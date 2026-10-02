from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    BLOCKED = "BLOCKED"
    FALLBACK = "FALLBACK"


class ContainerInfo(BaseModel):
    container_id: Optional[str] = None
    image: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    network_disabled: bool = True
    read_only_root: bool = False
    cpu_limit: Optional[float] = None
    memory_limit: Optional[str] = None
    pids_limit: Optional[int] = None


class ExecutionRequest(BaseModel):
    command: str
    workspace_root: Union[Path, str]
    timeout_seconds: float = 30.0
    env: Dict[str, str] = Field(default_factory=dict)
    mission_id: Optional[str] = None
    task_id: Optional[str] = None
    agent_id: Optional[str] = None

    def get_workspace_path(self) -> Path:
        return Path(self.workspace_root).resolve()


class ExecutionResult(BaseModel):
    status: ExecutionStatus
    exit_code: int = 0
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    duration_ms: float = 0.0
    container: Optional[ContainerInfo] = None
    backend: str = "local"
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS and self.exit_code == 0
