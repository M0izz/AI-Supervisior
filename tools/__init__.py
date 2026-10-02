from pathlib import Path
from typing import Dict
from tools.base import BaseTool, ToolResult
from tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListFilesTool
from tools.shell import RunCommandTool
from tools.testing import RunTestsTool
from tools.git import GitStatusTool, GitDiffTool


from typing import Dict, Optional
from execution.manager import ExecutionManager


def get_default_tools(
    workspace_root: Path,
    execution_manager: Optional[ExecutionManager] = None
) -> Dict[str, BaseTool]:
    """Factory creating all 8 sandboxed tools for an agent."""
    exec_mgr = execution_manager or ExecutionManager()
    tools = [
        ReadFileTool(workspace_root),
        WriteFileTool(workspace_root),
        EditFileTool(workspace_root),
        ListFilesTool(workspace_root),
        RunCommandTool(workspace_root, execution_manager=exec_mgr),
        RunTestsTool(workspace_root, execution_manager=exec_mgr),
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
