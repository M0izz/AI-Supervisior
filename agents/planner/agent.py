from typing import Any, Dict, List, Optional
from agents.base import BaseAgent
from core.events.bus import EventBus
from core.state.models import AgentContextPackage
from core.tasks.models import Task, generate_task_id


class PlannerAgent(BaseAgent):
    """Planner creates structured DAG tasks from high-level mission goals."""

    def __init__(self, agent_id: str = "planner_01", event_bus: Optional[EventBus] = None):
        super().__init__(agent_id=agent_id, role="Planner", event_bus=event_bus or EventBus())

    async def run(self, context_package: AgentContextPackage) -> Dict[str, Any]:
        mission_id = context_package.mission_id
        goal = context_package.objective

        await self.emit_action(
            mission_id=mission_id,
            task_id=None,
            description=f"Synthesizing execution plan for goal: '{goal}'"
        )

        # Standard structured task plan for software engineering tasks
        plan_tasks = [
            Task(id="TASK-001", mission_id=mission_id, title="Inspect existing data model", order=1, expected_files=["src/models.py"]),
            Task(id="TASK-002", mission_id=mission_id, title="Design CSV parser", dependencies=["TASK-001"], order=2, expected_files=["src/parser.py"]),
            Task(id="TASK-003", mission_id=mission_id, title="Implement importer", dependencies=["TASK-002"], order=3, expected_files=["src/importer.py"]),
            Task(id="TASK-004", mission_id=mission_id, title="Add validation", dependencies=["TASK-003"], order=4, expected_files=["src/validator.py"]),
            Task(id="TASK-005", mission_id=mission_id, title="Run tests", dependencies=["TASK-004"], order=5, expected_files=["tests/test_parser.py"]),
            Task(id="TASK-006", mission_id=mission_id, title="Verify integration", dependencies=["TASK-005"], order=6, expected_files=["src/main.py"]),
        ]

        await self.emit_action(
            mission_id=mission_id,
            task_id=None,
            description=f"Plan synthesized with {len(plan_tasks)} structured tasks."
        )

        return {"tasks": plan_tasks, "count": len(plan_tasks)}
