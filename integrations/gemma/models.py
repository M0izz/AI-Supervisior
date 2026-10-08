from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GemmaConfig(BaseModel):
    """Configuration for Gemma 4 supervisory intelligence."""
    model_id: str = Field(default="gemma-4-31B-it", description="Gemma 4 model identifier")
    api_endpoint: Optional[str] = Field(default=None, description="Local or remote inference endpoint")
    api_key: Optional[str] = Field(default=None, description="Optional inference API key")
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(default=800, ge=64)


class GemmaPlanningOutput(BaseModel):
    """Structured mission plan proposal produced with Gemma 4 assistance."""
    goal_summary: str
    detected_invariants: List[str] = Field(default_factory=list)
    suggested_steps: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_agent: str = "claude_code"
    fallback_agent: str = "codex"
    verification_focus: List[str] = Field(default_factory=list)
    model_provenance: str = "Google Gemma 4 (gemma-4-31B-it)"
