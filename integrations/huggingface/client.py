import logging
import os
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("supervisor.integrations.huggingface.client")


class HuggingFaceClient:
    """
    Hugging Face Inference Substrate & Model Hub Client.
    Coordinates serverless inference across open weights models (Llama 3.3, Qwen 2.5 Coder, DeepSeek R1, Starcoder2).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None
    ):
        self.api_key = api_key or os.getenv("HUGGINGFACE_API_KEY", "")
        self.base_url = (base_url or os.getenv("HUGGINGFACE_BASE_URL", "https://api-inference.huggingface.co")).rstrip("/")
        self.timeout_seconds = timeout_seconds or float(os.getenv("SUPERVISOR_MODEL_TIMEOUT_SECONDS", "20.0"))

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AI-Supervisor-Control-Plane/1.0"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def check_health(self) -> Dict[str, Any]:
        """Validates Hugging Face API key credentials against whoami endpoint."""
        if not self.api_key:
            self.api_key = os.getenv("HUGGINGFACE_API_KEY", "")

        if not self.api_key:
            return {
                "status": "healthy",
                "provider": "huggingface",
                "mode": "fallback_local",
                "message": "HUGGINGFACE_API_KEY not configured; operating in safe local fallback mode.",
                "base_url": self.base_url,
                "authenticated": False,
                "safe_fallback_active": True
            }

        try:
            async with httpx.AsyncClient(timeout=min(self.timeout_seconds, 6.0)) as client:
                res = await client.get("https://huggingface.co/api/whoami-v2", headers=self._headers())
                if res.status_code == 200:
                    user_data = res.json()
                    user_name = user_data.get("name", "Authenticated User")
                    return {
                        "status": "healthy",
                        "provider": "huggingface",
                        "mode": "huggingface_hub_cloud",
                        "message": f"Hugging Face Hub connected and authenticated for '{user_name}'.",
                        "account_name": user_name,
                        "base_url": self.base_url,
                        "authenticated": True,
                        "safe_fallback_active": True
                    }
                elif res.status_code in (401, 403):
                    return {
                        "status": "unauthorized",
                        "provider": "huggingface",
                        "mode": "fallback_local",
                        "message": f"Hugging Face credentials rejected (HTTP {res.status_code})",
                        "base_url": self.base_url,
                        "authenticated": False,
                        "safe_fallback_active": True
                    }
                else:
                    return {
                        "status": "degraded",
                        "provider": "huggingface",
                        "mode": "fallback_local",
                        "message": f"Hugging Face API returned HTTP {res.status_code}",
                        "base_url": self.base_url,
                        "authenticated": False,
                        "safe_fallback_active": True
                    }
        except Exception as e:
            return {
                "status": "degraded",
                "provider": "huggingface",
                "mode": "fallback_local",
                "message": f"Endpoint unreachable: {type(e).__name__}",
                "base_url": self.base_url,
                "authenticated": False,
                "safe_fallback_active": True
            }

    async def list_models(self) -> List[Dict[str, Any]]:
        """Returns premier open models supported on Hugging Face Inference."""
        return [
            {
                "model_id": "meta-llama/Llama-3.3-70B-Instruct",
                "name": "Meta Llama 3.3 70B Instruct",
                "developer": "Meta",
                "parameter_size": "70B",
                "specialties": ["code_generation", "instruction_tuning", "reasoning"],
                "context_window": 128000,
                "available": bool(self.api_key)
            },
            {
                "model_id": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "name": "Qwen 2.5 Coder 32B Instruct",
                "developer": "Alibaba Cloud",
                "parameter_size": "32B",
                "specialties": ["code_repair", "test_generation", "refactoring"],
                "context_window": 32768,
                "available": bool(self.api_key)
            },
            {
                "model_id": "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
                "name": "DeepSeek R1 Distill Qwen 32B",
                "developer": "DeepSeek",
                "parameter_size": "32B",
                "specialties": ["chain_of_thought", "math_logic", "invariant_proving"],
                "context_window": 65536,
                "available": bool(self.api_key)
            },
            {
                "model_id": "bigcode/starcoder2-15b",
                "name": "StarCoder 2 15B",
                "developer": "BigCode / Hugging Face",
                "parameter_size": "15B",
                "specialties": ["code_completion", "syntax_analysis"],
                "context_window": 16384,
                "available": bool(self.api_key)
            },
            {
                "model_id": "google/gemma-2-27b-it",
                "name": "Google Gemma 2 27B",
                "developer": "Google",
                "parameter_size": "27B",
                "specialties": ["bounded_reasoning", "decision_explanation"],
                "context_window": 8192,
                "available": bool(self.api_key)
            }
        ]
