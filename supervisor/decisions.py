from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class SupervisorAction(str, Enum):
    CONTINUE = "CONTINUE"
    RETRY = "RETRY"
    CHANGE_STRATEGY = "CHANGE_STRATEGY"
    DELEGATE = "DELEGATE"
    ROLLBACK = "ROLLBACK"
    PAUSE = "PAUSE"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    COMPLETE = "COMPLETE"


class SupervisorDecision(BaseModel):
    action: SupervisorAction
    severity: str = "medium"  # low, medium, high, critical
    confidence: float = 1.0   # 0.0 to 1.0
    reason: str
    target_agent: Optional[str] = None
    recommended_strategy: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source: str = "rule_engine"  # "rule_engine" | "nemotron-4-340b"
