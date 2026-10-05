from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class AdapterCapability(str, Enum):
    """Declared execution capabilities for an agent adapter."""
    CODE_EXECUTION = "code_execution"
    FILESYSTEM_READ = "filesystem_read"
    FILESYSTEM_WRITE = "filesystem_write"
    TERMINAL_EXECUTION = "terminal_execution"
    GIT = "git"
    TEST_EXECUTION = "test_execution"
    DOCUMENTATION = "documentation"
    WEB_ACCESS = "web_access"
    LOCAL_MODEL = "local_model"
    MULTIMODAL = "multimodal"


class AdapterAvailabilityStatus(str, Enum):
    """Runtime availability status of an agent adapter."""
    AVAILABLE = "AVAILABLE"
    NOT_INSTALLED = "NOT_INSTALLED"
    MISCONFIGURED = "MISCONFIGURED"
    UNAUTHORIZED = "UNAUTHORIZED"
    UNAVAILABLE = "UNAVAILABLE"


class AdapterProcessStatus(str, Enum):
    """Lifecycle status of an executing agent process."""
    PENDING = "PENDING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class AdapterIdentity(BaseModel):
    """Structured identity and capability metadata for an agent adapter."""
    provider: str = Field(..., description="Provider name (e.g., 'anthropic', 'openai')")
    adapter_id: str = Field(..., description="Unique adapter key (e.g., 'claude_code')")
    display_name: str = Field(..., description="Human-readable display name")
    version: str = Field(default="1.0.0", description="Adapter semantic version")
    capabilities: List[str] = Field(default_factory=list, description="List of supported capability tags")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class AdapterAvailability(BaseModel):
    """Diagnostic check result for adapter installation and authorization."""
    status: AdapterAvailabilityStatus
    available: bool
    message: str
    executable_path: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class AdapterExecutionResult(BaseModel):
    """Structured outcome of an adapter execution session."""
    status: AdapterProcessStatus
    exit_code: Optional[int] = None
    duration: float = Field(default=0.0, ge=0.0)
    workspace: str
    summary: str = ""
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""
    failure_reason: Optional[str] = None
    affected_files: List[str] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)
