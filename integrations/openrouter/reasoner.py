import json
import logging
import os
from typing import Any, Dict, Optional
import httpx
from integrations.nebius.provider import BaseReasoningProvider, ReasoningDecision, MockReasoningProvider
from integrations.openrouter.client import OpenRouterClient

logger = logging.getLogger("supervisor.integrations.openrouter.reasoner")


class OpenRouterReasoner(BaseReasoningProvider):
    """
    Supervisory Reasoning Provider backed by OpenRouter inference.
    Supports routing reasoning through Claude 3.7 Sonnet, DeepSeek R1, GPT-4o, or Nemotron.
    """

    def __init__(
        self,
        client: Optional[OpenRouterClient] = None,
        model: Optional[str] = None
    ):
        self.client = client or OpenRouterClient()
        self.model = model or os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.7-sonnet")

    async def check_health(self) -> Dict[str, Any]:
        """Health check matching standard provider response schema."""
        health = await self.client.check_health()
        return {
            "status": health.get("status", "healthy"),
            "provider": "openrouter",
            "model": self.model,
            "mode": health.get("mode", "fallback_local"),
            "base_url": self.client.base_url,
            "authenticated": health.get("authenticated", False),
            "safe_fallback_active": True
        }

    async def reason_about_situation(self, prompt_context: Dict[str, Any]) -> ReasoningDecision:
        """Performs situation reasoning and supervisory decision making."""
        if not self.client.api_key:
            logger.warning("No OPENROUTER_API_KEY configured; using safe MockReasoningProvider fallback.")
            return await MockReasoningProvider().reason_about_situation(prompt_context)

        system_prompt = (
            "You are the AI Work Supervisor Reasoning Engine powered by OpenRouter Multi-Model Inference.\n"
            "Your role is to watch autonomous coding agents, detect failure loops or drift, and make deterministic supervisory decisions.\n"
            "You MUST respond ONLY with valid JSON conforming to this schema:\n"
            "{\n"
            '  "decision": "CONTINUE" | "RETRY" | "CHANGE_STRATEGY" | "DELEGATE" | "ROLLBACK" | "PAUSE" | "REQUEST_APPROVAL" | "COMPLETE",\n'
            '  "severity": "low" | "medium" | "high" | "critical",\n'
            '  "confidence": 0.0 to 1.0,\n'
            '  "reason": "concise explanation of why you intervened",\n'
            '  "recommended_action": "actionable instruction",\n'
            '  "target_agent": "reviewer_01" | "worker_01" | null\n'
            "}"
        )

        user_content = json.dumps(prompt_context, indent=2)

        try:
            async with httpx.AsyncClient(timeout=self.client.timeout_seconds) as client:
                res = await client.post(
                    f"{self.client.base_url}/chat/completions",
                    headers=self.client._headers(),
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Supervisory Context:\n{user_content}"}
                        ],
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"}
                    }
                )

                if res.status_code != 200:
                    logger.warning(f"OpenRouter API error HTTP {res.status_code}: {res.text[:120]}; falling back to local mock.")
                    return await MockReasoningProvider().reason_about_situation(prompt_context)

                result_json = res.json()
                content = result_json["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return ReasoningDecision.model_validate(parsed)
        except Exception as e:
            logger.warning(f"OpenRouter reasoning exception: {e}; falling back to local mock.")
            return await MockReasoningProvider().reason_about_situation(prompt_context)
