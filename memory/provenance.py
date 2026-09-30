from enum import Enum
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import uuid


class FactStatus(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    DECIDED = "DECIDED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    STALE = "STALE"


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:8]}")
    mission_id: str
    fact: str
    source: str       # e.g., "test_482", "verifier_01", "reviewer_01", "operator"
    created_by: str   # agent or role
    confidence: float = 1.0
    status: FactStatus = FactStatus.OBSERVED
    category: str = "fact"  # fact, decision, rejected_approach, known_issue
    details: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
