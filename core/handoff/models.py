from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field, ConfigDict


class HandoffStatus(str, Enum):
    """Lifecycle status of a task handoff operation."""
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    PREPARING = "PREPARING"
    TRANSFERRED = "TRANSFERRED"
    ACCEPTED = "ACCEPTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class HandoffTrigger(str, Enum):
    """Deterministic triggers initiating a task handoff."""
    REPEATED_FAILURE = "REPEATED_FAILURE"        # Trigger A: Watchdog loop detection
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"  # Trigger B: Verifier rejected completion claim
    AGENT_FAILURE = "AGENT_FAILURE"              # Trigger C: Agent crash / unavailable / error
    MANUAL = "MANUAL"                            # Operator requested handoff


class FactProvenance(str, Enum):
    """Classification of context fact reliability."""
    VERIFIED = "VERIFIED"        # Empirically proven by verifier or deterministic rule
    UNVERIFIED = "UNVERIFIED"    # Claimed by worker agent without empirical proof
    REJECTED = "REJECTED"        # Explicitly disproved by verification or watchdog


class ContextFact(BaseModel):
    """
    Fine-grained item of context transferred during a handoff.
    Preserves exact provenance so receiving agents know what is proven vs claimed.
    """
    fact_id: str = Field(default_factory=lambda: f"fct_{uuid.uuid4().hex[:8]}")
    statement: str = Field(..., description="Fact or observation statement")
    provenance: FactProvenance = Field(..., description="Reliability classification")
    source: str = Field(..., description="Attribution source (e.g. verification_id, event_id, watchdog)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class HandoffContextPackage(BaseModel):
    """
    Standardized, bounded context package transferred from source agent to target agent.
    Separates verified facts from unverified claims and known rejected attempts.
    """
    task_id: str = Field(..., description="Task identifier")
    mission_id: str = Field(..., description="Mission identifier")
    objective: str = Field(..., description="Task goal and requirements")
    task_description: str = Field(default="", description="Task description and background")
    allowed_scope: List[str] = Field(default_factory=list, description="Authorized file patterns")
    workspace: str = Field(..., description="Path to the isolated task Git worktree")
    source_agent_id: str = Field(..., description="Source agent giving up task")
    target_agent_id: str = Field(..., description="Target agent receiving task")
    trigger: HandoffTrigger = Field(..., description="Trigger reason for handoff")
    failure_reason: str = Field(default="", description="Detailed failure diagnosis")
    failure_signature: Optional[str] = Field(default=None, description="Normalized error signature if applicable")
    consecutive_failures: int = Field(default=0, description="Count of identical failures")
    
    # Provenance-separated context items
    verified_facts: List[ContextFact] = Field(default_factory=list, description="Empirically verified truths")
    unverified_claims: List[ContextFact] = Field(default_factory=list, description="Claims made by source agent without proof")
    rejected_attempts: List[ContextFact] = Field(default_factory=list, description="Strategies proven to fail")
    
    changed_files: List[str] = Field(default_factory=list, description="Files modified in the worktree")
    executed_commands: List[str] = Field(default_factory=list, description="Commands run by source agent")
    watchdog_evidence: Dict[str, Any] = Field(default_factory=dict, description="Watchdog anomaly reports")
    verification_evidence: Dict[str, Any] = Field(default_factory=dict, description="Independent verification results")
    remaining_work: str = Field(default="", description="Summary of work still required")
    handoff_history: List[Dict[str, Any]] = Field(default_factory=list, description="Prior handoffs for this task")
    handoff_count: int = Field(default=1, description="Sequential handoff index for this task")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class HandoffRecord(BaseModel):
    """Durable record of a handoff persisted to SQLite."""
    handoff_id: str = Field(default_factory=lambda: f"hnd_{uuid.uuid4().hex[:12]}")
    mission_id: str
    task_id: str
    source_agent_id: str
    target_agent_id: str
    trigger: HandoffTrigger
    status: HandoffStatus = HandoffStatus.REQUESTED
    reason: str = ""
    context_package: Optional[HandoffContextPackage] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    transferred_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class HandoffResult(BaseModel):
    """Outcome of a handoff dispatch operation."""
    handoff_id: str
    task_id: str
    success: bool
    status: HandoffStatus
    source_agent_id: str
    target_agent_id: str
    context_package: Optional[HandoffContextPackage] = None
    verification_result: Optional[Any] = None
    error: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
