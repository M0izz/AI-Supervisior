from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class WorkerState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    PAUSED = "PAUSED"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkerAction(BaseModel):
    action: str  # tool name or "finish_task"
    arguments: Dict[str, Any] = Field(default_factory=dict)
    thought_summary: str  # Short operational rationale, never hidden chain-of-thought
