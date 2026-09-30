from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: f"appr_{uuid.uuid4().hex[:8]}")
    mission_id: str
    task_id: Optional[str] = None
    agent_id: str
    action_type: str  # e.g., "destructive_command", "scope_violation", "database_migration"
    target: str       # e.g. "rm -rf ./build/cache" or "database/migrations/001.sql"
    reason: str
    risk_level: str = "medium"  # low, medium, high, critical
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    feedback: Optional[str] = None


class AgentContextPackage(BaseModel):
    """
    Curated, structured context provided to an agent for a specific execution step.
    Avoids dumping 40k tokens of unstructured chat history.
    """
    mission_id: str
    objective: str
    task: Dict[str, Any]
    constraints: List[str] = Field(default_factory=list)
    relevant_memory: List[Dict[str, Any]] = Field(default_factory=list)
    rejected_approaches: List[Dict[str, Any]] = Field(default_factory=list)
    recent_events: List[Dict[str, Any]] = Field(default_factory=list)
    previous_attempts: List[Dict[str, Any]] = Field(default_factory=list)
    verification_status: Dict[str, Any] = Field(default_factory=dict)


class SystemSnapshot(BaseModel):
    """Real-time unified state transmitted to the Control Room Dashboard."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mission_id: Optional[str] = None
    mission_status: Optional[str] = None
    mission_title: Optional[str] = None
    progress_percentage: int = 0
    active_agent: Optional[str] = None
    agents_summary: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    supervisor_status: str = "IDLE"  # IDLE, MONITORING, ANOMALY_DETECTED, REASONING, INTERVENING, PAUSED
    active_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    last_decision: Optional[Dict[str, Any]] = None
    recent_activity: List[Dict[str, Any]] = Field(default_factory=list)
    pending_approvals: List[ApprovalRequest] = Field(default_factory=list)
