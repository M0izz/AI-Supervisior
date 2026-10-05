"""
Domain models for Phase 9: Absence Mode.

Core Invariants:
- "Absence Mode expands continuity, not authority."
- Policy snapshots are immutable once armed/activated.
- Conservative defaults: strict limits on duration, retries, tasks, and commands.
"""

from enum import Enum
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
import uuid


class AbsenceSessionState(str, Enum):
    DISABLED = "DISABLED"
    ARMED = "ARMED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    EXPIRED = "EXPIRED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class ApprovalPolicy(str, Enum):
    ALWAYS_ASK = "ALWAYS_ASK"
    ASK_IF_UNSAFE = "ASK_IF_UNSAFE"
    AUTO_APPROVE_WITHIN_POLICY = "AUTO_APPROVE_WITHIN_POLICY"
    NEVER_ALLOW = "NEVER_ALLOW"


class VerificationPolicy(str, Enum):
    STRICT = "STRICT"  # Verification is ALWAYS mandatory; zero bypass


class FailurePolicy(str, Enum):
    PAUSE_AND_NOTIFY = "PAUSE_AND_NOTIFY"
    SAFE_STOP = "SAFE_STOP"


class AbsenceDecisionType(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    PAUSE = "PAUSE"
    REQUIRE_USER = "REQUIRE_USER"


DEFAULT_DANGEROUS_COMMANDS = [
    "rm -rf", "drop table", "drop database", "format ", "mkfs",
    "dd if=", "chmod 777", "chmod -R 777", "kill -9", "shutdown",
    ":(){ :|:& };:"
]

DEFAULT_PROTECTED_PATHS = [
    ".git", ".env", "secrets", "database/migrations", "migrations/", "schema.sql"
]


class AbsencePolicy(BaseModel):
    """
    Explicit, structured authority policy for unattended execution.
    Once assigned to an AbsenceSession, this policy is treated as an immutable snapshot.
    """
    enabled: bool = True
    max_duration_seconds: int = Field(default=7200, description="Max session duration in seconds (default: 2h)")
    max_tasks: int = Field(default=5, description="Max completed tasks allowed in this session")
    max_handoffs: int = Field(default=2, description="Max cross-agent handoffs allowed in this session")
    max_retries: int = Field(default=3, description="Max consecutive task retries before pausing")
    max_budget: float = Field(default=10.0, description="Max measurable cost / budget ceiling")
    max_execution_time_seconds: int = Field(default=3600, description="Max cumulative process runtime")

    allowed_capabilities: List[str] = Field(
        default_factory=lambda: ["file_read", "file_write", "test_execution", "git_worktree"]
    )
    allowed_paths: List[str] = Field(default_factory=lambda: ["*"])
    prohibited_paths: List[str] = Field(default_factory=lambda: list(DEFAULT_PROTECTED_PATHS))
    allowed_actions: List[str] = Field(
        default_factory=lambda: ["read_file", "write_file", "run_test", "git_commit", "git_diff"]
    )
    prohibited_commands: List[str] = Field(default_factory=lambda: list(DEFAULT_DANGEROUS_COMMANDS))

    approval_policy: ApprovalPolicy = ApprovalPolicy.AUTO_APPROVE_WITHIN_POLICY
    verification_policy: VerificationPolicy = VerificationPolicy.STRICT
    failure_policy: FailurePolicy = FailurePolicy.PAUSE_AND_NOTIFY
    notification_policy: str = "ACTIONABLE_ONLY"
    version: str = "1.0.0"

    @field_validator("max_duration_seconds")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("max_duration_seconds must be positive")
        if v > 86400:  # 24 hours ceiling
            raise ValueError("max_duration_seconds cannot exceed 86400 (24 hours)")
        return v

    @field_validator("max_retries")
    @classmethod
    def validate_retries(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_retries must be at least 1")
        if v > 10:
            raise ValueError("max_retries cannot exceed 10")
        return v

    @field_validator("max_handoffs")
    @classmethod
    def validate_handoffs(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_handoffs cannot be negative")
        if v > 5:
            raise ValueError("max_handoffs cannot exceed 5")
        return v

    def is_command_prohibited(self, command: str) -> bool:
        cmd_lower = command.lower()
        return any(p.lower() in cmd_lower for p in self.prohibited_commands)

    def is_path_prohibited(self, path: str) -> bool:
        norm = path.replace("\\", "/").lower()
        return any(p.lower() in norm for p in self.prohibited_paths)


class AbsenceSession(BaseModel):
    """
    Persistent Absence Mode session representation.
    Holds the authoritative snapshot of the user-authorized policy.
    """
    absence_id: str = Field(default_factory=lambda: f"abs_{uuid.uuid4().hex[:12]}")
    mission_id: str
    status: AbsenceSessionState = AbsenceSessionState.ARMED
    policy: AbsencePolicy
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_by: str = "user"
    tasks_completed: int = 0
    retries_count: int = 0
    handoffs_count: int = 0
    paused_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if not self.expires_at:
            return False
        current_time = now or datetime.now(timezone.utc)
        return current_time >= self.expires_at

    def remaining_seconds(self, now: Optional[datetime] = None) -> float:
        if not self.expires_at:
            return float(self.policy.max_duration_seconds)
        current_time = now or datetime.now(timezone.utc)
        delta = (self.expires_at - current_time).total_seconds()
        return max(0.0, delta)


class AbsenceDecision(BaseModel):
    """
    Auditable autonomous decision record.
    """
    decision_id: str = Field(default_factory=lambda: f"dec_{uuid.uuid4().hex[:12]}")
    absence_id: str
    mission_id: str
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    decision: AbsenceDecisionType
    rule_id: str
    reason: str
    action: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
