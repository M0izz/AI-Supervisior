import asyncio
import os
from pathlib import Path
from typing import Optional
from tools.base import BaseTool, ToolResult
from execution.manager import ExecutionManager
from execution.models import ExecutionRequest, ExecutionStatus


class RunCommandTool(BaseTool):
    name = "run_command"
    description = "Execute a command inside the workspace directory with timeout."

    ALLOWED_COMMAND_PREFIXES = (
        "python", "pytest", "git", "ls", "dir", "pwd", "echo", "cat", "type", "head", "tail"
    )

    DANGEROUS_PATTERNS = (
        "rm -rf", "drop table", "drop database", "format ", "mkfs",
        "dd if=", "chmod 777", "chmod -R 777", "kill -9", "shutdown",
        ":(){ :|:& };:"
    )

    def __init__(self, workspace_root: Path, execution_manager: Optional[ExecutionManager] = None):
        super().__init__(workspace_root)
        self.execution_manager = execution_manager or ExecutionManager()

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

    async def execute(self, command: str, timeout: int = 30) -> ToolResult:
        try:
            self.validate_command(command)

            req = ExecutionRequest(
                command=command,
                workspace_root=self.workspace_root,
                timeout_seconds=timeout
            )
            res = await self.execution_manager.execute(req)

            if res.status == ExecutionStatus.BLOCKED or res.metadata.get("danger_detected"):
                return ToolResult(success=False, error=res.error, metadata={"danger_detected": True})

            if res.status == ExecutionStatus.TIMEOUT:
                return ToolResult(success=False, error=f"Command timed out after {timeout} seconds", metadata={"timeout": True})

            if res.status == ExecutionStatus.ERROR:
                return ToolResult(success=False, error=res.error, metadata={"error": True})

            success = res.exit_code == 0
            return ToolResult(
                success=success,
                output=res.stdout[:2000] if res.stdout else None,
                error=res.stderr[:1000] if (res.stderr and not success) else None,
                metadata={
                    "returncode": res.exit_code,
                    "backend": res.backend,
                    "container_id": res.container.container_id if res.container else None
                }
            )
        except PermissionError as pe:
            return ToolResult(success=False, error=str(pe), metadata={"danger_detected": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))

