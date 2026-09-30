import os
from pathlib import Path
from typing import List, Optional
from tools.base import BaseTool, ToolResult


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file within the workspace."

    async def execute(self, path: str) -> ToolResult:
        try:
            target = self.resolve_path(path)
            if not target.exists():
                return ToolResult(success=False, error=f"File not found: {path}")
            content = target.read_text(encoding="utf-8")
            return ToolResult(success=True, output=content, metadata={"bytes": len(content)})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Create or overwrite a file within the workspace."

    async def execute(self, path: str, content: str) -> ToolResult:
        try:
            target = self.resolve_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolResult(success=True, output=f"Successfully wrote {len(content)} characters to {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class EditFileTool(BaseTool):
    name = "edit_file"
    description = "Replace specific lines or chunks in a file within the workspace."

    async def execute(self, path: str, target_content: str, replacement_content: str) -> ToolResult:
        try:
            target = self.resolve_path(path)
            if not target.exists():
                return ToolResult(success=False, error=f"File not found: {path}")
            current = target.read_text(encoding="utf-8")
            if target_content not in current:
                return ToolResult(success=False, error="Target content block not found in file.")
            updated = current.replace(target_content, replacement_content, 1)
            target.write_text(updated, encoding="utf-8")
            return ToolResult(success=True, output=f"Successfully edited {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files and directories in the workspace."

    async def execute(self, path: str = ".") -> ToolResult:
        try:
            target = self.resolve_path(path)
            if not target.exists():
                return ToolResult(success=False, error=f"Path not found: {path}")
            items = []
            for root, dirs, files in os.walk(target):
                rel_root = Path(root).relative_to(self.workspace_root)
                for f in files:
                    items.append(str(rel_root / f).replace("\\", "/"))
            return ToolResult(success=True, output="\n".join(items), metadata={"count": len(items)})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
