from enum import Enum
from typing import Optional
from supervisor.decisions import SupervisorAction


class SupervisorState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    INVESTIGATING = "INVESTIGATING"
    RECOVERING = "RECOVERING"
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

    def set_state(self, new_state: SupervisorState) -> SupervisorState:
        """Explicit state override."""
        self._state = new_state
        return self._state

    def transition(self, action: SupervisorAction, anomaly_type: Optional[str] = None) -> SupervisorState:
        """Calculate state transition based on current state and supervisor action."""
        if action == SupervisorAction.CONTINUE:
            if self._state == SupervisorState.RECOVERING:
                self._state = SupervisorState.RUNNING
            elif self._state in (SupervisorState.IDLE, SupervisorState.RUNNING, SupervisorState.RETRYING):
                self._state = SupervisorState.RUNNING
        elif action == SupervisorAction.RETRY:
            self._state = SupervisorState.RETRYING
        elif action == SupervisorAction.DELEGATE:
            self._state = SupervisorState.INVESTIGATING
        elif action == SupervisorAction.CHANGE_STRATEGY:
            self._state = SupervisorState.RECOVERING
        elif action == SupervisorAction.REQUEST_APPROVAL:
            self._state = SupervisorState.AWAITING_APPROVAL
        elif action == SupervisorAction.PAUSE:
            self._state = SupervisorState.PAUSED
        elif action == SupervisorAction.COMPLETE:
            self._state = SupervisorState.COMPLETED
        elif action == SupervisorAction.ROLLBACK:
            self._state = SupervisorState.INVESTIGATING
        elif action == SupervisorAction.FAIL:
            self._state = SupervisorState.FAILED

        return self._state

    def reset(self) -> None:
        self._state = SupervisorState.IDLE
