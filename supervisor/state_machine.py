from enum import Enum
from typing import Optional
from supervisor.decisions import SupervisorAction


class SupervisorState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    INVESTIGATING = "INVESTIGATING"
    PAUSED = "PAUSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SupervisorStateMachine:
    """Explicit state machine governing the Supervisor lifecycle."""

    def __init__(self):
        self._state: SupervisorState = SupervisorState.IDLE

    @property
    def current_state(self) -> SupervisorState:
        return self._state

    def transition(self, action: SupervisorAction, anomaly_type: Optional[str] = None) -> SupervisorState:
        """Calculate state transition based on current state and supervisor action."""
        if action == SupervisorAction.CONTINUE:
            self._state = SupervisorState.RUNNING
        elif action == SupervisorAction.RETRY:
            self._state = SupervisorState.RETRYING
        elif action == SupervisorAction.DELEGATE:
            self._state = SupervisorState.INVESTIGATING
        elif action == SupervisorAction.CHANGE_STRATEGY:
            self._state = SupervisorState.RUNNING
        elif action == SupervisorAction.REQUEST_APPROVAL:
            self._state = SupervisorState.AWAITING_APPROVAL
        elif action == SupervisorAction.PAUSE:
            self._state = SupervisorState.PAUSED
        elif action == SupervisorAction.COMPLETE:
            self._state = SupervisorState.COMPLETED
        elif action == SupervisorAction.ROLLBACK:
            self._state = SupervisorState.INVESTIGATING

        return self._state

    def reset(self) -> None:
        self._state = SupervisorState.IDLE
