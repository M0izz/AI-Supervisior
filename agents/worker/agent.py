import logging
from typing import Any, Dict, Optional
from agents.base import BaseAgent
from core.events.bus import EventBus
from core.state.models import AgentContextPackage
from tools.base import BaseTool

logger = logging.getLogger("supervisor.worker")


class WorkerAgent(BaseAgent):
    """Executes coding tasks via sandbox tools."""

    def __init__(
        self,
        agent_id: str = "worker_01",
        event_bus: Optional[EventBus] = None,
        tools: Optional[Dict[str, BaseTool]] = None
    ):
        super().__init__(agent_id=agent_id, role="Worker", event_bus=event_bus or EventBus(), tools=tools)

    async def run(self, context_package: AgentContextPackage) -> Dict[str, Any]:
        mission_id = context_package.mission_id
        task = context_package.task
        task_id = task.get("id", "task_unknown")

        await self.emit_action(
            mission_id=mission_id,
            task_id=task_id,
            description=f"Worker executing task: {task.get('title')}"
        )

        return {"status": "in_progress", "task_id": task_id}
