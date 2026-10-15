import logging
import os
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("supervisor.integrations.openrouter.client")


class OpenRouterClient:
    """
    OpenRouter API Client.
    Provides multi-model inference routing and dynamic model catalog discovery.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.base_url = (base_url or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")).rstrip("/")
        self.timeout_seconds = timeout_seconds or float(os.getenv("SUPERVISOR_MODEL_TIMEOUT_SECONDS", "20.0"))

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ai-supervisior.vercel.app",
            "X-Title": "AI Supervisor Control Plane"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def check_health(self) -> Dict[str, Any]:
        """Verifies OpenRouter API key validity and connectivity."""
        if not self.api_key:
            self.api_key = os.getenv("OPENROUTER_API_KEY", "")

        if not self.api_key:
            return {
                "status": "healthy",
                "provider": "openrouter",
                "mode": "fallback_local",
                "message": "OPENROUTER_API_KEY not configured; operating in safe deterministic local fallback mode.",
                "base_url": self.base_url,
                "authenticated": False,
                "safe_fallback_active": True
            }

        try:
            async with httpx.AsyncClient(timeout=min(self.timeout_seconds, 6.0)) as client:
                res = await client.get(f"{self.base_url}/auth/key", headers=self._headers())
                if res.status_code == 200:
                    data = res.json().get("data", {})
                    limit_rem = data.get("limit_remaining")
                    is_free = data.get("is_free_tier", False)
                    return {
                        "status": "healthy",
                        "provider": "openrouter",
                        "mode": "openrouter_cloud",
                        "message": "OpenRouter API authenticated successfully.",
                        "base_url": self.base_url,
                        "authenticated": True,
                        "is_free_tier": is_free,
                        "limit_remaining": limit_rem,
                        "safe_fallback_active": True
                    }
                else:
                    return {
                        "status": "degraded",
                        "provider": "openrouter",
                        "mode": "fallback_local",
                        "message": f"OpenRouter returned HTTP {res.status_code}: {res.text[:100]}",
                        "base_url": self.base_url,
                        "authenticated": False,
                        "safe_fallback_active": True
                    }
        except Exception as e:
            return {
                "status": "degraded",
                "provider": "openrouter",
                "mode": "fallback_local",
                "message": f"Endpoint unreachable: {type(e).__name__}",
                "base_url": self.base_url,
                "authenticated": False,
                "safe_fallback_active": True
            }

    async def list_models(self) -> List[Dict[str, Any]]:
        """Queries OpenRouter model catalog or returns premier model defaults."""
        default_catalog = [
            {
                "model_id": "anthropic/claude-3.7-sonnet",
                "name": "Claude 3.7 Sonnet",
                "developer": "Anthropic",
                "parameter_size": "Hybrid Reasoning",
                "specialties": ["coding", "architecture", "tool_use"],
                "context_window": 200000,
                "available": bool(self.api_key)
            },
            {
                "model_id": "deepseek/deepseek-r1",
                "name": "DeepSeek R1",
                "developer": "DeepSeek",
                "parameter_size": "671B",
                "specialties": ["reasoning", "math_and_logic", "code_repair"],
                "context_window": 164000,
                "available": bool(self.api_key)
            },
            {
                "model_id": "openai/gpt-4o",
                "name": "OpenAI GPT-4o",
                "developer": "OpenAI",
                "parameter_size": "Omni",
                "specialties": ["fast_coding", "multimodal", "precision"],
                "context_window": 128000,
                "available": bool(self.api_key)
            },
            {
                "model_id": "google/gemini-2.5-pro",
                "name": "Gemini 2.5 Pro",
                "developer": "Google",
                "parameter_size": "Thinking",
                "specialties": ["deep_analysis", "long_context", "multimodal"],
                "context_window": 1048576,
                "available": bool(self.api_key)
            },
            {
                "model_id": "meta-llama/llama-3.3-70b-instruct",
                "name": "Meta Llama 3.3 70B",
                "developer": "Meta",
                "parameter_size": "70B",
                "specialties": ["code_generation", "instruction_following"],
                "context_window": 128000,
                "available": bool(self.api_key)
            },
            {
                "model_id": "qwen/qwen-2.5-coder-32b-instruct",
                "name": "Qwen 2.5 Coder 32B",
                "developer": "Alibaba Cloud",
                "parameter_size": "32B",
                "specialties": ["code_editing", "test_crafting"],
                "context_window": 32768,
                "available": bool(self.api_key)
            }
        ]

        if not self.api_key:
            return default_catalog

        try:
            async with httpx.AsyncClient(timeout=min(self.timeout_seconds, 6.0)) as client:
                res = await client.get(f"{self.base_url}/models", headers=self._headers())
                if res.status_code == 200:
                    raw_models = res.json().get("data", [])
                    if raw_models:
                        featured_ids = {
                            "anthropic/claude-3.7-sonnet",
                            "deepseek/deepseek-r1",
                            "openai/gpt-4o",
                            "google/gemini-2.5-pro",
                            "meta-llama/llama-3.3-70b-instruct",
                            "qwen/qwen-2.5-coder-32b-instruct"
                        }
                        discovered = []
                        for m in raw_models:
                            mid = m.get("id", "")
                            if mid in featured_ids or any(k in mid.lower() for k in ["claude-3.7", "deepseek-r1", "gpt-4o", "gemini-2.5", "llama-3.3"]):
                                name = m.get("name") or mid.split("/")[-1].replace("-", " ").title()
                                dev = mid.split("/")[0].title() if "/" in mid else "OpenRouter"
                                ctx = m.get("context_length", 128000)
                                discovered.append({
                                    "model_id": mid,
                                    "name": name,
                                    "developer": dev,
                                    "parameter_size": "Cloud Multi-Provider",
                                    "specialties": ["inference", "routing"],
                                    "context_window": ctx,
                                    "available": True
                                })
                        if discovered:
                            existing_ids = {d["model_id"] for d in discovered}
                            for dm in default_catalog:
                                if dm["model_id"] not in existing_ids:
                                    discovered.insert(0, dm)
                            return discovered
        except Exception as e:
            logger.debug(f"Dynamic OpenRouter catalog query error: {e}")

        return default_catalog
