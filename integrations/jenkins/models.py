from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class JenkinsBuildStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"


class JenkinsBuildOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    UNSTABLE = "UNSTABLE"
    ABORTED = "ABORTED"
    UNKNOWN = "UNKNOWN"


class JenkinsTestCase(BaseModel):
    name: str
    status: str  # PASSED, FAILED, SKIPPED
    duration_s: float = 0.0
    error_details: Optional[str] = None
    error_stack_trace: Optional[str] = None


class JenkinsBuildResult(BaseModel):
    """Structured build result consumed by Supervisor and EventBus."""
    build_id: str
    job_name: str
    status: JenkinsBuildStatus
    result: JenkinsBuildOutcome
    duration_ms: float = 0.0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    error_signature: Optional[str] = None
    details: Optional[str] = None
    test_cases: List[JenkinsTestCase] = Field(default_factory=list)
    url: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def is_success(self) -> bool:
        return self.status == JenkinsBuildStatus.COMPLETED and self.result == JenkinsBuildOutcome.SUCCESS and self.tests_failed == 0

    @property
    def is_failure(self) -> bool:
        return self.result in (JenkinsBuildOutcome.FAILURE, JenkinsBuildOutcome.UNSTABLE) or self.tests_failed > 0

    def to_concise_summary(self) -> Dict[str, Any]:
        """Returns concise summary without leaking secrets or massive logs."""
        return {
            "build_id": self.build_id,
            "job_name": self.job_name,
            "status": self.status.value,
            "result": self.result.value,
            "duration_ms": self.duration_ms,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_skipped": self.tests_skipped,
            "error_signature": self.error_signature,
            "details": self.details,
            "url": self.url
        }


class JenkinsTriggerResult(BaseModel):
    """Result from triggering a build on Jenkins."""
    queued: bool = True
    job_name: str
    queue_item_url: Optional[str] = None
    build_id: Optional[str] = None
    message: Optional[str] = None


# Structured Exceptions for Jenkins operations
class JenkinsError(Exception):
    """Base exception for Jenkins CI operations."""
    pass


class JenkinsConnectionError(JenkinsError):
    """Raised when Jenkins server is unreachable or offline."""
    pass


class JenkinsAuthError(JenkinsError):
    """Raised when authentication against Jenkins fails."""
    pass


class JenkinsJobNotFoundError(JenkinsError):
    """Raised when the specified Jenkins job is not found."""
    pass


class JenkinsTimeoutError(JenkinsError):
    """Raised when polling for a Jenkins build completion exceeds the timeout."""
    pass
