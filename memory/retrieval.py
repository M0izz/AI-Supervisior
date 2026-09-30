from typing import Any, Dict, List, Optional
from core.state.models import AgentContextPackage
from core.tasks.models import Task
from memory.provenance import FactStatus
from memory.store import MemoryStore


class ContextPackager:
    """Builds the compact Agent Context Package without full chat dump."""

    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store

    async def build_package(
        self,
        mission_id: str,
        goal: str,
        task: Task,
        constraints: List[str],
        recent_events: List[Dict[str, Any]]
    ) -> AgentContextPackage:
        mem_records = await self.memory_store.get_by_mission(mission_id)

        relevant_memory = [
            {"fact": r.fact, "status": r.status.value, "confidence": r.confidence}
            for r in mem_records
            if r.status in (FactStatus.VERIFIED, FactStatus.DECIDED)
        ]

        rejected = [
            {"approach": r.fact, "reason": r.details or "Failed during execution"}
            for r in mem_records
            if r.status == FactStatus.REJECTED or r.category == "rejected_approach"
        ]

        return AgentContextPackage(
            mission_id=mission_id,
            objective=goal,
            task=task.model_dump(),
            constraints=constraints,
            relevant_memory=relevant_memory,
            rejected_approaches=rejected,
            recent_events=recent_events[-5:],
            previous_attempts=[],
            verification_status={"task_attempts": task.attempts, "task_failures": task.failures}
        )
