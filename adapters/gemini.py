import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
import shutil
import sys
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

logger = logging.getLogger("supervisor.adapters.gemini")

MAX_OUTPUT_BUFFER_LINES = 500
MAX_OUTPUT_BUFFER_CHARS = 65536


class GeminiAdapter(AgentAdapter):
    """
    Production-grade AgentAdapter for Google Gemini CLI / SDK runtime.
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
            provider="google",
            adapter_id="gemini",
            display_name="Gemini CLI",
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
        Lightweight diagnostic check for Gemini CLI.
        Verifies executable on PATH (or configured override) and credentials exist.
        """
        target_exec = (
            self.executable_override
            or os.getenv("GEMINI_EXECUTABLE")
            or "gemini"
        )
        resolved_path = shutil.which(target_exec)
        if not resolved_path:
            p = Path(target_exec)
            if p.exists() and p.is_file():
                resolved_path = str(p.resolve())

        if not resolved_path:
            return AdapterAvailability(
                status=AdapterAvailabilityStatus.NOT_INSTALLED,
                available=False,
                message=f"Gemini executable '{target_exec}' not found on PATH or environment.",
            )

        api_key = os.getenv("GEMINI_API_KEY")
        adc_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not api_key and not adc_creds and not self.executable_override:
            return AdapterAvailability(
                status=AdapterAvailabilityStatus.UNAUTHORIZED,
                available=False,
                executable_path=resolved_path,
                message="GEMINI_API_KEY or GOOGLE_APPLICATION_CREDENTIALS is not configured.",
            )

        return AdapterAvailability(
            status=AdapterAvailabilityStatus.AVAILABLE,
            available=True,
            executable_path=resolved_path,
            message="Gemini CLI is installed and configured.",
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
            if resolved == self.worktree_manager.repo_root.resolve():
                raise ValueError(
                    f"Execution refused: Workspace '{resolved}' matches primary repository root. "
                    "Gemini must execute inside an isolated Git worktree."
                )

            try:
                resolved.relative_to(self.worktree_manager.worktrees_base_dir.resolve())
            except ValueError:
                logger.warning(
                    f"Workspace '{resolved}' is outside supervisor worktree directory "
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
            agent_id="gemini",
            type=EventType(event_type) if event_type in [e.value for e in EventType] else EventType.AGENT_ACTION,
            severity=EventSeverity.INFO,
            payload={
                "provider": "google",
                "adapter_id": "gemini",
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
        Executes Gemini CLI in the designated isolated worktree without shell injection.
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

        task_id = dispatch.task_id
        mission_id = dispatch.mission_id

        avail = await self.check_availability()
        if not avail.available and not self.executable_override:
            return AdapterExecutionResult(
                status=AdapterProcessStatus.FAILED,
                exit_code=-1,
                duration=0.0,
                workspace=str(ws_path),
                failure_reason=f"Gemini unavailable: {avail.message}",
            )

        executable = self.executable_override or avail.executable_path or "gemini"
        prompt = self._build_prompt(dispatch)

        if executable.endswith(".py"):
            args = [sys.executable, executable, "-p", prompt]
        else:
            args = [executable, "-p", prompt]

        env = os.environ.copy()
        env["AI_SUPERVISOR_TASK_ID"] = task_id
        env["AI_SUPERVISOR_MISSION_ID"] = mission_id
        env["AI_SUPERVISOR_WORKSPACE"] = str(ws_path)

        start_time = time.monotonic()
        stdout_lines: List[str] = []
        stderr_lines: List[str] = []
        affected_files: List[str] = []

        async with self._lock:
            self._task_statuses[task_id] = AdapterProcessStatus.STARTING

        await self._emit_event(
            ProtocolEventType.AGENT_STARTED.value,
            dispatch,
            action=ActionInfo(action_type="agent_start", target=executable, parameters={"args": args[1:]}),
        )

        try:
            logger.info(f"[GEMINI] Spawning process for task {task_id} in {ws_path}: {' '.join(args)}")
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(ws_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            async with self._lock:
                self._active_processes[task_id] = proc
                self._task_statuses[task_id] = AdapterProcessStatus.RUNNING

            await self._emit_event(
                ProtocolEventType.COMMAND_STARTED.value,
                dispatch,
                action=ActionInfo(action_type="command_execute", target=" ".join(args)),
            )

            timeout_secs = dispatch.timeout or 300.0

            async def read_stream(stream, buffer_list, is_stderr=False):
                char_count = 0
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").rstrip()
                    if len(buffer_list) < MAX_OUTPUT_BUFFER_LINES and char_count < MAX_OUTPUT_BUFFER_CHARS:
                        buffer_list.append(decoded)
                        char_count += len(decoded)

                    await self._parse_line_to_event(decoded, dispatch, is_stderr, affected_files)

            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(proc.stdout, stdout_lines, is_stderr=False),
                        read_stream(proc.stderr, stderr_lines, is_stderr=True),
                        proc.wait(),
                    ),
                    timeout=timeout_secs,
                )
            except asyncio.TimeoutError:
                logger.error(f"[GEMINI] Task {task_id} timed out after {timeout_secs}s")
                await self._terminate_process(proc)
                async with self._lock:
                    self._task_statuses[task_id] = AdapterProcessStatus.TIMED_OUT

                duration = time.monotonic() - start_time
                await self._emit_event(
                    ProtocolEventType.AGENT_STOPPED.value,
                    dispatch,
                    payload={"reason": f"Execution timed out after {timeout_secs}s"},
                )
                return AdapterExecutionResult(
                    status=AdapterProcessStatus.TIMED_OUT,
                    exit_code=-1,
                    duration=duration,
                    workspace=str(ws_path),
                    stdout_excerpt="\n".join(stdout_lines[-20:]),
                    stderr_excerpt="\n".join(stderr_lines[-20:]),
                    failure_reason=f"Timed out after {timeout_secs}s",
                    affected_files=list(set(affected_files)),
                )

            duration = time.monotonic() - start_time
            exit_code = proc.returncode

            async with self._lock:
                current_status = self._task_statuses.get(task_id, AdapterProcessStatus.RUNNING)
                if current_status == AdapterProcessStatus.CANCELLED:
                    final_status = AdapterProcessStatus.CANCELLED
                elif exit_code == 0:
                    final_status = AdapterProcessStatus.COMPLETED
                else:
                    final_status = AdapterProcessStatus.FAILED
                self._task_statuses[task_id] = final_status

            await self._emit_event(
                ProtocolEventType.TASK_COMPLETED.value if final_status == AdapterProcessStatus.COMPLETED else ProtocolEventType.AGENT_STOPPED.value,
                dispatch,
                telemetry=TelemetryInfo(execution_time_ms=duration * 1000, exit_code=exit_code),
                payload={"status": final_status.value, "exit_code": exit_code},
            )

            return AdapterExecutionResult(
                status=final_status,
                exit_code=exit_code,
                duration=duration,
                workspace=str(ws_path),
                summary=stdout_lines[-1] if stdout_lines else ("Task completed" if exit_code == 0 else "Task failed"),
                stdout_excerpt="\n".join(stdout_lines[-20:]),
                stderr_excerpt="\n".join(stderr_lines[-20:]),
                failure_reason=None if exit_code == 0 else f"Process exited with code {exit_code}",
                affected_files=list(set(affected_files)),
            )

        except Exception as e:
            logger.error(f"[GEMINI] Exception executing task {task_id}: {e}")
            async with self._lock:
                self._task_statuses[task_id] = AdapterProcessStatus.FAILED
            duration = time.monotonic() - start_time
            return AdapterExecutionResult(
                status=AdapterProcessStatus.FAILED,
                exit_code=-1,
                duration=duration,
                workspace=str(ws_path),
                failure_reason=str(e),
            )
        finally:
            await self.cleanup(task_id)

    async def _parse_line_to_event(
        self,
        line: str,
        dispatch: TaskDispatchPackage,
        is_stderr: bool,
        affected_files: List[str],
    ) -> None:
        """Parses stdout/stderr lines and emits normalized WorkProtocol events."""
        clean = line.strip()
        if not clean:
            return

        file_write_match = re.search(r"(?:Created|Wrote|Modified|Editing|Writing)\s+([^\s]+\.\w+)", clean, re.IGNORECASE)
        if file_write_match:
            fpath = file_write_match.group(1).strip()
            affected_files.append(fpath)
            await self._emit_event(
                ProtocolEventType.FILE_CHANGED.value,
                dispatch,
                action=ActionInfo(action_type="file_modify", target=fpath),
            )

        test_fail_match = re.search(r"FAILED\s+([^\s:]+)", clean)
        if test_fail_match:
            test_target = test_fail_match.group(1).strip()
            await self._emit_event(
                ProtocolEventType.TEST_FAILED.value,
                dispatch,
                action=ActionInfo(action_type="test_run", target=test_target),
                payload={"failure_output": clean},
            )

        if "Error:" in clean or "Exception:" in clean or "fatal:" in clean:
            await self._emit_event(
                ProtocolEventType.AGENT_STOPPED.value,
                dispatch,
                payload={"error_line": clean},
            )

    async def _terminate_process(self, proc: asyncio.subprocess.Process) -> None:
        """Terminates process safely: SIGTERM -> grace period -> SIGKILL."""
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.warning(f"[GEMINI] Error terminating process: {e}")

    async def cancel(self, task_id: str) -> bool:
        """Cancels an active Gemini execution process."""
        async with self._lock:
            proc = self._active_processes.get(task_id)
            if not proc:
                return False
            self._task_statuses[task_id] = AdapterProcessStatus.CANCELLED

        logger.info(f"[GEMINI] Cancelling process for task {task_id}")
        await self._terminate_process(proc)
        return True

    async def status(self, task_id: str) -> AdapterProcessStatus:
        """Returns the process status of a given task."""
        async with self._lock:
            return self._task_statuses.get(task_id, AdapterProcessStatus.PENDING)

    async def cleanup(self, task_id: str) -> None:
        """Cleans up internal tracking handles for a completed task."""
        async with self._lock:
            self._active_processes.pop(task_id, None)
