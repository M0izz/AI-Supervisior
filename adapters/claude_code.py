import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any, Dict, List, Optional

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.protocol.schema import (
    WorkProtocolEvent,
    TaskDispatchPackage,
)
from core.protocol.actions import ActionInfo, TelemetryInfo
from core.protocol.events import ProtocolEventType
from execution.worktree import GitWorktreeManager
from adapters.base import AgentAdapter
from adapters.models import (
    AdapterIdentity,
    AdapterCapability,
    AdapterAvailability,
    AdapterAvailabilityStatus,
    AdapterProcessStatus,
    AdapterExecutionResult,
)

logger = logging.getLogger("supervisor.adapters.claude_code")

MAX_OUTPUT_BUFFER_LINES = 500
MAX_OUTPUT_BUFFER_CHARS = 65536


class ClaudeCodeAdapter(AgentAdapter):
    """
    Production-grade AgentAdapter for Anthropic Claude Code.
    Controls execution inside isolated Git worktrees, streams stdout/stderr,
    normalizes events into Work Protocol v1, and manages timeouts & cancellations.
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        worktree_manager: Optional[GitWorktreeManager] = None,
        executable_override: Optional[str] = None,
    ):
        self.event_bus = event_bus
        self.worktree_manager = worktree_manager
        self.executable_override = executable_override

        self._active_processes: Dict[str, asyncio.subprocess.Process] = {}
        self._task_statuses: Dict[str, AdapterProcessStatus] = {}
        self._lock = asyncio.Lock()

    @property
    def identity(self) -> AdapterIdentity:
        return AdapterIdentity(
            provider="anthropic",
            adapter_id="claude_code",
            display_name="Claude Code",
            version="1.0.0",
            capabilities=[
                AdapterCapability.CODE_EXECUTION.value,
                AdapterCapability.FILESYSTEM_READ.value,
                AdapterCapability.FILESYSTEM_WRITE.value,
                AdapterCapability.TERMINAL_EXECUTION.value,
                AdapterCapability.GIT.value,
                AdapterCapability.TEST_EXECUTION.value,
            ],
        )

    async def check_availability(self) -> AdapterAvailability:
        """
        Non-intrusive availability check for Claude Code.
        Verifies that executable is on PATH (or configured override) and credentials exist.
        """
        target_exec = (
            self.executable_override
            or os.getenv("CLAUDE_CODE_EXECUTABLE")
            or "claude"
        )
        resolved_path = shutil.which(target_exec)
        if not resolved_path:
            # Check if override was an explicit file path that exists
            p = Path(target_exec)
            if p.exists() and p.is_file():
                resolved_path = str(p.resolve())

        if not resolved_path:
            return AdapterAvailability(
                status=AdapterAvailabilityStatus.NOT_INSTALLED,
                available=False,
                message=f"Claude Code executable '{target_exec}' not found on PATH or environment.",
            )

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key and not self.executable_override:
            return AdapterAvailability(
                status=AdapterAvailabilityStatus.UNAUTHORIZED,
                available=False,
                message="ANTHROPIC_API_KEY environment variable is not configured.",
                executable_path=resolved_path,
            )

        return AdapterAvailability(
            status=AdapterAvailabilityStatus.AVAILABLE,
            available=True,
            message="Claude Code is available and configured.",
            executable_path=resolved_path,
        )

    def _verify_worktree_isolation(self, workspace_path: str) -> Path:
        """
        Strictly enforces that task workspace is an isolated worktree.
        Refuses execution if directory is the primary repository or outside worktree root.
        """
        resolved = Path(workspace_path).resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ValueError(f"Task workspace does not exist or is not a directory: {workspace_path}")

        if self.worktree_manager:
            # Refuse execution if pointing to primary repository root
            if resolved == self.worktree_manager.repo_root:
                raise ValueError(
                    f"Execution refused: Workspace '{resolved}' matches primary repository root. "
                    "Claude Code must execute inside an isolated Git worktree."
                )

            # Refuse execution if not within supervisor worktrees base directory
            try:
                resolved.relative_to(self.worktree_manager.worktrees_base_dir)
            except ValueError:
                raise ValueError(
                    f"Execution refused: Workspace '{resolved}' is outside supervisor worktree directory "
                    f"'{self.worktree_manager.worktrees_base_dir}'."
                )

        return resolved

    def _build_prompt(self, dispatch: TaskDispatchPackage) -> str:
        """Constructs an authoritative task prompt from the dispatch package."""
        lines = [
            f"# Mission: {dispatch.mission_id}",
            f"## Task {dispatch.task_id}: {dispatch.objective}",
            "",
            "### Instructions & Scope:",
        ]
        if dispatch.allowed_files:
            lines.append("You are strictly constrained to modify ONLY these files:")
            for f in dispatch.allowed_files:
                lines.append(f"- {f}")
            lines.append("")

        if dispatch.dependencies:
            lines.append(f"Prerequisite tasks completed: {', '.join(dispatch.dependencies)}")
            lines.append("")

        if dispatch.context:
            lines.append("### Context & Memory:")
            for k, v in dispatch.context.items():
                lines.append(f"**{k}**: {v}")
            lines.append("")

        if dispatch.verification_requirements:
            lines.append("### Verification Criteria:")
            lines.append("Your work must pass the following verification tests before completion:")
            for req in dispatch.verification_requirements:
                lines.append(f"- `{req}`")
            lines.append("")

        lines.append("Please perform the required edits, run tests to verify your changes, and summarize your work.")
        return "\n".join(lines)

    async def _emit_event(
        self,
        event_type: str,
        dispatch: TaskDispatchPackage,
        action: Optional[ActionInfo] = None,
        telemetry: Optional[TelemetryInfo] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emits normalized WorkProtocolEvent to EventBus if connected."""
        if not self.event_bus:
            return

        event_payload = payload or {}
        event = Event(
            mission_id=dispatch.mission_id,
            task_id=dispatch.task_id,
            agent_id="claude_code",
            type=EventType(event_type) if event_type in [e.value for e in EventType] else EventType.AGENT_ACTION,
            severity=EventSeverity.INFO,
            payload={
                "provider": "anthropic",
                "adapter_id": "claude_code",
                "event_type": event_type,
                "action": action.model_dump() if action else None,
                "telemetry": telemetry.model_dump() if telemetry else None,
                **event_payload,
            }
        )
        try:
            await self.event_bus.publish(event)
        except Exception as e:
            logger.warning(f"Failed to publish WorkProtocolEvent to EventBus: {e}")

    async def execute(self, dispatch: TaskDispatchPackage) -> AdapterExecutionResult:
        """
        Executes Claude Code in the designated isolated worktree without shell injection.
        """
        try:
            await self.prepare(dispatch)
            ws_path = self._verify_worktree_isolation(dispatch.workspace)
        except Exception as e:
            return AdapterExecutionResult(
                status=AdapterProcessStatus.FAILED,
                exit_code=-1,
                duration=0.0,
                workspace=str(dispatch.workspace),
                failure_reason=str(e),
            )

        # Check availability
        avail = await self.check_availability()
        if not avail.available and not self.executable_override:
            return AdapterExecutionResult(
                status=AdapterProcessStatus.FAILED,
                exit_code=-1,
                duration=0.0,
                workspace=str(ws_path),
                failure_reason=f"Claude Code unavailable: {avail.message}",
            )

        executable = self.executable_override or avail.executable_path or "claude"

        prompt = self._build_prompt(dispatch)
        # Construct argument list safely (NO shell=True)
        # If executable_override is a python command or script, accommodate argument structure
        if executable.endswith(".py"):
            args = ["python", executable, "-p", prompt]
        else:
            args = [executable, "-p", prompt]

        # Note permission limitations
        if not dispatch.permissions.get("allow_network", False):
            logger.info(
                f"[ADAPTER] Task {dispatch.task_id} requests allow_network=False. "
                "Host CLI execution does not enforce kernel network boundaries. "
                "For strict network isolation, execution must use container sandboxing."
            )

        start_time = time.monotonic()
        async with self._lock:
            self._task_statuses[dispatch.task_id] = AdapterProcessStatus.STARTING

        # Emit started event
        await self._emit_event(
            ProtocolEventType.AGENT_STARTED.value,
            dispatch,
            action=ActionInfo(action_type="agent_launch", target=executable),
            payload={"prompt_preview": prompt[:200]},
        )

        stdout_lines: List[str] = []
        stderr_lines: List[str] = []
        affected_files: List[str] = []

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(ws_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            async with self._lock:
                self._active_processes[dispatch.task_id] = process
                self._task_statuses[dispatch.task_id] = AdapterProcessStatus.RUNNING

            await self._emit_event(
                ProtocolEventType.COMMAND_STARTED.value,
                dispatch,
                action=ActionInfo(action_type="command_execute", target=" ".join(args[:2])),
            )

            # Stream stdout and stderr concurrently
            async def read_stream(stream, lines_list, is_stderr=False):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    if len(lines_list) < MAX_OUTPUT_BUFFER_LINES:
                        lines_list.append(decoded)

                    # Look for file changes or tool indicators in output
                    if not is_stderr and ("Writing" in decoded or "Editing" in decoded or "Created" in decoded):
                        match = re.search(r'(?:Writing|Editing|Created)\s+([^\s\(\)]+)', decoded)
                        if match:
                            filepath = match.group(1)
                            if filepath not in affected_files:
                                affected_files.append(filepath)
                                await self._emit_event(
                                    ProtocolEventType.FILE_CHANGED.value,
                                    dispatch,
                                    action=ActionInfo(action_type="file_write", target=filepath),
                                )

            timeout_sec = dispatch.timeout or 300.0
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(process.stdout, stdout_lines, is_stderr=False),
                        read_stream(process.stderr, stderr_lines, is_stderr=True),
                        process.wait(),
                    ),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Claude Code process for task {dispatch.task_id} timed out after {timeout_sec}s.")
                async with self._lock:
                    self._task_statuses[dispatch.task_id] = AdapterProcessStatus.TIMED_OUT

                # Forceful cleanup
                try:
                    process.terminate()
                    await asyncio.sleep(0.5)
                    if process.returncode is None:
                        process.kill()
                except Exception:
                    pass

                duration = time.monotonic() - start_time
                await self._emit_event(
                    ProtocolEventType.AGENT_STOPPED.value,
                    dispatch,
                    telemetry=TelemetryInfo(duration=duration, exit_status="timeout"),
                    payload={"reason": f"Execution timed out after {timeout_sec}s"},
                )

                return AdapterExecutionResult(
                    status=AdapterProcessStatus.TIMED_OUT,
                    exit_code=-9,
                    duration=duration,
                    workspace=str(ws_path),
                    summary=f"Task timed out after {timeout_sec} seconds.",
                    stdout_excerpt="\n".join(stdout_lines[-30:]),
                    stderr_excerpt="\n".join(stderr_lines[-30:]),
                    failure_reason="Process execution timed out.",
                    affected_files=affected_files,
                )

            duration = time.monotonic() - start_time
            exit_code = process.returncode

            # Check if cancelled while running
            async with self._lock:
                current_status = self._task_statuses.get(dispatch.task_id, AdapterProcessStatus.RUNNING)

            if current_status == AdapterProcessStatus.CANCELLED:
                return AdapterExecutionResult(
                    status=AdapterProcessStatus.CANCELLED,
                    exit_code=exit_code,
                    duration=duration,
                    workspace=str(ws_path),
                    summary="Execution was explicitly cancelled by Supervisor.",
                    stdout_excerpt="\n".join(stdout_lines[-30:]),
                    stderr_excerpt="\n".join(stderr_lines[-30:]),
                    failure_reason="Cancelled by operator.",
                    affected_files=affected_files,
                )

            if exit_code == 0:
                async with self._lock:
                    self._task_statuses[dispatch.task_id] = AdapterProcessStatus.COMPLETED

                await self._emit_event(
                    ProtocolEventType.TASK_COMPLETED.value,
                    dispatch,
                    telemetry=TelemetryInfo(duration=duration, exit_status="success"),
                    payload={"exit_code": 0, "affected_files": affected_files},
                )
                await self._emit_event(
                    ProtocolEventType.AGENT_STOPPED.value,
                    dispatch,
                    telemetry=TelemetryInfo(duration=duration, exit_status="success"),
                    payload={"exit_code": 0, "affected_files": affected_files},
                )
                await self._emit_event(
                    ProtocolEventType.COMMAND_COMPLETED.value,
                    dispatch,
                    action=ActionInfo(action_type="command_execute", exit_code=0, affected_files=affected_files),
                    telemetry=TelemetryInfo(duration=duration, exit_status="success"),
                )

                return AdapterExecutionResult(
                    status=AdapterProcessStatus.COMPLETED,
                    exit_code=0,
                    duration=duration,
                    workspace=str(ws_path),
                    summary="Claude Code completed successfully.",
                    stdout_excerpt="\n".join(stdout_lines[-30:]),
                    stderr_excerpt="\n".join(stderr_lines[-30:]),
                    affected_files=affected_files,
                )
            else:
                async with self._lock:
                    self._task_statuses[dispatch.task_id] = AdapterProcessStatus.FAILED

                err_msg = "\n".join(stderr_lines[-10:]) or f"Process exited with non-zero code {exit_code}"
                await self._emit_event(
                    ProtocolEventType.TEST_FAILED.value,
                    dispatch,
                    telemetry=TelemetryInfo(duration=duration, exit_status="failed"),
                    payload={"exit_code": exit_code, "error": err_msg},
                )

                return AdapterExecutionResult(
                    status=AdapterProcessStatus.FAILED,
                    exit_code=exit_code,
                    duration=duration,
                    workspace=str(ws_path),
                    summary=f"Claude Code failed with exit code {exit_code}.",
                    stdout_excerpt="\n".join(stdout_lines[-30:]),
                    stderr_excerpt="\n".join(stderr_lines[-30:]),
                    failure_reason=err_msg,
                    affected_files=affected_files,
                )

        except Exception as e:
            duration = time.monotonic() - start_time
            logger.exception(f"Unhandled exception executing Claude Code for task {dispatch.task_id}: {e}")
            async with self._lock:
                self._task_statuses[dispatch.task_id] = AdapterProcessStatus.FAILED

            return AdapterExecutionResult(
                status=AdapterProcessStatus.FAILED,
                exit_code=-1,
                duration=duration,
                workspace=str(ws_path),
                summary=f"Failed to launch or execute Claude Code: {str(e)}",
                failure_reason=str(e),
                affected_files=affected_files,
            )
        finally:
            await self.cleanup(dispatch.task_id)

    async def cancel(self, task_id: str) -> bool:
        """Gracefully terminates active Claude Code subprocess."""
        async with self._lock:
            process = self._active_processes.get(task_id)
            if not process or process.returncode is not None:
                return False

            self._task_statuses[task_id] = AdapterProcessStatus.CANCELLED

        try:
            process.terminate()
            # Wait up to 2 seconds for clean exit before escalation
            for _ in range(20):
                if process.returncode is not None:
                    break
                await asyncio.sleep(0.1)

            if process.returncode is None:
                process.kill()
            logger.info(f"[ADAPTER] Cancelled Claude Code process for task {task_id}")
            return True
        except Exception as e:
            logger.warning(f"Error terminating Claude Code process for task {task_id}: {e}")
            return False

    async def status(self, task_id: str) -> AdapterProcessStatus:
        """Returns the real-time status of the Claude Code task process."""
        async with self._lock:
            return self._task_statuses.get(task_id, AdapterProcessStatus.PENDING)

    async def cleanup(self, task_id: str) -> None:
        """Removes process handle references without deleting the worktree."""
        async with self._lock:
            self._active_processes.pop(task_id, None)
