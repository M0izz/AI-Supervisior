import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("supervisor.nebius")


class ReasoningDecision(BaseModel):
    decision: str = "CONTINUE"
    severity: str = "medium"
    confidence: float = 0.95
    reason: str
    recommended_action: Optional[str] = None
    target_agent: Optional[str] = None


class BaseReasoningProvider(ABC):
    """Abstract interface for supervisory reasoning backends."""

    @abstractmethod
    async def reason_about_situation(self, prompt_context: Dict[str, Any]) -> ReasoningDecision:
        """Analyze situation and return structured decision."""
        pass


class MockReasoningProvider(BaseReasoningProvider):
    """
    Local mock reasoning engine for tests and offline development.
    Produces deterministic Nemotron-like structured decisions.
    """

    async def reason_about_situation(self, prompt_context: Dict[str, Any]) -> ReasoningDecision:
        anomaly = prompt_context.get("anomaly_type")
        error_sig = prompt_context.get("error_signature", "")

        if anomaly == "LOOP_DETECTED":
            return ReasoningDecision(
                decision="DELEGATE",
                severity="medium",
                confidence=0.92,
                reason=f"The worker repeated the identical approach without changing the failure signature: '{error_sig}'.",
                recommended_action="Delegate root-cause diagnosis to reviewer agent to check file encodings.",
                target_agent="reviewer_01"
            )
        elif anomaly == "NO_PROGRESS":
            return ReasoningDecision(
                decision="CHANGE_STRATEGY",
                severity="medium",
                confidence=0.89,
                reason="Multiple test attempts showed no improvement in passing test count.",
                recommended_action="Formulate alternative parsing approach without modifying database schema.",
                target_agent="worker_01"
            )
        elif anomaly == "DANGEROUS_ACTION":
            return ReasoningDecision(
                decision="REQUEST_APPROVAL",
                severity="high",
                confidence=0.98,
                reason="Proposed command or file write violates safety policies.",
                recommended_action="Await operator confirmation before proceeding.",
                target_agent=None
            )
        elif anomaly == "SCOPE_VIOLATION":
            return ReasoningDecision(
                decision="PAUSE",
                severity="high",
                confidence=0.94,
                reason="Worker attempted modification outside declared task boundaries.",
                recommended_action="Pause worker and require scope validation.",
                target_agent=None
            )
        elif anomaly == "BUDGET_WARNING":
            return ReasoningDecision(
                decision="PAUSE",
                severity="high",
                confidence=0.95,
                reason="Task exceeded configured turn or time budget.",
                recommended_action="Pause execution for operator budget review.",
                target_agent=None
            )

        return ReasoningDecision(
            decision="CONTINUE",
            severity="low",
            confidence=0.88,
            reason="Progressing within acceptable tolerances.",
            recommended_action=None,
            target_agent=None
        )


class NebiusNemotronProvider(BaseReasoningProvider):
    """
    Nebius hosted AI infrastructure calling NVIDIA Nemotron.
    Forces structured JSON output parsing.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None
    ):
        self.api_key = api_key or os.getenv("NEBIUS_API_KEY", "")
        self.base_url = base_url or os.getenv("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1")
        self.model = model or os.getenv("NEBIUS_MODEL", "nvidia/nemotron-4-340b-instruct")
        self.timeout_seconds = timeout_seconds or float(os.getenv("SUPERVISOR_MODEL_TIMEOUT_SECONDS", "20.0"))

    async def reason_about_situation(self, prompt_context: Dict[str, Any]) -> ReasoningDecision:
        if not self.api_key:
            logger.warning("No NEBIUS_API_KEY provided; falling back to MockReasoningProvider.")
            return await MockReasoningProvider().reason_about_situation(prompt_context)

        system_prompt = (
            "You are the AI Work Supervisor Reasoning Engine powered by NVIDIA Nemotron on Nebius.\n"
            "Your role is to watch what autonomous agents do, detect failure or drift, and make supervisory decisions.\n"
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
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
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
                    logger.error(f"Nebius API error {res.status_code}: {res.text}")
                    return await MockReasoningProvider().reason_about_situation(prompt_context)

                result_json = res.json()
                content = result_json["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return ReasoningDecision.model_validate(parsed)
        except Exception as e:
            logger.error(f"Exception contacting Nebius Nemotron: {e}")
            return await MockReasoningProvider().reason_about_situation(prompt_context)
