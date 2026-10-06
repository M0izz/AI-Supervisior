from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GeminiAnalysisRequest(BaseModel):
    """Request for deeper analysis by Google Gemini."""
    task_id: Optional[str] = None
    mission_id: Optional[str] = None
    analysis_type: str = "COMPLEX_FAILURE"  # COMPLEX_FAILURE, MULTIMODAL, ARCHITECTURE_REVIEW, RECOVERY_STRATEGY
    context: Dict[str, Any] = Field(default_factory=dict)
    prompt: Optional[str] = None


class GeminiAnalysisResult(BaseModel):
    """Result of complex failure or multimodal analysis."""
    diagnosis: str
    root_cause: str
    recommended_recovery: str
    confidence: float = 0.85
    affected_components: List[str] = Field(default_factory=list)
    model_provenance: str = "Google Gemini (gemini-1.5-pro)"
    is_live: bool = False
