import logging
from typing import Any, Dict, List, Optional
from integrations.nebius.provider import BaseReasoningProvider, MockReasoningProvider, NebiusNemotronProvider, ReasoningDecision
from supervisor.decisions import SupervisorAction, SupervisorDecision

logger = logging.getLogger("supervisor.reasoning")


class SupervisoryReasoner:
    """
    Layer B: Nemotron reasoning engine.
    Constructs compact structured supervisory context and obtains high-confidence decisions.
    """

    def __init__(self, provider: Optional[BaseReasoningProvider] = None):
        self.provider = provider or MockReasoningProvider()

    def build_supervisory_context(
        self,
        mission_goal: str,
        current_task_title: str,
        agent_id: str,
        recent_actions: List[Dict[str, Any]],
        error_signature: Optional[str],
        constraints: List[str],
        anomaly_type: str
    ) -> Dict[str, Any]:
        return {
            "mission": mission_goal,
            "current_task": current_task_title,
            "agent": agent_id,
            "recent_actions": recent_actions[-6:],
            "error_signature": error_signature or "NONE",
            "project_constraints": constraints,
            "anomaly_type": anomaly_type,
            "available_actions": [a.value for a in SupervisorAction]
        }

    async def decide(self, context: Dict[str, Any]) -> SupervisorDecision:
        decision_raw: ReasoningDecision = await self.provider.reason_about_situation(context)

        # Map string decision to SupervisorAction
        action_map = {
            "CONTINUE": SupervisorAction.CONTINUE,
            "RETRY": SupervisorAction.RETRY,
            "CHANGE_STRATEGY": SupervisorAction.CHANGE_STRATEGY,
            "DELEGATE": SupervisorAction.DELEGATE,
            "ROLLBACK": SupervisorAction.ROLLBACK,
            "PAUSE": SupervisorAction.PAUSE,
            "REQUEST_APPROVAL": SupervisorAction.REQUEST_APPROVAL,
            "COMPLETE": SupervisorAction.COMPLETE,
        }
        action = action_map.get(decision_raw.decision.upper(), SupervisorAction.PAUSE)

        return SupervisorDecision(
            action=action,
            severity=decision_raw.severity,
            confidence=decision_raw.confidence,
            reason=decision_raw.reason,
            target_agent=decision_raw.target_agent,
            recommended_strategy=decision_raw.recommended_action,
            source="nemotron-4-340b" if isinstance(self.provider, NebiusNemotronProvider) else "mock_nemotron"
        )

    async def check_health(self) -> Dict[str, Any]:
        if hasattr(self.provider, "check_health"):
            return await self.provider.check_health()
        return {
            "status": "healthy",
            "provider": type(self.provider).__name__,
            "mode": "custom"
        }
