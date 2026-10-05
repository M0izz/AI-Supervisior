"""
Shared Project Memory Domain Models (Phase 7).
Defines structured provenance, memory types, status transitions, queries,
and bounded agent context packages.
"""

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, model_validator


# Common sensitive patterns for secret scrubbing (Security Section 23)
SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|token|password|auth|bearer)\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{8,})["\']?'),
    re.compile(r'\b(sk-[a-zA-Z0-9]{20,})\b'),
    re.compile(r'\b(ghp_[a-zA-Z0-9]{20,})\b'),
    re.compile(r'\b(glpat-[a-zA-Z0-9_\-]{20,})\b'),
    re.compile(r'\b(xox[baprs]-[a-zA-Z0-9_\-]{10,})\b'),
]


def sanitize_text(text: str) -> str:
    """Scrub known API keys and credentials from text before memory persistence."""
    if not text:
        return text
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub(r'\1: [REDACTED_SECRET]', sanitized) if 'api' in pattern.pattern else pattern.sub('[REDACTED_SECRET]', sanitized)
    return sanitized


class MemoryStatus(str, Enum):
    """
    Epistemic status of a memory record.
    Invariant: Memory is not automatically truth.
    VERIFIED requires objective independent empirical evidence.
    """
    VERIFIED = "VERIFIED"
    INFERRED = "INFERRED"
    UNVERIFIED = "UNVERIFIED"
    REJECTED = "REJECTED"
    # Backward compatibility states
    OBSERVED = "OBSERVED"
    DECIDED = "DECIDED"
    STALE = "STALE"


# Alias for backward compatibility
FactStatus = MemoryStatus


class MemoryType(str, Enum):
    """Classification of knowledge item."""
    FACT = "FACT"
    DECISION = "DECISION"
    CONSTRAINT = "CONSTRAINT"
    FAILURE = "FAILURE"
    REJECTED_APPROACH = "REJECTED_APPROACH"
    DISCOVERY = "DISCOVERY"
    TASK_CONTEXT = "TASK_CONTEXT"
    VERIFICATION_RESULT = "VERIFICATION_RESULT"


class MemoryProvenance(BaseModel):
    """
    Every memory item must answer: Where did this information come from?
    """
    source: str = Field(
        default="system_observation",
        description="Source type (e.g., 'agent_event', 'watchdog_event', 'verification', 'handoff', 'routing', 'user_input', 'system_observation')"
    )
    source_id: str = Field(
        default="",
        description="Identifier of originating event, verification_id, handoff_id, or task_id"
    )
    created_by: str = Field(
        default="system",
        description="Agent ID, tool, or supervisor component that asserted this fact"
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Objective proof references or test output lines supporting the status"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class MemoryRecord(BaseModel):
    """
    Structured project memory unit stored in SQLite WAL.
    """
    id: str = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:12]}")
    project_id: str = Field(default="", description="Project or repository scope")
    mission_id: str = Field(..., description="Parent mission identifier")
    task_id: Optional[str] = Field(default=None, description="Optional associated task identifier")
    content: str = Field(..., description="The factual proposition, decision, or discovery")
    memory_type: MemoryType = Field(default=MemoryType.FACT, description="Kind of knowledge")
    status: MemoryStatus = Field(default=MemoryStatus.OBSERVED, description="Epistemic verification status")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence level between 0.0 and 1.0")
    provenance: MemoryProvenance = Field(default_factory=MemoryProvenance)
    category: str = Field(default="fact", description="Legacy category tag for UI screens")
    details: Optional[str] = Field(default=None, description="Extended diagnostic or contextual details")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary structured metadata")
    superseded_by: Optional[str] = Field(default=None, description="ID of memory record superseding this one")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Backward compatibility: support 'fact' as alias for 'content'
            if "fact" in data and "content" not in data:
                data["content"] = data["fact"]
            # Backward compatibility: map category to memory_type if memory_type is default
            cat = str(data.get("category", "")).lower()
            if "memory_type" not in data:
                if cat == "decision":
                    data["memory_type"] = MemoryType.DECISION
                elif cat in ("rejected_approach", "rejected"):
                    data["memory_type"] = MemoryType.REJECTED_APPROACH
                elif cat == "constraint":
                    data["memory_type"] = MemoryType.CONSTRAINT
                elif cat == "failure":
                    data["memory_type"] = MemoryType.FAILURE
            # Construct provenance if flat fields provided
            prov_raw = data.get("provenance")
            if prov_raw is None or isinstance(prov_raw, dict):
                prov_dict = prov_raw or {}
                data["provenance"] = {
                    "source": str(prov_dict.get("source", data.get("source", "system_observation"))),
                    "source_id": str(prov_dict.get("source_id", data.get("source_id", ""))),
                    "created_by": str(prov_dict.get("created_by", data.get("created_by", "system"))),
                    "evidence": prov_dict.get("evidence", data.get("evidence", [])) if isinstance(prov_dict.get("evidence", data.get("evidence", [])), list) else [],
                }
            # Auto-sanitize content and details
            if "content" in data and isinstance(data["content"], str):
                data["content"] = sanitize_text(data["content"])
            if "details" in data and isinstance(data["details"], str):
                data["details"] = sanitize_text(data["details"])
        return data

    @property
    def fact(self) -> str:
        """Backward-compatibility property returning content."""
        return self.content

    @property
    def source(self) -> str:
        """Backward-compatibility property returning provenance source."""
        return self.provenance.source

    @property
    def created_by(self) -> str:
        """Backward-compatibility property returning provenance created_by."""
        return self.provenance.created_by


class MemoryQuery(BaseModel):
    """
    Deterministic retrieval query for scoped project memories.
    """
    project_id: Optional[str] = None
    mission_id: Optional[str] = None
    task_id: Optional[str] = None
    memory_types: Optional[List[MemoryType]] = None
    statuses: Optional[List[MemoryStatus]] = None
    keywords: Optional[List[str]] = None
    sources: Optional[List[str]] = None
    exclude_superseded: bool = True
    limit: int = 50

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ProjectMemoryContext(BaseModel):
    """
    Bounded, deterministic memory package passed to an agent during task start or handoff.
    """
    project_id: str = ""
    mission_id: str = ""
    task_id: Optional[str] = None
    relevant_facts: List[Dict[str, Any]] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    recent_decisions: List[Dict[str, Any]] = Field(default_factory=list)
    rejected_approaches: List[Dict[str, Any]] = Field(default_factory=list)
    relevant_failures: List[Dict[str, Any]] = Field(default_factory=list)
    verification_evidence: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)
