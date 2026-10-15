from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


class MissionStatus(str, Enum):
    DRAFT = "DRAFT"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    # Backward compatibility aliases
    CREATED = "CREATED"
    PENDING = "PENDING"
    STARTING = "STARTING"
    PAUSED = "PAUSED"
    INVESTIGATING = "INVESTIGATING"
    RECOVERING = "RECOVERING"
    BLOCKED = "BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


class PlanTaskItem(BaseModel):
    task_id: str
    title: str
    description: str = ""
    dependencies: List[str] = Field(default_factory=list)
    proposed_agent: str = "worker_01"
    required_capabilities: List[str] = Field(default_factory=lambda: ["file_editing", "command_execution"])
    expected_files: List[str] = Field(default_factory=list)
    risk_classification: str = "LOW"  # LOW, MEDIUM, HIGH
    acceptance_criteria: List[str] = Field(default_factory=list)
    verification_strategy: str = "automated_test"


class StructuredInterpretation(BaseModel):
    original_request: str
    interpreted_goal: str
    expected_deliverables: List[str] = Field(default_factory=list)
    in_scope: List[str] = Field(default_factory=list)
    explicit_exclusions: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    blocking_questions: List[str] = Field(default_factory=list)
    non_blocking_assumptions: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    definition_of_success: str = ""
    proposed_verification_methods: List[str] = Field(default_factory=list)


class PlanApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PlanVersion(BaseModel):
    plan_id: str = Field(default_factory=lambda: f"pln_{uuid.uuid4().hex[:8]}")
    mission_id: str
    version: int = 1
    interpretation: StructuredInterpretation
    tasks: List[PlanTaskItem] = Field(default_factory=list)
    validation_status: str = "VALID"  # VALID, INVALID, NEEDS_CLARIFICATION
    approval_status: PlanApprovalStatus = PlanApprovalStatus.PENDING
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    execution_started_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    original_request: Optional[str] = None
    repository_path: str = "./demo/sample-project"
    status: MissionStatus = MissionStatus.CREATED
    current_plan_version: int = 0
    approved_plan_version: Optional[int] = None
    constraints: MissionConstraints = Field(default_factory=MissionConstraints)
    metrics: MissionMetrics = Field(default_factory=MissionMetrics)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active_agent_id: Optional[str] = None
    current_task_id: Optional[str] = None
    assigned_agents: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
