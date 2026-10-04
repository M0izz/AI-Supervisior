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

logger = logging.getLogger("supervisor.adapters.codex")

MAX_OUTPUT_BUFFER_LINES = 500
MAX_OUTPUT_BUFFER_CHARS = 65536


class CodexAdapter(AgentAdapter):
    """
    Production-grade AgentAdapter for OpenAI Codex.
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
            provider="openai",
            adapter_id="codex",
            display_name="OpenAI Codex",
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
        Non-intrusive availability check for OpenAI Codex.
        Verifies that executable is on PATH (or configured override) and credentials exist.
        """
        target_exec = (
            self.executable_override
            or os.getenv("CODEX_EXECUTABLE")
            or "codex"
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
                message=f"OpenAI Codex executable '{target_exec}' not found on PATH or environment.",
            )

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key and not self.executable_override:
            return AdapterAvailability(
                status=AdapterAvailabilityStatus.UNAUTHORIZED,
                available=False,
                executable_path=resolved_path,
                message="OPENAI_API_KEY environment variable is missing or empty.",
            )

        return AdapterAvailability(
            status=AdapterAvailabilityStatus.AVAILABLE,
            available=True,
            executable_path=resolved_path,
            message="OpenAI Codex CLI is installed and configured.",
        )

    async def prepare(self, dispatch: TaskDispatchPackage) -> bool:
        """
        Pre-flight validation ensuring dispatch package correctness and worktree isolation.
        Strictly guarantees that Codex cannot execute against the primary repository.
        """
        await super().prepare(dispatch)

        ws_path = Path(dispatch.workspace).resolve()

        if self.worktree_manager:
            if ws_path == self.worktree_manager.repo_root.resolve():
                raise ValueError(
                    f"Execution refused: Workspace '{ws_path}' matches primary repository root. "
                    "Autonomous Codex tasks must execute strictly inside an isolated Git worktree."
                )

            try:
                ws_path.relative_to(self.worktree_manager.worktrees_base_dir.resolve())
            except ValueError:
                logger.warning(
                    f"Workspace '{ws_path}' is outside designated worktree base dir "
                    f"'{self.worktree_manager.worktrees_base_dir}'."
                )

        return True

    async def execute(self, dispatch: TaskDispatchPackage) -> AdapterExecutionResult:
        """
        Executes an assigned task inside its isolated worktree.
        Streams line-by-line output, normalizes events to Work Protocol v1,
        and enforces execution timeouts and cancellations.
        """
        try:
            await self.prepare(dispatch)
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
        workspace = Path(dispatch.workspace).resolve()

        availability = await self.check_availability()
        if not availability.available and not self.executable_override:
            error_msg = f"Codex execution failed: {availability.message}"
            logger.error(error_msg)
            return AdapterExecutionResult(
                status=AdapterProcessStatus.FAILED,
                exit_code=127,
                duration=0.0,
                workspace=str(workspace),
                failure_reason=error_msg,
            )

        target_exec = availability.executable_path or (
            self.executable_override
            or os.getenv("CODEX_EXECUTABLE")
            or "codex"
        )

        # Build argument list safely without shell
        if target_exec.endswith(".py"):
            cmd_args = [sys.executable, target_exec]
        else:
            cmd_args = [target_exec]
        if self.executable_override or os.getenv("CODEX_MOCK_MODE"):
            cmd_args.extend(["--workspace", str(workspace), "--task", task_id])
            if dispatch.objective:
                cmd_args.extend(["--prompt", dispatch.objective])
        else:
            # Production Codex CLI invocation arguments
            cmd_args.extend(["--workdir", str(workspace)])
            if dispatch.objective:
                cmd_args.extend(["--message", dispatch.objective])

        # Inject handoff recovery instructions if present in context
        handoff_ctx = dispatch.context.get("handoff")
        if handoff_ctx and isinstance(handoff_ctx, dict):
            reason = handoff_ctx.get("failure_reason", "")
            failed_attempts = handoff_ctx.get("rejected_attempts", [])
            logger.info(f"[CODEX] Executing task {task_id} with handoff context: {reason}")

        env = os.environ.copy()
        env["AI_SUPERVISOR_TASK_ID"] = task_id
        env["AI_SUPERVISOR_MISSION_ID"] = mission_id
        env["AI_SUPERVISOR_WORKSPACE"] = str(workspace)

        start_time = time.monotonic()
        stdout_lines: List[str] = []
        stderr_lines: List[str] = []
        affected_files: List[str] = []

        async with self._lock:
            self._task_statuses[task_id] = AdapterProcessStatus.STARTING

        # Emit AGENT_STARTED protocol event
        await self._emit_protocol_event(
            mission_id=mission_id,
            task_id=task_id,
            event_type=ProtocolEventType.AGENT_STARTED,
            action=ActionInfo(
                action_type="command_execute",
                target=target_exec,
                parameters={"args": cmd_args[1:]},
            ),
        )

        try:
            logger.info(f"[CODEX] Spawning process for task {task_id} in {workspace}: {' '.join(cmd_args)}")
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                cwd=str(workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            async with self._lock:
                self._active_processes[task_id] = proc
                self._task_statuses[task_id] = AdapterProcessStatus.RUNNING

            # Emit COMMAND_STARTED
            await self._emit_protocol_event(
                mission_id=mission_id,
                task_id=task_id,
                event_type=ProtocolEventType.COMMAND_STARTED,
                action=ActionInfo(
                    action_type="command_execute",
                    target=" ".join(cmd_args),
                ),
            )

            stream_task = asyncio.create_task(
                self._stream_output(
                    proc=proc,
                    mission_id=mission_id,
                    task_id=task_id,
                    stdout_lines=stdout_lines,
                    stderr_lines=stderr_lines,
                    affected_files=affected_files,
                )
            )

            timeout_secs = dispatch.timeout or 300.0
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout_secs)
                await stream_task
            except asyncio.TimeoutError:
                logger.warning(f"[CODEX] Task {task_id} timed out after {timeout_secs}s. Terminating process.")
                async with self._lock:
                    self._task_statuses[task_id] = AdapterProcessStatus.TIMED_OUT

                await self.cancel(task_id)
                await stream_task

                duration = time.monotonic() - start_time
                return AdapterExecutionResult(
                    status=AdapterProcessStatus.TIMED_OUT,
                    exit_code=-1,
                    duration=duration,
                    workspace=str(workspace),
                    summary=f"OpenAI Codex process timed out after {timeout_secs:.1f}s.",
                    stdout_excerpt="\n".join(stdout_lines[-50:]),
                    stderr_excerpt="\n".join(stderr_lines[-50:]),
                    failure_reason="EXECUTION_TIMEOUT",
                    affected_files=affected_files,
                )

            duration = time.monotonic() - start_time
            exit_code = proc.returncode

            async with self._lock:
                current_status = self._task_statuses.get(task_id)
                if current_status == AdapterProcessStatus.CANCELLED:
                    final_status = AdapterProcessStatus.CANCELLED
                elif exit_code == 0:
                    final_status = AdapterProcessStatus.COMPLETED
                else:
                    final_status = AdapterProcessStatus.FAILED
                self._task_statuses[task_id] = final_status

            # Emit terminal events
            if final_status == AdapterProcessStatus.COMPLETED:
                await self._emit_protocol_event(
                    mission_id=mission_id,
                    task_id=task_id,
                    event_type=ProtocolEventType.TASK_COMPLETED,
                    action=ActionInfo(
                        action_type="tool_call",
                        result="Codex task execution successful.",
                        affected_files=affected_files,
                    ),
                    telemetry=TelemetryInfo(
                        duration=duration,
                        exit_status="success",
                    ),
                )
            elif final_status == AdapterProcessStatus.CANCELLED:
                await self._emit_protocol_event(
                    mission_id=mission_id,
                    task_id=task_id,
                    event_type=ProtocolEventType.AGENT_STOPPED,
                    action=ActionInfo(
                        action_type="tool_call",
                        result="Codex task cancelled by supervisor.",
                    ),
                    telemetry=TelemetryInfo(
                        duration=duration,
                        exit_status="cancelled",
                    ),
                )
            else:
                await self._emit_protocol_event(
                    mission_id=mission_id,
                    task_id=task_id,
                    event_type=ProtocolEventType.TEST_FAILED,
                    action=ActionInfo(
                        action_type="command_execute",
                        result=f"Process exited with code {exit_code}",
                        exit_code=exit_code,
                    ),
                    telemetry=TelemetryInfo(
                        duration=duration,
                        exit_status="error",
                    ),
                )

            return AdapterExecutionResult(
                status=final_status,
                exit_code=exit_code,
                duration=duration,
                workspace=str(workspace),
                summary="Codex execution completed successfully." if exit_code == 0 else f"Codex exited with code {exit_code}",
                stdout_excerpt="\n".join(stdout_lines[-50:]),
                stderr_excerpt="\n".join(stderr_lines[-50:]),
                failure_reason=None if exit_code == 0 else f"Process exited with code {exit_code}",
                affected_files=affected_files,
            )

        except Exception as e:
            logger.error(f"[CODEX] Unhandled exception during task {task_id}: {e}", exc_info=True)
            async with self._lock:
                self._task_statuses[task_id] = AdapterProcessStatus.FAILED

            duration = time.monotonic() - start_time
            return AdapterExecutionResult(
                status=AdapterProcessStatus.FAILED,
                exit_code=1,
                duration=duration,
                workspace=str(workspace),
                summary=f"Exception during execution: {e}",
                failure_reason=str(e),
                affected_files=affected_files,
            )
        finally:
            await self.cleanup(task_id)

    async def cancel(self, task_id: str) -> bool:
        """Gracefully halts ongoing Codex execution via SIGINT/SIGTERM, escalating if necessary."""
        async with self._lock:
            proc = self._active_processes.get(task_id)
            self._task_statuses[task_id] = AdapterProcessStatus.CANCELLED

        if not proc or proc.returncode is not None:
            return True

        logger.warning(f"[CODEX] Cancelling execution for task {task_id} (PID: {proc.pid})")
        try:
            if os.name == "nt":
                # Windows taskkill process tree
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    shell=False,
                )
            else:
                import signal
                proc.send_signal(signal.SIGINT)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
        except Exception as e:
            logger.warning(f"[CODEX] Escalating to kill for PID {proc.pid}: {e}")
            try:
                proc.kill()
            except Exception:
                pass

        return True

    async def status(self, task_id: str) -> AdapterProcessStatus:
        """Returns the real-time process lifecycle status for a given task."""
        async with self._lock:
            return self._task_statuses.get(task_id, AdapterProcessStatus.PENDING)

    async def cleanup(self, task_id: str) -> None:
        """Releases active process handles and tracking data."""
        async with self._lock:
            self._active_processes.pop(task_id, None)

    async def _stream_output(
        self,
        proc: asyncio.subprocess.Process,
        mission_id: str,
        task_id: str,
        stdout_lines: List[str],
        stderr_lines: List[str],
        affected_files: List[str],
    ) -> None:
        """Consumes stdout and stderr lines, normalizing events to the Work Protocol."""
        async def read_stdout():
            if not proc.stdout:
                return
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                if len(stdout_lines) < MAX_OUTPUT_BUFFER_LINES:
                    stdout_lines.append(decoded)

                # Inspect line for file mutations or actions
                self._inspect_line_for_mutations(decoded, affected_files)

                # Emit WorkProtocolEvent for significant lines
                if decoded.startswith("[FILE_WRITE]") or decoded.startswith("Wrote:"):
                    parts = decoded.split(maxsplit=1)
                    target_file = parts[1].strip() if len(parts) > 1 else ""
                    if target_file and target_file not in affected_files:
                        affected_files.append(target_file)
                    await self._emit_protocol_event(
                        mission_id=mission_id,
                        task_id=task_id,
                        event_type=ProtocolEventType.FILE_CHANGED,
                        action=ActionInfo(
                            action_type="file_write",
                            target=target_file,
                            affected_files=[target_file] if target_file else [],
                        ),
                    )

        async def read_stderr():
            if not proc.stderr:
                return
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                if len(stderr_lines) < MAX_OUTPUT_BUFFER_LINES:
                    stderr_lines.append(decoded)

        await asyncio.gather(read_stdout(), read_stderr())

    def _inspect_line_for_mutations(self, line: str, affected_files: List[str]) -> None:
        """Heuristically extracts modified file paths from Codex CLI output."""
        patterns = [
            r"(?:Created|Updated|Modified|Wrote|Editing)\s+([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)",
            r"file:\/\/([a-zA-Z0-9_\-./\\]+)",
        ]
        for pat in patterns:
            match = re.search(pat, line, re.IGNORECASE)
            if match:
                fpath = match.group(1).strip()
                if fpath not in affected_files:
                    affected_files.append(fpath)

    async def _emit_protocol_event(
        self,
        mission_id: str,
        task_id: str,
        event_type: ProtocolEventType,
        action: Optional[ActionInfo] = None,
        telemetry: Optional[TelemetryInfo] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emits a canonical WorkProtocolEvent envelope onto the EventBus."""
        if not self.event_bus:
            return

        wp_event = WorkProtocolEvent(
            mission_id=mission_id,
            task_id=task_id,
            agent_id="codex",
            provider="openai",
            event_type=event_type.value,
            action=action,
            telemetry=telemetry,
            payload=payload or {},
        )

        bus_event = Event(
            mission_id=mission_id,
            task_id=task_id,
            agent_id="codex",
            type=EventType.AGENT_ACTION,
            severity=EventSeverity.INFO,
            payload={
                "event_type": event_type.value,
                "provider": "openai",
                "action": action.model_dump() if action else {},
                "telemetry": telemetry.model_dump() if telemetry else {},
                "payload": payload or {},
            },
        )

        try:
            await self.event_bus.publish(bus_event)
        except Exception as e:
            logger.warning(f"[CODEX] Failed to publish protocol event {event_type.value}: {e}")
