from enum import Enum
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict
import uuid


class EventType(str, Enum):
    # Mission events
    MISSION_CREATED = "mission.created"
    MISSION_STARTED = "mission.started"
    MISSION_STATUS_CHANGED = "mission.status_changed"
    MISSION_PAUSED = "mission.paused"
    MISSION_RESUMED = "mission.resumed"
    MISSION_COMPLETED = "mission.completed"
    MISSION_FAILED = "mission.failed"

    # Task events
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_STATUS_CHANGED = "task.status_changed"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"

    # Agent events
    AGENT_STARTED = "agent.started"
    AGENT_ACTION = "agent.action"
    AGENT_PAUSED = "agent.paused"
    AGENT_RESUMED = "agent.resumed"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    # Tool events (supporting both tool.call/result and tool.called/completed/failed)
    TOOL_CALL = "tool.call"
    TOOL_CALLED = "tool.called"
    TOOL_RESULT = "tool.result"
    TOOL_COMPLETED = "tool.completed"
    TOOL_ERROR = "tool.error"
    TOOL_FAILED = "tool.failed"

    # Test execution events
    TEST_STARTED = "test.started"
    TEST_RESULT = "test.result"
    TEST_COMPLETED = "test.completed"
    TEST_FAILED = "test.failed"

    # Safety & Danger
    DANGER_DETECTED = "danger.detected"

    # Supervisor events
    SUPERVISOR_ALERT = "supervisor.alert"
    SUPERVISOR_ANOMALY_DETECTED = "supervisor.anomaly_detected"
    SUPERVISOR_REASONING_STARTED = "supervisor.reasoning_started"
    SUPERVISOR_REASONING_COMPLETED = "supervisor.reasoning_completed"
    SUPERVISOR_DECISION = "supervisor.decision"
    SUPERVISOR_INTERVENTION = "supervisor.intervention"

    # Human-in-the-loop approvals
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"

    # Recovery events
    RECOVERY_STARTED = "recovery.started"
    RECOVERY_CONTEXT_CREATED = "recovery.context_created"
    RECOVERY_STRATEGY_REPEATED = "recovery.strategy_repeated"

    # Verification events
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_RESULT = "verification.result"
    VERIFICATION_FAILED = "verification.failed"

    # Project Memory events
    MEMORY_UPDATED = "memory.updated"

    # Control Plane & Multi-Agent Coordination
    TASK_REOPENED = "task.reopened"
    FILE_CONTENTION_DETECTED = "supervisor.file_contention_detected"
    OPERATOR_TAKE_CONTROL = "operator.take_control"


class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


def generate_event_id(prefix: str = "evt") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Event(BaseModel):
    event_id: str = Field(default_factory=generate_event_id)
    mission_id: str
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    type: EventType
    severity: EventSeverity = EventSeverity.INFO
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


# Typed event helpers for easy creation
class ToolCallPayload(BaseModel):
    tool: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    target: Optional[str] = None


class ToolResultPayload(BaseModel):
    tool: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    target: Optional[str] = None


class TestResultPayload(BaseModel):
    command: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    error_signature: Optional[str] = None
    details: Optional[str] = None


class SupervisorAlertPayload(BaseModel):
    rule_name: str
    description: str
    anomaly_type: str  # e.g., "LOOP_DETECTED", "SCOPE_VIOLATION", "NO_PROGRESS", "DANGEROUS_ACTION"
    evidence: Dict[str, Any] = Field(default_factory=dict)


class SupervisorDecisionPayload(BaseModel):
    decision: str  # e.g., "CONTINUE", "RETRY", "CHANGE_STRATEGY", "DELEGATE", "ROLLBACK", "PAUSE", "REQUEST_APPROVAL", "COMPLETE"
    severity: str
    confidence: float
    reason: str
    recommended_action: Optional[str] = None
    target_agent: Optional[str] = None
    model_source: str = "rule_engine"  # e.g. "nemotron-4-340b" or "rule_engine"
