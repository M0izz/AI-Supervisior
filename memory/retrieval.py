from typing import Any, Dict, List, Optional
from core.events.bus import EventBus
from core.events.schema import Event, EventType
from core.state.models import AgentContextPackage
from core.tasks.models import Task
from memory.provenance import FactStatus
from memory.store import MemoryStore


class ContextPackager:
    """Builds compact Agent Context Packages and Recovery Context Packages without full chat dump."""

    def __init__(self, memory_store: MemoryStore, event_bus: Optional[EventBus] = None):
        self.memory_store = memory_store
        self.event_bus = event_bus

    async def build_package(
        self,
        mission_id: str,
        goal: str,
        task: Task,
        constraints: List[str],
        recent_events: List[Dict[str, Any]],
        project_id: str = "",
    ) -> AgentContextPackage:
        mem_ctx = await self.memory_store.build_project_memory_context(
            mission_id=mission_id,
            project_id=project_id,
            task_id=task.id,
            task_objective=f"{task.title} {goal}",
        )

        relevant_memory = [
            {"fact": r["fact"], "status": r["status"], "confidence": r["confidence"]}
            for r in mem_ctx.relevant_facts
            if r["status"] in (FactStatus.VERIFIED.value, FactStatus.DECIDED.value)
        ]

        rejected = [
            {"approach": r["approach"], "reason": r.get("reason", "Failed during execution")}
            for r in mem_ctx.rejected_approaches
        ]

        # Combine configured constraints with memory-retrieved constraints
        all_constraints = list(set(constraints + mem_ctx.constraints))

        return AgentContextPackage(
            mission_id=mission_id,
            objective=goal,
            task=task.model_dump(),
            constraints=all_constraints,
            relevant_memory=relevant_memory,
            rejected_approaches=rejected,
            recent_events=recent_events[-5:],
            previous_attempts=[],
            verification_status={"task_attempts": task.attempts, "task_failures": task.failures}
        )

    async def build_recovery_package(
        self,
        mission_id: str,
        goal: str,
        task: Task,
        constraints: List[str],
        diagnosis: Dict[str, Any],
        recent_verification_evidence: Optional[Dict[str, Any]] = None
    ) -> AgentContextPackage:
        """
        Builds a dedicated Recovery Context Package containing:
        - original objective
        - current task
        - constraints
        - relevant verified facts (including diagnosis)
        - previous failed approaches
        - reviewer diagnosis and recommended strategy
        - verification evidence
        """
        pkg = await self.build_package(
            mission_id=mission_id,
            goal=goal,
            task=task,
            constraints=constraints,
            recent_events=[]
        )

        # Inject reviewer diagnosis as explicit verified/decided facts
        if "recommended_strategy" in diagnosis:
            pkg.relevant_memory.append({
                "fact": f"RECOMMENDED STRATEGY: {diagnosis['recommended_strategy']}",
                "status": "DECIDED",
                "confidence": diagnosis.get("confidence", 0.95)
            })

        if "rejected_approach" in diagnosis and diagnosis["rejected_approach"]:
            pkg.rejected_approaches.append({
                "approach": diagnosis["rejected_approach"],
                "reason": diagnosis.get("diagnosis", "Disproven by diagnosis")
            })

        pkg.verification_status = {
            "diagnosis": diagnosis.get("diagnosis"),
            "evidence": diagnosis.get("evidence", []),
            "recent_verification": recent_verification_evidence or {}
        }

        if self.event_bus:
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task.id,
                    type=EventType.RECOVERY_CONTEXT_CREATED,
                    payload={
                        "task_id": task.id,
                        "recommended_strategy": diagnosis.get("recommended_strategy"),
                        "rejected_approach": diagnosis.get("rejected_approach")
                    }
                )
            )

        return pkg
