from enum import Enum


class ProtocolEventType(str, Enum):
    """
    Standard Work Protocol v1 Event Types.
    Defines typed event representations for the core lifecycle across
    all local and external agents.
    """
    # Mission lifecycle
    MISSION_CREATED = "mission.created"
    MISSION_COMPLETED = "mission.completed"
    MISSION_FAILED = "mission.failed"

    # Task lifecycle
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"

    # Agent connection and execution lifecycle
    AGENT_CONNECTED = "agent.connected"
    AGENT_DISCONNECTED = "agent.disconnected"
    AGENT_STARTED = "agent.started"
    AGENT_PAUSED = "agent.paused"
    AGENT_RESUMED = "agent.resumed"
    AGENT_STOPPED = "agent.stopped"

    # Agent actions and tools
    AGENT_ACTION_EXECUTED = "agent.action.executed"
    AGENT_TOOL_CALLED = "agent.tool_called"

    # Filesystem operations
    FILE_CHANGED = "file.changed"

    # Command execution
    COMMAND_STARTED = "command.started"
    COMMAND_COMPLETED = "command.completed"

    # Testing lifecycle
    TEST_STARTED = "test.started"
    TEST_PASSED = "test.passed"
    TEST_FAILED = "test.failed"

    # Supervisor interventions & handoffs
    SUPERVISOR_INTERVENED = "supervisor.intervened"
    HANDOFF_CREATED = "handoff.created"

    # Recovery lifecycle
    RECOVERY_STARTED = "recovery.started"
    RECOVERY_COMPLETED = "recovery.completed"

    # Verification lifecycle
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_PASSED = "verification.passed"
    VERIFICATION_FAILED = "verification.failed"
    VERIFICATION_COMPLETED = "verification.completed"
    VERIFICATION_CHECK_COMPLETED = "verification.check.completed"


    # Human-in-the-loop approvals
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"

    @classmethod
    def is_valid_type(cls, value: str) -> bool:
        return any(item.value == value for item in cls)
