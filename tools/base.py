import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    """Abstract base class for all agent sandbox tools."""

    name: str
    description: str

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def resolve_path(self, relative_path: str) -> Path:
        """
        Enforce strict workspace sandbox jail.
        Raises PermissionError if target is outside workspace root.
        """
        resolved = (self.workspace_root / relative_path).resolve()
        if not str(resolved).startswith(str(self.workspace_root)):
            raise PermissionError(f"Access denied: path '{relative_path}' escapes workspace jail.")
        return resolved

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool inside the sandbox."""
        pass
