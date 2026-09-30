import asyncio
import os
import subprocess
from pathlib import Path
from tools.base import BaseTool, ToolResult


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

    def validate_command(self, command: str) -> None:
        cmd_stripped = command.strip()
        cmd_lower = cmd_stripped.lower()

        # 1. Check for dangerous patterns
        for pat in self.DANGEROUS_PATTERNS:
            if pat in cmd_lower:
                raise PermissionError(f"Dangerous command pattern detected: '{pat}'. Execution halted.")

        # 2. Check whitelist prefixes
        first_token = cmd_stripped.split()[0].lower() if cmd_stripped.split() else ""
        # Handle python -m pytest or similar
        if not any(cmd_lower.startswith(prefix) for prefix in self.ALLOWED_COMMAND_PREFIXES):
            raise PermissionError(f"Command '{first_token}' is not in allowed sandbox commands {self.ALLOWED_COMMAND_PREFIXES}.")

    async def execute(self, command: str, timeout: int = 30) -> ToolResult:
        try:
            self.validate_command(command)

            process = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self.workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            out_str = stdout.decode("utf-8", errors="replace")
            err_str = stderr.decode("utf-8", errors="replace")

            success = process.returncode == 0
            return ToolResult(
                success=success,
                output=out_str[:2000] if out_str else None,
                error=err_str[:1000] if not success else None,
                metadata={"returncode": process.returncode}
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Command timed out after {timeout} seconds")
        except PermissionError as pe:
            return ToolResult(success=False, error=str(pe), metadata={"danger_detected": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
