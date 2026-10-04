import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from core.events.bus import EventBus
from core.events.schema import Event, EventSeverity, EventType
from core.tasks.models import Task, TaskGraph, TaskStatus

logger = logging.getLogger("supervisor.tasks")


class TaskManager:
    """Manages tasks, dependencies, and DAG lifecycle for missions."""

    def __init__(self, event_bus: EventBus, repository: Optional[Any] = None):
        self._event_bus = event_bus
        self._repository = repository
        self._graphs: Dict[str, TaskGraph] = {}  # mission_id -> TaskGraph
        self._lock = asyncio.Lock()

    async def _persist_task(self, task: Optional[Task]) -> None:
        if self._repository and task:
            try:
                await self._repository.save(task)
            except Exception as e:
                logger.warning(f"Failed to persist task {task.id} to repository: {e}")

    async def initialize_mission_tasks(self, mission_id: str, tasks: List[Task]) -> TaskGraph:
        async with self._lock:
            graph = TaskGraph(mission_id=mission_id)
            for i, task in enumerate(tasks):
                task.mission_id = mission_id
                if not task.order:
                    task.order = i + 1
                graph.add_task(task)
            self._graphs[mission_id] = graph

        # Emit events for each task created and persist if repository configured
        for task in tasks:
            await self._persist_task(task)
            await self._event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task.id,
                    type=EventType.TASK_CREATED,
                    payload={
                        "task_id": task.id,
                        "title": task.title,
                        "dependencies": task.dependencies,
                        "expected_files": task.expected_files,
                        "order": task.order,
                    }
                )
            )
        return graph

    async def get_graph(self, mission_id: str) -> Optional[TaskGraph]:
        async with self._lock:
            graph = self._graphs.get(mission_id)
            if graph:
                return graph
            if self._repository:
                try:
                    tasks_data = await self._repository.list_by_mission(mission_id)
                    if tasks_data:
                        g = TaskGraph(mission_id=mission_id)
                        for d in tasks_data:
                            g.add_task(Task.model_validate(d))
                        self._graphs[mission_id] = g
                        return g
                except Exception as e:
                    logger.warning(f"Failed to load task graph for {mission_id} from repository: {e}")
            return None

    async def get_task(self, mission_id: str, task_id: str) -> Optional[Task]:
        async with self._lock:
            graph = self._graphs.get(mission_id)
            if graph:
                t = graph.get_task(task_id)
                if t:
                    return t
            if self._repository:
                try:
                    d = await self._repository.get(task_id)
                    if d:
                        return Task.model_validate(d)
                except Exception as e:
                    logger.warning(f"Failed to load task {task_id} from repository: {e}")
            return None

    async def start_task(self, mission_id: str, task_id: str, agent_id: str) -> Optional[Task]:
        async with self._lock:
            graph = self._graphs.get(mission_id)
            if not graph:
                return None
            task = graph.get_task(task_id)
            if not task:
                return None

            task.status = TaskStatus.IN_PROGRESS
            task.assigned_agent_id = agent_id
            task.started_at = datetime.now(timezone.utc)
            task.attempts += 1
            await self._persist_task(task)

        await self._event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                type=EventType.TASK_STARTED,
                payload={
                    "task_id": task_id,
                    "title": task.title,
                    "attempt": task.attempts,
                }
            )
        )
        return task

    async def route_and_start_task(
        self,
        mission_id: str,
        task_id: str,
        routing_engine: Any,
        task_requirements: Optional[Any] = None,
    ) -> Any:
        """
        Dynamically routes task to the best available agent using the RoutingEngine,
        records the decision, and transitions task to IN_PROGRESS.
        """
        task = await self.get_task(mission_id, task_id)
        if not task:
            return None, None

        from core.routing.models import RoutingRequest, TaskRequirements, RoutingDecisionType
        reqs = task_requirements or TaskRequirements.from_task(task)
        request = RoutingRequest(
            mission_id=mission_id,
            task_id=task_id,
            task_objective=task.title or "",
            task_requirements=reqs,
        )
        decision = await routing_engine.route(request)
        if decision.decision == RoutingDecisionType.ROUTE and decision.selected_agent_id:
            started = await self.start_task(mission_id, task_id, decision.selected_agent_id)
            return started, decision
        return task, decision

    async def complete_task(
        self,
        mission_id: str,
        task_id: str,
        summary: Optional[str] = None
    ) -> Optional[Task]:
        async with self._lock:
            graph = self._graphs.get(mission_id)
            if not graph:
                return None
            task = graph.get_task(task_id)
            if not task:
                return None

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)
            task.result_summary = summary
            await self._persist_task(task)

        await self._event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=task.assigned_agent_id,
                type=EventType.TASK_COMPLETED,
                payload={
                    "task_id": task_id,
                    "summary": summary,
                }
            )
        )
        return task

    async def verify_task(
        self,
        mission_id: str,
        task_id: str,
        caller_role: str = "VERIFIER",
        ci_passed: bool = False,
        tests_passed: bool = False,
        evidence: Optional[Dict[str, Any]] = None
    ) -> Task:
        """
        Mark task as VERIFIED.
        Enforces strict safety invariants:
        - Workers CANNOT mark work VERIFIED (only Verifier or Supervisor can).
        - Failed or missing CI/tests cannot produce VERIFIED.
        """
        if caller_role.upper() not in ("VERIFIER", "SUPERVISOR"):
            raise PermissionError(
                f"Role '{caller_role}' is not authorized to mark task as VERIFIED. "
                "Only Verifier or Supervisor can verify."
            )
        if not (ci_passed or tests_passed):
            raise ValueError(
                "Empirical verification requirement not met: "
                "CI or tests must pass before task can be marked VERIFIED."
            )

        async with self._lock:
            graph = self._graphs.get(mission_id)
            if not graph:
                raise ValueError(f"Mission graph '{mission_id}' not found.")
            task = graph.get_task(task_id)
            if not task:
                raise ValueError(f"Task '{task_id}' not found.")
            task.status = TaskStatus.VERIFIED
            task.completed_at = datetime.now(timezone.utc)
            task.metadata["verified"] = True
            task.metadata["verification_evidence"] = evidence or {}
            await self._persist_task(task)

        await self._event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=caller_role,
                type=EventType.VERIFICATION_RESULT,
                severity=EventSeverity.INFO,
                payload={
                    "task_id": task_id,
                    "status": "VERIFIED",
                    "evidence": evidence or {}
                }
            )
        )
        return task

    async def fail_task(
        self,
        mission_id: str,
        task_id: str,
        error_signature: Optional[str] = None,
        reason: Optional[str] = None
    ) -> Optional[Task]:
        async with self._lock:
            graph = self._graphs.get(mission_id)
            if not graph:
                return None
            task = graph.get_task(task_id)
            if not task:
                return None

            task.failures += 1
            task.last_error_signature = error_signature
            await self._persist_task(task)

        await self._event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=task.assigned_agent_id,
                type=EventType.TASK_FAILED,
                severity=EventSeverity.WARNING,
                payload={
                    "task_id": task_id,
                    "error_signature": error_signature,
                    "reason": reason,
                    "attempt": task.attempts,
                    "failures": task.failures,
                }
            )
        )
        return task

    async def reopen_task(
        self,
        mission_id: str,
        task_id: str,
        reason: str = "Verification failed - worker claim rejected"
    ) -> Optional[Task]:
        async with self._lock:
            graph = self._graphs.get(mission_id)
            if not graph:
                return None
            task = graph.get_task(task_id)
            if not task:
                return None
            task.status = TaskStatus.IN_PROGRESS
            task.failures += 1
            task.metadata["reopened"] = True
            task.metadata["reopen_reason"] = reason
            await self._persist_task(task)

        await self._event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=task.assigned_agent_id,
                type=EventType.TASK_REOPENED,
                severity=EventSeverity.WARNING,
                payload={
                    "task_id": task_id,
                    "reason": reason,
                    "failures": task.failures
                }
            )
        )
        return task

    async def record_file_modification(
        self,
        mission_id: str,
        task_id: str,
        file_path: str
    ) -> None:
        async with self._lock:
            graph = self._graphs.get(mission_id)
            if graph:
                task = graph.get_task(task_id)
                if task and file_path not in task.actual_modified_files:
                    task.actual_modified_files.append(file_path)
