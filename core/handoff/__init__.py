"""
Handoff Engine module for AI Supervisor.
Enables transferring task execution from one agent to another with preserved
context, provenance, worktree continuity, and verification integrity.
"""

from core.handoff.models import (
    HandoffStatus,
    HandoffTrigger,
    FactProvenance,
    ContextFact,
    HandoffContextPackage,
    HandoffRecord,
    HandoffResult,
)
from core.handoff.context import HandoffContextBuilder
from core.handoff.engine import HandoffEngine

__all__ = [
    "HandoffStatus",
    "HandoffTrigger",
    "FactProvenance",
    "ContextFact",
    "HandoffContextPackage",
    "HandoffRecord",
    "HandoffResult",
    "HandoffContextBuilder",
    "HandoffEngine",
]
