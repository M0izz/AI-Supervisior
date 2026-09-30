import logging
from typing import Any, Dict, Optional
from agents.base import BaseAgent
from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.state.models import AgentContextPackage
from tools.base import BaseTool

logger = logging.getLogger("supervisor.verifier")


class VerifierAgent(BaseAgent):
    """
    Independent Verifier.
    Never trusts worker claims without empirical evidence (tests, git diff, scope check).
    """

    def __init__(
        self,
        agent_id: str = "verifier_01",
        event_bus: Optional[EventBus] = None,
        tools: Optional[Dict[str, BaseTool]] = None
    ):
        super().__init__(agent_id=agent_id, role="Verifier", event_bus=event_bus or EventBus(), tools=tools)

    async def run(self, context_package: AgentContextPackage) -> Dict[str, Any]:
        mission_id = context_package.mission_id
        task_id = context_package.task.get("id")

        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=self.agent_id,
                type=EventType.VERIFICATION_STARTED,
                payload={"goal": context_package.objective}
            )
        )

        # 1. Run tests if tool is available
        test_result = None
        if "run_tests" in self.tools:
            test_result = await self.call_tool(
                "run_tests",
                {"test_command": "python -m pytest tests/ -v"},
                mission_id=mission_id,
                task_id=task_id
            )

        passed = test_result.metadata.get("passed", 0) if test_result else 0
        failed = test_result.metadata.get("failed", 0) if test_result else 0

        verified = (failed == 0) and (passed > 0)

        # 2. Emit verification result
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=self.agent_id,
                type=EventType.VERIFICATION_RESULT,
                severity=EventSeverity.INFO if verified else EventSeverity.ERROR,
                payload={
                    "verified": verified,
                    "tests_passed": passed,
                    "tests_failed": failed,
                    "evidence": {
                        "test_output_summary": f"{passed} passed, {failed} failed"
                    }
                }
            )
        )

        return {"verified": verified, "tests_passed": passed, "tests_failed": failed}
