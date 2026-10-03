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
    """Abstract base class for all agent sandbox tools with strict jail enforcement."""

    name: str
    description: str

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()

    def resolve_path(self, relative_path: str) -> Path:
        """
        Enforce strict workspace sandbox jail.
        Rejects:
        - Path traversal ('..')
        - Symlink escapes
        - Absolute paths outside workspace
        Raises PermissionError if target is outside workspace root.
        """
        # Reject explicit upward traversal tokens
        cleaned_path = relative_path.replace("\\", "/")
        if ".." in cleaned_path.split("/"):
            raise PermissionError(f"Access denied: path traversal token '..' detected in '{relative_path}'.")

        target = Path(relative_path)
        if target.is_absolute():
            resolved = target.resolve()
        else:
            resolved = (self.workspace_root / target).resolve()

        # Check real path to defeat symlink escapes
        real_target = Path(os.path.realpath(str(resolved)))
        real_workspace = Path(os.path.realpath(str(self.workspace_root)))

        try:
            real_target.relative_to(real_workspace)
        except ValueError:
            raise PermissionError(f"Access denied: path '{relative_path}' resolves outside workspace sandbox jail ({self.workspace_root}).")

        return resolved

    @staticmethod
    def sanitize_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Strip sensitive secrets or env vars from tool argument payloads."""
        import re
        sanitized = {}
        sensitive_keywords = {"key", "secret", "token", "password", "auth", "credential", "bearer", "api_key", "access_token", "private_key"}
        secret_patterns = [
            (re.compile(r"ghp_[A-Za-z0-9_]{10,}", re.IGNORECASE), "[REDACTED]"),
            (re.compile(r"sk-[A-Za-z0-9_]{10,}", re.IGNORECASE), "[REDACTED]"),
            (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{10,}", re.IGNORECASE), "Bearer [REDACTED]"),
            (re.compile(r"(password\s*[:=]\s*)([^\s;]+)", re.IGNORECASE), r"\1[REDACTED]"),
            (re.compile(r"(secret\s*[:=]\s*)([^\s;]+)", re.IGNORECASE), r"\1[REDACTED]"),
            (re.compile(r"(api[_-]?key\s*[:=]\s*)([^\s;]+)", re.IGNORECASE), r"\1[REDACTED]"),
        ]
        for k, v in arguments.items():
            if any(s in k.lower() for s in sensitive_keywords):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, str):
                val = v
                for pattern, repl in secret_patterns:
                    val = pattern.sub(repl, val)
                if len(val) > 500:
                    sanitized[k] = val[:500] + "... [TRUNCATED]"
                else:
                    sanitized[k] = val
            elif isinstance(v, dict):
                sanitized[k] = BaseTool.sanitize_arguments(v)
            else:
                sanitized[k] = v
        return sanitized

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool inside the sandbox."""
        pass
