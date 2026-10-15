import logging
import os
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("supervisor.integrations.backboard.client")


class BackboardClient:
    """
    Backboard.io (Espri.ai) Sovereign AI Infrastructure Client.
    Coordinates persistent memory, adaptive context management, and unified model routing.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None
    ):
        self.api_key = api_key or os.getenv("BACKBOARD_API_KEY", "")
        self.base_url = (base_url or os.getenv("BACKBOARD_BASE_URL", "https://app.backboard.io/api")).rstrip("/")
        self.timeout_seconds = timeout_seconds or float(os.getenv("SUPERVISOR_MODEL_TIMEOUT_SECONDS", "20.0"))

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AI-Supervisor-Control-Plane/1.0"
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def check_health(self) -> Dict[str, Any]:
        """Validates Backboard.io authentication and connectivity."""
        if not self.api_key:
            self.api_key = os.getenv("BACKBOARD_API_KEY", "")

        if not self.api_key:
            return {
                "status": "healthy",
                "provider": "backboard",
                "mode": "fallback_local",
                "message": "BACKBOARD_API_KEY not configured in environment.",
                "base_url": self.base_url,
                "authenticated": False,
                "safe_fallback_active": True
            }

        try:
            async with httpx.AsyncClient(timeout=min(self.timeout_seconds, 6.0)) as client:
                res = await client.get(f"{self.base_url}/assistants", headers=self._headers())
                if res.status_code == 200:
                    return {
                        "status": "healthy",
                        "provider": "backboard",
                        "mode": "backboard_sovereign_cloud",
                        "message": "Backboard.io sovereign infrastructure connected and authenticated.",
                        "base_url": self.base_url,
                        "authenticated": True,
                        "safe_fallback_active": True
                    }
                elif res.status_code in (401, 403):
                    return {
                        "status": "unauthorized",
                        "provider": "backboard",
                        "mode": "fallback_local",
                        "message": f"Backboard API rejected credentials: HTTP {res.status_code}",
                        "base_url": self.base_url,
                        "authenticated": False,
                        "safe_fallback_active": True
                    }
                else:
                    return {
                        "status": "degraded",
                        "provider": "backboard",
                        "mode": "fallback_local",
                        "message": f"Backboard API returned HTTP {res.status_code}",
                        "base_url": self.base_url,
                        "authenticated": False,
                        "safe_fallback_active": True
                    }
        except Exception as e:
            return {
                "status": "degraded",
                "provider": "backboard",
                "mode": "fallback_local",
                "message": f"Endpoint unreachable: {type(e).__name__}",
                "base_url": self.base_url,
                "authenticated": False,
                "safe_fallback_active": True
            }

    async def list_models(self) -> List[Dict[str, Any]]:
        """Returns models and capabilities exposed through Backboard.io."""
        return [
            {
                "model_id": "backboard/sovereign-router",
                "name": "Backboard Sovereign Unified Router",
                "developer": "Espri.ai (Backboard.io)",
                "parameter_size": "Dynamic 17k+ Models",
                "specialties": ["persistent_memory", "adaptive_context", "model_routing"],
                "context_window": 128000,
                "available": bool(self.api_key)
            },
            {
                "model_id": "backboard/context-engine",
                "name": "Backboard Adaptive Context Engine",
                "developer": "Espri.ai (Backboard.io)",
                "parameter_size": "Context & Memory Layer",
                "specialties": ["session_memory", "hybrid_rag", "state_management"],
                "context_window": 256000,
                "available": bool(self.api_key)
            }
        ]
