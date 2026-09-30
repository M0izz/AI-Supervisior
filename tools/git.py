import asyncio
from pathlib import Path
from tools.base import BaseTool, ToolResult


class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Inspect repository git status to check modified, untracked, and staged files."

    async def execute(self) -> ToolResult:
        try:
            process = await asyncio.create_subprocess_shell(
                "git status --porcelain",
                cwd=str(self.workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
            out_str = stdout.decode("utf-8", errors="replace").strip()
            modified_files = [line[3:].strip() for line in out_str.split("\n") if line.strip()]

            return ToolResult(
                success=True,
                output=out_str,
                metadata={"modified_files": modified_files, "count": len(modified_files)}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "Inspect working tree diff to verify scope and modifications."

    async def execute(self, path: str = "") -> ToolResult:
        try:
            cmd = f"git diff {path}" if path else "git diff"
            process = await asyncio.create_subprocess_shell(
                cmd,
                cwd=str(self.workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
            out_str = stdout.decode("utf-8", errors="replace")
            return ToolResult(success=True, output=out_str, metadata={"diff_lines": len(out_str.splitlines())})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
