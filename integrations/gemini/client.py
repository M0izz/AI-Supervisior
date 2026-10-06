import os
import logging
import httpx
from typing import Any, Dict, List, Optional

logger = logging.getLogger("supervisor.integrations.gemini.client")


class GeminiClient:
    """
    Lightweight, resilient HTTP client for Google Gemini API.
    Operates offline-first when GEMINI_API_KEY is not configured in environment.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 0)

    async def check_health(self) -> Dict[str, Any]:
        """Probes Gemini connectivity without throwing unhandled exceptions."""
        if not self.is_configured:
            return {
                "status": "NOT_CONFIGURED",
                "message": "GEMINI_API_KEY not configured in environment.",
                "available": False
            }

        try:
            url = f"{self.BASE_URL}/models?key={self.api_key}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return {
                        "status": "CONNECTED",
                        "message": "Google Gemini API connected and authenticated.",
                        "available": True
                    }
                elif resp.status_code in (401, 403):
                    return {
                        "status": "AUTHENTICATION_REQUIRED",
                        "message": "Invalid Google Gemini API credential.",
                        "available": False
                    }
                else:
                    return {
                        "status": "ERROR",
                        "message": f"Gemini API returned HTTP {resp.status_code}",
                        "available": False
                    }
        except Exception as e:
            logger.debug(f"Gemini API probe exception (offline mode preserved): {e}")
            return {
                "status": "UNAVAILABLE",
                "message": f"Connection error: {e}",
                "available": False
            }

    async def generate_content(
        self,
        model: str = "gemini-1.5-flash",
        prompt: str = "",
        system_instruction: Optional[str] = None
    ) -> Optional[str]:
        """Invokes Gemini generateContent if key is present."""
        if not self.is_configured:
            return None

        url = f"{self.BASE_URL}/models/{model}:generateContent?key={self.api_key}"
        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                logger.warning(f"Gemini call failed with HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            logger.warning(f"Gemini generation exception: {e}")

        return None
