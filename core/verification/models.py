from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field, ConfigDict


class VerificationDecision(str, Enum):
    """
    Final deterministic outcome of an independent verification pass.
    """
    ACCEPT = "ACCEPT"              # All required verification criteria satisfied with empirical evidence
    REJECT = "REJECT"              # Objective evidence proves failure, regression, or scope violation
    REQUIRE_REVIEW = "REQUIRE_REVIEW"  # Ambiguous state or missing verifiable criteria needing operator review


class VerificationCheckStatus(str, Enum):
    """Status of an individual verification check."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIPPED = "SKIPPED"


class VerificationCheckType(str, Enum):
    """Categories of independent verification checks."""
    TESTS = "TESTS"
    FILES = "FILES"
    SCOPE = "SCOPE"
    GIT = "GIT"
    COMPLETION_CLAIM = "COMPLETION_CLAIM"
    REGRESSION = "REGRESSION"


class VerificationCheck(BaseModel):
    """
    Individual modular verification assertion and its empirical evidence.
    """
    check_id: str = Field(..., description="Unique check identifier")
    check_type: VerificationCheckType = Field(..., description="Category of verification check")
    description: str = Field(..., description="Human-readable description of what this check verifies")
    status: VerificationCheckStatus = Field(..., description="Outcome status of the check")
    message: Optional[str] = Field(default=None, description="Detailed explanatory message or failure reason")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Empirical evidence data collected during check")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context or diagnostics")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class VerificationContext(BaseModel):
    """
    Input context provided to the verification engine.
    Encapsulates task boundaries, worktree location, claims, and test requirements.
    """
    mission_id: str = Field(..., description="Mission identifier")
    task_id: str = Field(..., description="Task identifier")
    agent_id: Optional[str] = Field(default=None, description="Agent claiming completion")
    workspace: str = Field(..., description="Path to isolated task workspace or Git worktree")
    allowed_files: List[str] = Field(default_factory=list, description="Authorized task file/dir whitelist patterns")
    expected_files: List[str] = Field(default_factory=list, description="Files expected to be created or modified")
    verification_requirements: List[str] = Field(
        default_factory=list,
        description="Explicit verification commands or test assertions (e.g., ['pytest tests/test_auth.py'])"
    )
    completion_claim: Dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-reported completion claims (e.g. summary, claimed files, claimed test status)"
    )
    baseline_test_results: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional baseline test results dictionary for regression detection"
    )
    timeout: float = Field(default=60.0, ge=0.01, description="Maximum execution timeout for verification commands in seconds")


    model_config = ConfigDict(arbitrary_types_allowed=True)


class VerificationResult(BaseModel):
    """
    Comprehensive structured report of independent verification.
    Persisted to SQLite and published to the EventBus.
    """
    verification_id: str = Field(
        default_factory=lambda: f"ver_{uuid.uuid4().hex[:12]}",
        description="Unique verification identifier"
    )
    mission_id: str = Field(..., description="Mission context identifier")
    task_id: str = Field(..., description="Task context identifier")
    agent_id: Optional[str] = Field(default=None, description="Agent identifier being verified")
    decision: VerificationDecision = Field(..., description="Final verification decision: ACCEPT, REJECT, or REQUIRE_REVIEW")
    status: str = Field(default="COMPLETED", description="Lifecycle status: COMPLETED, PASSED, FAILED, REVIEW_REQUIRED")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of verification")
    checks: List[VerificationCheck] = Field(default_factory=list, description="List of individual checks evaluated")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Aggregate empirical evidence summary")
    failed_checks: List[str] = Field(default_factory=list, description="IDs of checks that failed")
    warnings: List[str] = Field(default_factory=list, description="Warning messages or non-fatal anomalies")
    summary: str = Field(default="", description="Human-readable verification conclusion summary")

    model_config = ConfigDict(arbitrary_types_allowed=True)
