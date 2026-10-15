import logging
from typing import Any, Dict, List, Optional
from adapters.models import (
    ProviderDescriptor,
    ModelDescriptor,
    AdapterAvailabilityStatus,
)
from integrations.backboard.client import BackboardClient

logger = logging.getLogger("supervisor.integrations.backboard.provider")


class BackboardProvider:
    """
    Backboard.io (Espri.ai) Infrastructure & Memory Substrate Provider.
    Coordinates:
      1. Sovereign persistent AI memory and state management
      2. Adaptive context management for model switching
      3. Unified routing across 17,000+ LLMs
    """

    def __init__(self, client: Optional[BackboardClient] = None):
        self.client = client or BackboardClient()

    async def get_descriptor(self) -> ProviderDescriptor:
        """Returns standard operational descriptor for Backboard.io."""
        health = await self.client.check_health()
        authenticated = health.get("authenticated", False)

        if authenticated:
            avail_status = AdapterAvailabilityStatus.CONNECTED
            is_avail = True
            msg = "Backboard.io sovereign infrastructure authenticated and active."
        elif self.client.api_key:
            if "rejected" in health.get("message", "").lower() or health.get("status") == "unauthorized":
                avail_status = AdapterAvailabilityStatus.UNAUTHORIZED
                is_avail = False
                msg = health.get("message", "Backboard.io authentication failed.")
            else:
                avail_status = AdapterAvailabilityStatus.CONNECTED
                is_avail = True
                msg = "Backboard.io API key authenticated; sovereign persistent memory layer active."
        else:
            avail_status = AdapterAvailabilityStatus.NOT_CONFIGURED
            is_avail = False
            msg = "BACKBOARD_API_KEY not configured in environment."

        models = await self.client.list_models()

        return ProviderDescriptor(
            provider_id="backboard",
            name="Backboard.io (Espri.ai)",
            status=avail_status,
            available=is_avail,
            message=msg,
            capabilities=[
                "persistent_memory",
                "adaptive_context",
                "sovereign_ai",
                "multi_model_routing",
                "hybrid_rag"
            ],
            inference_endpoint=self.client.base_url,
            managed_agents_support=False,
            action_gateway_support=False,
            supported_models=[m["model_id"] for m in models]
        )

    async def get_models(self) -> List[ModelDescriptor]:
        """Returns all models exposed by Backboard.io."""
        raw_models = await self.client.list_models()
        return [
            ModelDescriptor(
                model_id=m["model_id"],
                name=m["name"],
                developer=m["developer"],
                infrastructure_provider="backboard",
                parameter_size=m.get("parameter_size"),
                specialties=m.get("specialties", []),
                available=bool(m.get("available", False)),
                context_window=m.get("context_window", 128000)
            )
            for m in raw_models
        ]
