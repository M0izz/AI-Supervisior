import asyncio
import os
import subprocess
from pathlib import Path
from tools.base import BaseTool, ToolResult


class RunCommandTool(BaseTool):
    name = "run_command"
    description = "Execute a command inside the workspace directory with timeout."

    async def execute(self, command: str, timeout: int = 30) -> ToolResult:
        try:
            # Run command synchronously in an executor or subprocess with cwd = workspace_root
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
                output=out_str,
                error=err_str if not success else None,
                metadata={"returncode": process.returncode}
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Command timed out after {timeout} seconds")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
