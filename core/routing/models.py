from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field, ConfigDict

from adapters.models import AdapterCapability, AdapterAvailabilityStatus


class RoutingDecisionType(str, Enum):
    """Possible outcomes of an agent routing evaluation."""
    ROUTE = "ROUTE"                          # At least one eligible agent found and selected
    NO_ELIGIBLE_AGENT = "NO_ELIGIBLE_AGENT"  # No available candidate satisfies required capabilities
    REQUIRE_REVIEW = "REQUIRE_REVIEW"        # Ambiguous requirements or conflicting constraints requiring operator review


class TaskRequirements(BaseModel):
    """
    Structured execution requirements for a task used by the Router.
    Enforces deterministic capability matching without relying on LLM classification.
    """
    task_type: str = Field(default="code_change", description="Task classification category")
    required_capabilities: List[str] = Field(
        default_factory=list,
        description="Mandatory capabilities; missing any disqualifies a candidate"
    )
    preferred_capabilities: List[str] = Field(
        default_factory=list,
        description="Desirable capabilities that boost routing score but do not disqualify"
    )
    excluded_agent_ids: List[str] = Field(
        default_factory=list,
        description="Agents barred from consideration (e.g. source agent during handoff)"
    )
    constraints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Explicit constraints or policy parameters for this task"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def from_task(
        cls,
        task: Any,
        required_capabilities: Optional[List[str]] = None,
        preferred_capabilities: Optional[List[str]] = None,
        excluded_agent_ids: Optional[List[str]] = None,
    ) -> "TaskRequirements":
        """
        Extracts structured task requirements from a Task instance or its metadata.
        Falls back to standard software engineering capabilities if unspecified.
        """
        metadata = getattr(task, "metadata", {}) or {}
        reqs = required_capabilities or metadata.get("required_capabilities")
        if reqs is None:
            # Deterministic default requirements for code tasks
            reqs = [
                AdapterCapability.CODE_EXECUTION.value,
                AdapterCapability.FILESYSTEM_WRITE.value,
                AdapterCapability.GIT.value,
                AdapterCapability.TEST_EXECUTION.value,
            ]

        prefs = preferred_capabilities or metadata.get("preferred_capabilities") or []
        excl = excluded_agent_ids or metadata.get("excluded_agent_ids") or []
        task_type = getattr(task, "task_type", None) or metadata.get("task_type") or "code_change"

        return cls(
            task_type=task_type,
            required_capabilities=[str(c) for c in reqs],
            preferred_capabilities=[str(c) for c in prefs],
            excluded_agent_ids=[str(a) for a in excl],
            constraints=metadata.get("constraints") or {},
        )


class RoutingCandidate(BaseModel):
    """
    Evaluation record for a specific agent adapter considered for a task.
    Transparently details capability matching, availability, and score components.
    """
    agent_id: str
    adapter_id: str
    capabilities: List[str] = Field(default_factory=list)
    availability: str = AdapterAvailabilityStatus.UNAVAILABLE.value
    is_available: bool = False
    is_eligible: bool = False
    ineligibility_reasons: List[str] = Field(default_factory=list)
    score: float = 0.0
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    historical_metrics: Dict[str, Any] = Field(default_factory=dict)
    evaluation_summary: str = ""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class RoutingRequest(BaseModel):
    """Input payload sent to the Router to select the best worker agent."""
    routing_id: str = Field(default_factory=lambda: f"rtg_{uuid.uuid4().hex[:12]}")
    mission_id: str
    task_id: str
    task_objective: str = ""
    task_requirements: TaskRequirements
    candidate_agent_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional explicit subset of agents to consider; defaults to all registered"
    )
    context: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class RoutingDecision(BaseModel):
    """
    Authoritative routing choice emitted by the Supervisor's RoutingEngine.
    Explains why an agent was selected or why no eligible agent could be found.
    """
    routing_id: str
    mission_id: str
    task_id: str
    decision: RoutingDecisionType
    selected_agent_id: Optional[str] = None
    selected_adapter_id: Optional[str] = None
    score: float = 0.0
    decision_reason: str = ""
    candidates: List[RoutingCandidate] = Field(default_factory=list)
    requirements: Optional[TaskRequirements] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)
