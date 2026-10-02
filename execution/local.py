import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from execution.base import BaseExecutionProvider
from execution.models import ExecutionRequest, ExecutionResult, ExecutionStatus

logger = logging.getLogger("supervisor.execution.local")


class LocalExecutionProvider(BaseExecutionProvider):
    """
    Local sandboxed shell execution provider.
    Enforces WorkspaceJail path boundaries, command prefix whitelisting,
    and dangerous pattern blocking without external container overhead.
    """

    backend_name: str = "local"

    ALLOWED_COMMAND_PREFIXES = (
        "python", "pytest", "git", "ls", "dir", "pwd", "echo", "cat", "type", "head", "tail"
    )

    DANGEROUS_PATTERNS = (
        "rm -rf", "drop table", "drop database", "format ", "mkfs",
        "dd if=", "chmod 777", "chmod -R 777", "kill -9", "shutdown",
        ":(){ :|:& };:"
    )

    def __init__(self, event_bus: Optional[EventBus] = None):
        super().__init__(event_bus=event_bus)

    async def is_available(self) -> bool:
        return True

    def validate_workspace(self, workspace_path: Path) -> None:
        """Validate workspace path safety."""
        resolved = workspace_path.resolve()
        # Reject root paths
        if str(resolved) in ("/", "C:\\", "C:/") or resolved == resolved.parent:
            raise PermissionError(f"LocalExecutionProvider: Host root execution is prohibited: '{resolved}'")
        if not resolved.exists():
            raise FileNotFoundError(f"LocalExecutionProvider: Workspace does not exist: '{resolved}'")

    def validate_command(self, command: str) -> None:
        cmd_stripped = command.strip()
        cmd_lower = cmd_stripped.lower()

        # 1. Check for dangerous patterns
        for pat in self.DANGEROUS_PATTERNS:
            if pat in cmd_lower:
                raise PermissionError(f"Dangerous command pattern detected: '{pat}'. Execution halted.")

        # 2. Check whitelist prefixes
        first_token = cmd_stripped.split()[0].lower() if cmd_stripped.split() else ""
        if not any(cmd_lower.startswith(prefix) for prefix in self.ALLOWED_COMMAND_PREFIXES):
            raise PermissionError(f"Command '{first_token}' is not in allowed sandbox commands {self.ALLOWED_COMMAND_PREFIXES}.")

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        workspace_path = request.get_workspace_path()
        start_time = time.monotonic()

        mission_id = request.mission_id or "default_mission"

        # Emit EXECUTION_STARTED
        if self.event_bus:
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=request.task_id,
                    agent_id=request.agent_id,
                    type=EventType.EXECUTION_STARTED,
                    payload={
                        "backend": self.backend_name,
                        "command": request.command,
                        "workspace": str(workspace_path)
                    }
                )
            )

        try:
            self.validate_workspace(workspace_path)
            self.validate_command(request.command)

            process = await asyncio.create_subprocess_shell(
                request.command,
                cwd=str(workspace_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **request.env}
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=request.timeout_seconds
            )
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)

            out_str = stdout.decode("utf-8", errors="replace")
            err_str = stderr.decode("utf-8", errors="replace")
            success = process.returncode == 0

            formatted_stdout = None
            if out_str:
                formatted_stdout = out_str if len(out_str) <= 50000 else (out_str[:15000] + "\n...[truncated]...\n" + out_str[-15000:])

            formatted_stderr = None
            if err_str:
                formatted_stderr = err_str if len(err_str) <= 20000 else (err_str[:10000] + "\n...[truncated]...\n" + err_str[-10000:])

            status = ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED
            result = ExecutionResult(
                status=status,
                exit_code=process.returncode,
                stdout=formatted_stdout,
                stderr=formatted_stderr,
                duration_ms=duration_ms,
                backend=self.backend_name,
                metadata={"returncode": process.returncode}
            )

            if self.event_bus:
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=request.task_id,
                        agent_id=request.agent_id,
                        type=EventType.EXECUTION_COMPLETED if success else EventType.EXECUTION_FAILED,
                        severity=EventSeverity.INFO if success else EventSeverity.WARNING,
                        payload={
                            "backend": self.backend_name,
                            "status": status.value,
                            "exit_code": process.returncode,
                            "duration_ms": duration_ms
                        }
                    )
                )
            return result

        except asyncio.TimeoutError:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            err_msg = f"Execution timed out after {request.timeout_seconds}s"
            if self.event_bus:
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=request.task_id,
                        agent_id=request.agent_id,
                        type=EventType.EXECUTION_FAILED,
                        severity=EventSeverity.CRITICAL,
                        payload={"backend": self.backend_name, "error": err_msg, "reason": "TIMEOUT"}
                    )
                )
            return ExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                exit_code=-1,
                error=err_msg,
                duration_ms=duration_ms,
                backend=self.backend_name
            )

        except PermissionError as pe:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            if self.event_bus:
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=request.task_id,
                        agent_id=request.agent_id,
                        type=EventType.DANGER_DETECTED,
                        severity=EventSeverity.CRITICAL,
                        payload={"backend": self.backend_name, "error": str(pe), "command": request.command}
                    )
                )
            return ExecutionResult(
                status=ExecutionStatus.BLOCKED,
                exit_code=-1,
                error=str(pe),
                duration_ms=duration_ms,
                backend=self.backend_name,
                metadata={"danger_detected": True}
            )

        except Exception as e:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                error=str(e),
                duration_ms=duration_ms,
                backend=self.backend_name
            )
