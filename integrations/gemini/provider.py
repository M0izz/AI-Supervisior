import logging
from typing import Any, Dict, List, Optional
from adapters.models import (
    ProviderDescriptor,
    ModelDescriptor,
    AdapterAvailabilityStatus,
)
from integrations.gemini.client import GeminiClient

logger = logging.getLogger("supervisor.integrations.gemini.provider")


class GeminiProvider:
    """
    Google Gemini Infrastructure & Inference Provider.
    Acts as an inference and deep reasoning layer (NOT an agent runtime).
    """

    def __init__(self, client: Optional[GeminiClient] = None):
        self.client = client or GeminiClient()

    async def get_descriptor(self) -> ProviderDescriptor:
        health = await self.client.check_health()
        status_val = health.get("status", "NOT_CONFIGURED")

        if status_val == "CONNECTED":
            avail_status = AdapterAvailabilityStatus.CONNECTED
            is_avail = True
        elif status_val == "AUTHENTICATION_REQUIRED":
            avail_status = AdapterAvailabilityStatus.UNAUTHORIZED
            is_avail = False
        elif status_val == "NOT_CONFIGURED":
            avail_status = AdapterAvailabilityStatus.NOT_CONFIGURED
            is_avail = False
        else:
            avail_status = AdapterAvailabilityStatus.UNAVAILABLE
            is_avail = False

        return ProviderDescriptor(
            provider_id="google_gemini",
            name="Google Gemini",
            status=avail_status,
            available=is_avail,
            message=health.get("message", "Google Gemini reasoning layer"),
            capabilities=[
                "multimodal_analysis",
                "complex_failure_diagnosis",
                "architecture_analysis",
                "deep_context_reasoning",
                "incident_briefing"
            ],
            inference_endpoint=self.client.BASE_URL,
            managed_agents_support=False,
            action_gateway_support=False,
            supported_models=[
                "gemini-1.5-pro",
                "gemini-1.5-flash",
                "gemini-2.0-flash"
            ]
        )

    async def get_models(self) -> List[ModelDescriptor]:
        is_avail = self.client.is_configured
        return [
            ModelDescriptor(
                model_id="gemini-1.5-pro",
                name="Google Gemini 1.5 Pro",
                developer="Google",
                infrastructure_provider="google_gemini",
                parameter_size="Multimodal",
                specialties=[
                    "complex_failure_diagnosis",
                    "architecture_analysis",
                    "multimodal_reasoning",
                    "deep_context"
                ],
                available=is_avail,
                context_window=2097152
            ),
            ModelDescriptor(
                model_id="gemini-1.5-flash",
                name="Google Gemini 1.5 Flash",
                developer="Google",
                infrastructure_provider="google_gemini",
                parameter_size="Fast",
                specialties=[
                    "fast_incident_analysis",
                    "log_parsing",
                    "recovery_strategy"
                ],
                available=is_avail,
                context_window=1048576
            ),
            ModelDescriptor(
                model_id="gemini-2.0-flash",
                name="Google Gemini 2.0 Flash",
                developer="Google",
                infrastructure_provider="google_gemini",
                parameter_size="Next-Gen",
                specialties=[
                    "real_time_multimodal",
                    "rapid_code_review"
                ],
                available=is_avail,
                context_window=1048576
            )
        ]
