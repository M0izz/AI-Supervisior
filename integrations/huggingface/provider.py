import logging
from typing import Any, Dict, List, Optional
from adapters.models import (
    ProviderDescriptor,
    ModelDescriptor,
    AdapterAvailabilityStatus,
)
from integrations.huggingface.client import HuggingFaceClient

logger = logging.getLogger("supervisor.integrations.huggingface.provider")


class HuggingFaceProvider:
    """
    Hugging Face First-Class Open Ecosystem Infrastructure Provider.
    Coordinates:
      1. Serverless Inference API for open weights models
      2. Hugging Face Model Hub catalog & embedding discovery
      3. Community model weighting and fallback execution
    """

    def __init__(self, client: Optional[HuggingFaceClient] = None):
        self.client = client or HuggingFaceClient()

    async def get_descriptor(self) -> ProviderDescriptor:
        """Returns standard operational descriptor for Hugging Face."""
        health = await self.client.check_health()
        authenticated = health.get("authenticated", False)

        if authenticated:
            avail_status = AdapterAvailabilityStatus.CONNECTED
            is_avail = True
            msg = health.get("message", "Hugging Face Hub connected and authorized.")
        elif self.client.api_key:
            avail_status = AdapterAvailabilityStatus.UNAUTHORIZED
            is_avail = False
            msg = health.get("message", "Hugging Face authentication failed.")
        else:
            avail_status = AdapterAvailabilityStatus.NOT_CONFIGURED
            is_avail = False
            msg = "HUGGINGFACE_API_KEY not configured in environment."

        models = await self.client.list_models()

        return ProviderDescriptor(
            provider_id="huggingface",
            name="Hugging Face",
            status=avail_status,
            available=is_avail,
            message=msg,
            capabilities=[
                "serverless_inference",
                "open_weights",
                "model_hub",
                "custom_fine_tunes",
                "embedding_models"
            ],
            inference_endpoint=self.client.base_url,
            managed_agents_support=False,
            action_gateway_support=False,
            supported_models=[m["model_id"] for m in models]
        )

    async def get_models(self) -> List[ModelDescriptor]:
        """Returns all models exposed by Hugging Face Inference catalog."""
        raw_models = await self.client.list_models()
        return [
            ModelDescriptor(
                model_id=m["model_id"],
                name=m["name"],
                developer=m["developer"],
                infrastructure_provider="huggingface",
                parameter_size=m.get("parameter_size"),
                specialties=m.get("specialties", []),
                available=bool(m.get("available", False)),
                context_window=m.get("context_window", 32768)
            )
            for m in raw_models
        ]
