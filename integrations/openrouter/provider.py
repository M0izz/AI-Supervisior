import logging
from typing import Any, Dict, List, Optional
from adapters.models import (
    ProviderDescriptor,
    ModelDescriptor,
    AdapterAvailabilityStatus,
)
from integrations.openrouter.client import OpenRouterClient

logger = logging.getLogger("supervisor.integrations.openrouter.provider")


class OpenRouterProvider:
    """
    OpenRouter Infrastructure & Inference Provider.
    Coordinates:
      1. Unified Multi-Model Gateway (200+ models from Anthropic, OpenAI, Meta, Google, DeepSeek)
      2. Dynamic Model Catalog Discovery
      3. Automatic Fallbacks and Cost-Optimized Routing
    """

    def __init__(self, client: Optional[OpenRouterClient] = None):
        self.client = client or OpenRouterClient()

    async def get_descriptor(self) -> ProviderDescriptor:
        """Returns standard operational descriptor for OpenRouter."""
        health = await self.client.check_health()
        authenticated = health.get("authenticated", False)

        if authenticated:
            avail_status = AdapterAvailabilityStatus.CONNECTED
            is_avail = True
            msg = "OpenRouter inference gateway connected and authorized."
        elif self.client.api_key:
            avail_status = AdapterAvailabilityStatus.UNAUTHORIZED
            is_avail = False
            msg = health.get("message", "OpenRouter authentication failed.")
        else:
            avail_status = AdapterAvailabilityStatus.NOT_CONFIGURED
            is_avail = False
            msg = "OPENROUTER_API_KEY not configured in environment."

        models = await self.client.list_models()

        return ProviderDescriptor(
            provider_id="openrouter",
            name="OpenRouter",
            status=avail_status,
            available=is_avail,
            message=msg,
            capabilities=[
                "multi_model_routing",
                "serverless_inference",
                "dynamic_catalog",
                "open_models",
                "automatic_fallback",
                "byok_support"
            ],
            inference_endpoint=self.client.base_url,
            managed_agents_support=False,
            action_gateway_support=False,
            supported_models=[m["model_id"] for m in models]
        )

    async def get_models(self) -> List[ModelDescriptor]:
        """Returns all models exposed by OpenRouter inference catalog."""
        raw_models = await self.client.list_models()
        return [
            ModelDescriptor(
                model_id=m["model_id"],
                name=m["name"],
                developer=m["developer"],
                infrastructure_provider="openrouter",
                parameter_size=m.get("parameter_size"),
                specialties=m.get("specialties", []),
                available=bool(m.get("available", False)),
                context_window=m.get("context_window", 128000)
            )
            for m in raw_models
        ]
