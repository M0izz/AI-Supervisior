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
    LONG_RUNNING_SESSION = "long_running_session"
    REMOTE_EXECUTION = "remote_execution"
    GOVERNED_TOOLS = "governed_tools"


class RuntimeType(str, Enum):
    """Distinction between Agent Runtimes, Underlying Models, and Infrastructure Providers."""
    AGENT_RUNTIME = "agent_runtime"
    MODEL = "model"
    INFRASTRUCTURE = "infrastructure"


class ExecutionMode(str, Enum):
    """Where and how execution runs."""
    LOCAL_PROCESS = "local_process"
    REMOTE_MANAGED = "remote_managed"
    SERVERLESS_INFERENCE = "serverless_inference"


class AdapterAvailabilityStatus(str, Enum):
    """Runtime availability status of an agent adapter or provider."""
    AVAILABLE = "AVAILABLE"
    CONNECTED = "CONNECTED"
    NOT_INSTALLED = "NOT_INSTALLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    MISCONFIGURED = "MISCONFIGURED"
    UNAUTHORIZED = "UNAUTHORIZED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class AdapterProcessStatus(str, Enum):
    """Lifecycle status of an executing agent process."""
    PENDING = "PENDING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    ATTACHED = "ATTACHED"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class AdapterIdentity(BaseModel):
    """Structured identity, architecture classification, and capability metadata."""
    provider: str = Field(..., description="Provider name (e.g., 'anthropic', 'digitalocean', 'nebius')")
    adapter_id: str = Field(..., description="Unique adapter key (e.g., 'claude_code', 'hermes')")
    display_name: str = Field(..., description="Human-readable display name")
    version: str = Field(default="1.0.0", description="Adapter semantic version")
    capabilities: List[str] = Field(default_factory=list, description="List of supported capability tags")

    # Architecture distinctions (Section 5, 18)
    runtime_type: RuntimeType = Field(default=RuntimeType.AGENT_RUNTIME, description="Classification of runtime")
    execution_mode: ExecutionMode = Field(default=ExecutionMode.LOCAL_PROCESS, description="Primary execution mode")
    infrastructure_provider: str = Field(default="local", description="Backing infrastructure (local, digitalocean, nebius)")
    supported_models: List[str] = Field(default_factory=list, description="Models this adapter can drive")
    supported_tools: List[str] = Field(default_factory=list, description="Governed tools or extensions supported")
    session_support: bool = Field(default=False, description="Supports long-lived attach/resume sessions")
    remote_execution: bool = Field(default=False, description="Executes on remote cloud/microVM infrastructure")
    local_execution: bool = Field(default=True, description="Executes on developer's local workstation")
    configuration_requirements: List[str] = Field(default_factory=list, description="Environment variables or files required")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class AdapterAvailability(BaseModel):
    """Diagnostic check result for adapter installation and authorization."""
    status: AdapterAvailabilityStatus
    available: bool
    message: str
    executable_path: Optional[str] = None
    diagnostics: Dict[str, Any] = Field(default_factory=dict)

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


class ProviderDescriptor(BaseModel):
    """Operational descriptor for an infrastructure or inference provider."""
    provider_id: str = Field(..., description="Unique provider ID (e.g., 'digitalocean', 'nebius', 'local')")
    name: str = Field(..., description="Display name")
    status: AdapterAvailabilityStatus = Field(default=AdapterAvailabilityStatus.NOT_CONFIGURED)
    available: bool = False
    message: str = ""
    capabilities: List[str] = Field(default_factory=list)
    inference_endpoint: Optional[str] = None
    managed_agents_support: bool = False
    action_gateway_support: bool = False
    supported_models: List[str] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ModelDescriptor(BaseModel):
    """Operational descriptor for an LLM model available through an inference provider."""
    model_id: str = Field(..., description="Unique model identifier (e.g., 'gemma-4-31B-it')")
    name: str = Field(..., description="Display name")
    developer: str = Field(..., description="Organization (e.g., Google, Nous Research, Alibaba)")
    infrastructure_provider: str = Field(..., description="Inference provider (digitalocean, nebius, local)")
    parameter_size: Optional[str] = None
    specialties: List[str] = Field(default_factory=list, description="Specialty tags (reasoning, coding, etc.)")
    available: bool = False
    context_window: Optional[int] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
