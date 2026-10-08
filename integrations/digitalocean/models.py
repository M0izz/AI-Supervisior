from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class DigitalOceanStatus(str, Enum):
    CONNECTED = "CONNECTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class DigitalOceanConfig(BaseModel):
    """DigitalOcean infrastructure and inference configuration."""
    api_token: Optional[str] = Field(default=None, description="DigitalOcean Personal Access Token")
    inference_key: Optional[str] = Field(default=None, description="DigitalOcean Inference API Key")
    project_id: Optional[str] = Field(default=None, description="Target DO Project ID")
    region: str = Field(default="nyc3", description="Default DO region (e.g. nyc3, sfo3, fra1)")
    inference_base_url: str = Field(
        default="https://inference.digitalocean.com/v1",
        description="DigitalOcean Serverless Inference base URL"
    )
    agents_api_url: str = Field(
        default="https://api.digitalocean.com/v2/managed-agents",
        description="DigitalOcean Managed Agents / Droplets API endpoint"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class GovernedToolCall(BaseModel):
    """A tool invocation passing through the DigitalOcean Action Gateway."""
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    requester_agent: str
    target_workspace: str
    is_safe: bool = True
    requires_approval: bool = False
    policy_violation_reason: Optional[str] = None


class ManagedAgentSession(BaseModel):
    """Persistent or microVM session state for remote execution."""
    session_id: str
    agent_runtime: str = "hermes"
    environment: str = "microvm"
    status: str = "INITIALIZING"
    created_at: float
    endpoint: Optional[str] = None
    isolated_workspace_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
