from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


class MissionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    INVESTIGATING = "INVESTIGATING"
    PAUSED = "PAUSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MissionConstraints(BaseModel):
    max_turns: int = 50
    max_budget_usd: float = 10.0
    timeout_seconds: int = 1800
    allowed_tools: List[str] = Field(default_factory=lambda: [
        "read_file", "write_file", "edit_file", "list_files",
        "run_command", "run_tests", "git_diff", "git_status"
    ])
    disallowed_paths: List[str] = Field(default_factory=lambda: [
        ".git", ".env", "secrets", "database/migrations", "package-lock.json"
    ])
    require_approval_for_destructive_commands: bool = True
    require_approval_for_db_changes: bool = True
    max_repeated_failures: int = 3


class MissionMetrics(BaseModel):
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_tool_calls: int = 0
    attempts: int = 0
    failures: int = 0
    interventions_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


def generate_mission_id() -> str:
    return f"msn_{uuid.uuid4().hex[:8]}"


class Mission(BaseModel):
    id: str = Field(default_factory=generate_mission_id)
    title: str
    goal: str
    repository_path: str = "./demo/sample-project"
    status: MissionStatus = MissionStatus.PENDING
    constraints: MissionConstraints = Field(default_factory=MissionConstraints)
    metrics: MissionMetrics = Field(default_factory=MissionMetrics)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active_agent_id: Optional[str] = None
    current_task_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
