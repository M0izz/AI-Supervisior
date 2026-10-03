from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class ActionType(str, Enum):
    """Supported action categories in Work Protocol v1."""
    TOOL_CALL = "tool_call"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    COMMAND_EXECUTE = "command_execute"
    API_CALL = "api_call"
    HUMAN_PROMPT = "human_prompt"
    HANDOFF = "handoff"
    CUSTOM = "custom"


class ActionInfo(BaseModel):
    """
    Structured action details associated with an execution event.
    Captures what the agent performed, targeted, and the immediate outcome.
    """
    action_type: str = Field(..., description="Type of action (e.g. tool_call, file_write, command_execute)")
    target: Optional[str] = Field(default=None, description="Action target: file path, tool name, or command")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Input parameters supplied to the action")
    result: Optional[Any] = Field(default=None, description="Result output or error description")
    exit_code: Optional[int] = Field(default=None, description="Process or command exit code if applicable")
    affected_files: List[str] = Field(default_factory=list, description="List of file paths modified, read, or created")

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")


class TelemetryInfo(BaseModel):
    """
    Resource usage, operational metrics, and telemetry for execution steps.
    Optional fields allow compatibility across different provider capabilities.
    """
    input_tokens: Optional[int] = Field(default=None, ge=0, description="Prompt/input tokens consumed")
    output_tokens: Optional[int] = Field(default=None, ge=0, description="Completion/output tokens consumed")
    cost: Optional[float] = Field(default=None, ge=0.0, description="Estimated monetary cost in USD")
    duration: Optional[float] = Field(default=None, ge=0.0, description="Duration in seconds")
    exit_status: Optional[str] = Field(default=None, description="Execution status: success, error, timeout, aborted")

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
