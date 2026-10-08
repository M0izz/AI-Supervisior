import logging
from typing import List, Optional
from adapters.models import (
    ProviderDescriptor,
    ModelDescriptor,
    AdapterAvailabilityStatus,
)
from integrations.gemma.reasoner import GemmaReasoner

logger = logging.getLogger("supervisor.integrations.gemma.provider")


class GemmaProvider:
    """
    Google Gemma 4 Supervisory Intelligence Provider.
    Exposes open-weights lightweight supervisory reasoning models
    for planning, bounded goal decomposition, and explanation.
    """

    def __init__(self, reasoner: Optional[GemmaReasoner] = None):
        self.reasoner = reasoner or GemmaReasoner()

    async def get_descriptor(self) -> ProviderDescriptor:
        """Returns standard operational descriptor for Google Gemma."""
        return ProviderDescriptor(
            provider_id="google_gemma",
            name="Google Gemma 4",
            status=AdapterAvailabilityStatus.AVAILABLE,
            available=True,
            message="Google Gemma 4 lightweight supervisory intelligence active.",
            capabilities=[
                "supervisory_intelligence",
                "goal_decomposition",
                "invariant_extraction",
                "decision_explanation",
                "failure_classification"
            ],
            inference_endpoint="local://gemma-engine",
            managed_agents_support=False,
            action_gateway_support=False,
            supported_models=["gemma-4-31B-it", "gemma-4-9B-it"]
        )

    async def get_models(self) -> List[ModelDescriptor]:
        """Returns models exposed by Google Gemma."""
        return [
            ModelDescriptor(
                model_id="gemma-4-31B-it",
                name="Google Gemma 4 (31B-it)",
                developer="Google",
                infrastructure_provider="gemma",
                parameter_size="31B",
                specialties=[
                    "supervisory_planning",
                    "goal_decomposition",
                    "decision_explanation",
                    "invariant_extraction"
                ],
                available=True,
                context_window=131072
            ),
            ModelDescriptor(
                model_id="gemma-4-9B-it",
                name="Google Gemma 4 (9B-it)",
                developer="Google",
                infrastructure_provider="gemma",
                parameter_size="9B",
                specialties=[
                    "fast_triage",
                    "failure_classification",
                    "lightweight_supervision"
                ],
                available=True,
                context_window=32768
            )
        ]
