from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from core.protocol.events import ProtocolEventType
from core.protocol.actions import ActionInfo, TelemetryInfo


CURRENT_SCHEMA_VERSION = "1.0.0"


def default_event_id(prefix: str = "evt") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def default_dispatch_id(prefix: str = "dsp") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class WorkProtocolEvent(BaseModel):
    """
    Work Protocol v1 Unified Event Model.
    Provides standard event envelope and telemetry identity across all agent runtimes.
    """
    schema_version: str = Field(default=CURRENT_SCHEMA_VERSION, description="Protocol schema version")
    event_id: str = Field(default_factory=default_event_id, description="Unique identifier for this event")
    mission_id: str = Field(..., description="Mission context identifier")
    task_id: Optional[str] = Field(default=None, description="Task context identifier if applicable")
    agent_id: Optional[str] = Field(default=None, description="Originating agent identifier if applicable")
    provider: str = Field(default="internal", description="Agent runtime or model provider (internal, claude, codex, gemini, etc.)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of the event")
    event_type: str = Field(..., description="Typed lifecycle event type")
    
    # Structured execution payloads
    action: Optional[ActionInfo] = Field(default=None, description="Structured action information if applicable")
    telemetry: Optional[TelemetryInfo] = Field(default=None, description="Execution metrics, tokens, and duration if available")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Flexible validated payload metadata")

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    @property
    def id(self) -> str:
        return self.event_id


class TaskDispatchPackage(BaseModel):
    """
    Stable typed structure for dispatching work to an agent.
    Acts as the isolation boundary between the Supervisor and any AgentAdapter.
    """
    schema_version: str = Field(default=CURRENT_SCHEMA_VERSION, description="Dispatch specification version")
    dispatch_id: str = Field(default_factory=default_dispatch_id, description="Unique identifier for this dispatch package")
    task_id: str = Field(..., description="Target task identifier")
    mission_id: str = Field(..., description="Associated mission identifier")
    objective: str = Field(..., description="Clear, verifiable prompt or objective for the agent")
    dependencies: List[str] = Field(default_factory=list, description="IDs of prerequisite tasks that have completed")
    workspace: str = Field(..., description="Absolute or relative path to the isolated task workspace/worktree")
    allowed_files: List[str] = Field(default_factory=list, description="Explicit whitelist of files or glob patterns within scope")
    permissions: Dict[str, Any] = Field(
        default_factory=lambda: {
            "read_filesystem": True,
            "write_filesystem": True,
            "execute_terminal": True,
            "allow_network": False,
        },
        description="Fine-grained execution capabilities granted to the agent"
    )
    budget: Optional[Dict[str, float]] = Field(
        default=None,
        description="Optional resource caps: {'max_tokens': 100000, 'max_cost_usd': 2.0, 'max_iterations': 15}"
    )
    timeout: Optional[float] = Field(
        default=300.0,
        ge=1.0,
        description="Maximum execution timeout in seconds"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Contextual artifacts, instructions, repository memory snippets, and previous step summaries"
    )
    verification_requirements: List[str] = Field(
        default_factory=list,
        description="List of verification commands or assertions required before task completion can be accepted"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
