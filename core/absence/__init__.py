"""
Absence Mode Subsystem for AI Supervisor.
Enforces bounded autonomy, conservative limits, auditable decisions,
and the core invariant:
"Absence Mode expands continuity, not authority."
"""

from core.absence.models import (
    AbsencePolicy,
    AbsenceSession,
    AbsenceSessionState,
    AbsenceDecision,
    AbsenceDecisionType,
    ApprovalPolicy,
    VerificationPolicy,
    FailurePolicy
)
from core.absence.engine import AbsencePolicyEngine

__all__ = [
    "AbsencePolicy",
    "AbsenceSession",
    "AbsenceSessionState",
    "AbsenceDecision",
    "AbsenceDecisionType",
    "ApprovalPolicy",
    "VerificationPolicy",
    "FailurePolicy",
    "AbsencePolicyEngine",
]
