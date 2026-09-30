from pathlib import Path
from typing import Dict
from tools.base import BaseTool, ToolResult
from tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListFilesTool
from tools.shell import RunCommandTool
from tools.testing import RunTestsTool
from tools.git import GitStatusTool, GitDiffTool


def get_default_tools(workspace_root: Path) -> Dict[str, BaseTool]:
    """Factory creating all 8 sandboxed tools for an agent."""
    tools = [
        ReadFileTool(workspace_root),
        WriteFileTool(workspace_root),
        EditFileTool(workspace_root),
        ListFilesTool(workspace_root),
        RunCommandTool(workspace_root),
        RunTestsTool(workspace_root),
        GitStatusTool(workspace_root),
        GitDiffTool(workspace_root),
    ]
    return {t.name: t for t in tools}


__all__ = [
    "BaseTool",
    "ToolResult",
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ListFilesTool",
    "RunCommandTool",
    "RunTestsTool",
    "GitStatusTool",
    "GitDiffTool",
    "get_default_tools",
]
