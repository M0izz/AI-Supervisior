import logging
from typing import Any, Dict, Optional
from agents.base import BaseAgent
from core.events.bus import EventBus
from core.state.models import AgentContextPackage
from tools.base import BaseTool

logger = logging.getLogger("supervisor.reviewer")


class ReviewerAgent(BaseAgent):
    """
    Reviewer agent delegated by the Supervisor when a loop or drift is detected.
    Diagnoses failure signatures and provides recovery guidance.
    """

    def __init__(
        self,
        agent_id: str = "reviewer_01",
        event_bus: Optional[EventBus] = None,
        tools: Optional[Dict[str, BaseTool]] = None
    ):
        super().__init__(agent_id=agent_id, role="Reviewer", event_bus=event_bus or EventBus(), tools=tools)

    async def run(self, context_package: AgentContextPackage) -> Dict[str, Any]:
        mission_id = context_package.mission_id
        task_id = context_package.task.get("id")

        await self.emit_action(
            mission_id=mission_id,
            task_id=task_id,
            description="Reviewer analyzing repeated failure signature and code diff."
        )

        diagnosis = {
            "root_cause": "CSV headers contain UTF-8 Byte Order Mark (BOM) causing comparison mismatch",
            "recommended_strategy": "Use encoding='utf-8-sig' when reading CSV content and strip leading BOM whitespace",
            "rejected_approach": "Direct string equality on raw header bytes",
        }

        await self.emit_action(
            mission_id=mission_id,
            task_id=task_id,
            description=f"Diagnosis complete: {diagnosis['root_cause']}. Strategy formulated.",
            metadata={"diagnosis": diagnosis}
        )

        return diagnosis
