import os
import logging
from typing import Any, Dict, List, Optional
import httpx
from integrations.digitalocean.models import (
    DigitalOceanConfig,
    DigitalOceanStatus,
    ManagedAgentSession,
)

logger = logging.getLogger("supervisor.integrations.digitalocean")


class DigitalOceanClient:
    """
    Asynchronous client for DigitalOcean Managed Agents, Harness Runtime,
    Action Gateway, and Serverless Inference.
    Offline-first and safe: will never crash or leak credentials if unconfigured.
    """

    def __init__(self, config: Optional[DigitalOceanConfig] = None):
        self.config = config or DigitalOceanConfig(
            api_token=os.getenv("DIGITALOCEAN_TOKEN") or os.getenv("DO_API_TOKEN"),
            inference_key=os.getenv("DO_INFERENCE_KEY") or os.getenv("DIGITALOCEAN_TOKEN") or os.getenv("DO_API_TOKEN"),
            project_id=os.getenv("DO_PROJECT_ID"),
            region=os.getenv("DO_REGION", "nyc3"),
        )
        self.timeout = float(os.getenv("DO_API_TIMEOUT", "15.0"))

    @property
    def is_configured(self) -> bool:
        return bool(self.config.api_token or self.config.inference_key)

    async def check_health(self) -> Dict[str, Any]:
        """Verifies authentication and availability of DigitalOcean services."""
        if not self.is_configured:
            return {
                "status": DigitalOceanStatus.NOT_CONFIGURED.value,
                "available": False,
                "message": "DIGITALOCEAN_TOKEN or DO_API_TOKEN not configured in environment.",
                "region": self.config.region,
                "inference_ready": False,
                "managed_agents_ready": False,
            }

        headers = {
            "Authorization": f"Bearer {self.config.api_token or self.config.inference_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Test connectivity to account or inference endpoint
                resp = await client.get(
                    f"{self.config.inference_base_url}/models",
                    headers=headers
                )
                if resp.status_code in (200, 201):
                    return {
                        "status": DigitalOceanStatus.CONNECTED.value,
                        "available": True,
                        "message": "Connected to DigitalOcean infrastructure & Inference API.",
                        "region": self.config.region,
                        "inference_ready": True,
                        "managed_agents_ready": True,
                    }
                elif resp.status_code in (401, 403):
                    return {
                        "status": DigitalOceanStatus.AUTHENTICATION_REQUIRED.value,
                        "available": False,
                        "message": "Invalid DigitalOcean API token or insufficient permissions.",
                        "region": self.config.region,
                        "inference_ready": False,
                        "managed_agents_ready": False,
                    }
                else:
                    return {
                        "status": DigitalOceanStatus.UNAVAILABLE.value,
                        "available": False,
                        "message": f"DigitalOcean service responded with HTTP {resp.status_code}",
                        "region": self.config.region,
                        "inference_ready": False,
                        "managed_agents_ready": False,
                    }
        except Exception as e:
            logger.warning(f"DigitalOcean connectivity probe error: {e}")
            return {
                "status": DigitalOceanStatus.UNAVAILABLE.value,
                "available": False,
                "message": f"Network error contacting DigitalOcean: {type(e).__name__}",
                "region": self.config.region,
                "inference_ready": False,
                "managed_agents_ready": False,
            }

    async def list_models(self) -> List[Dict[str, Any]]:
        """Returns models supported by DigitalOcean Serverless Inference."""
        default_catalog = [
            {
                "model_id": "gemma-4-31B-it",
                "name": "Google Gemma 4",
                "developer": "Google",
                "parameter_size": "31B",
                "specialties": ["reasoning", "planning", "code_review"],
                "available": self.is_configured,
            },
            {
                "model_id": "hermes-4-70b-instruct",
                "name": "Nous Hermes 4",
                "developer": "Nous Research",
                "parameter_size": "70B",
                "specialties": ["agentic_coding", "tool_use", "long_session"],
                "available": self.is_configured,
            },
            {
                "model_id": "llama-3.3-70b-instruct",
                "name": "Meta Llama 3.3",
                "developer": "Meta",
                "parameter_size": "70B",
                "specialties": ["general", "code_generation"],
                "available": self.is_configured,
            }
        ]

        if not self.is_configured:
            return default_catalog

        headers = {
            "Authorization": f"Bearer {self.config.inference_key or self.config.api_token}",
            "Content-Type": "application/json"
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.config.inference_base_url}/models", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    if models:
                        return [
                            {
                                "model_id": m.get("id", "unknown"),
                                "name": m.get("name", m.get("id")),
                                "developer": "DigitalOcean Inference",
                                "parameter_size": "Cloud",
                                "specialties": ["inference"],
                                "available": True,
                            }
                            for m in models
                        ]
        except Exception as e:
            logger.debug(f"Could not fetch dynamic DO model catalog: {e}")

        return default_catalog

    async def invoke_inference(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500
    ) -> Dict[str, Any]:
        """Invokes DigitalOcean Serverless Inference (e.g. Gemma 4)."""
        if not self.is_configured:
            # Deterministic offline fallback mock
            return {
                "id": "mock_do_inference",
                "model": model,
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "DigitalOcean Inference offline fallback. Configure DIGITALOCEAN_TOKEN to enable live generation."
                        }
                    }
                ],
                "usage": {"total_tokens": 0}
            }

        headers = {
            "Authorization": f"Bearer {self.config.inference_key or self.config.api_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.config.inference_base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            resp.raise_for_status()
            return resp.json()
