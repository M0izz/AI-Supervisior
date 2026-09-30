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

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._graphs: Dict[str, TaskGraph] = {}  # mission_id -> TaskGraph
        self._lock = asyncio.Lock()

    async def initialize_mission_tasks(self, mission_id: str, tasks: List[Task]) -> TaskGraph:
        async with self._lock:
            graph = TaskGraph(mission_id=mission_id)
            for i, task in enumerate(tasks):
                task.mission_id = mission_id
                if not task.order:
                    task.order = i + 1
                graph.add_task(task)
            self._graphs[mission_id] = graph

        # Emit events for each task created
        for task in tasks:
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
            return self._graphs.get(mission_id)

    async def get_task(self, mission_id: str, task_id: str) -> Optional[Task]:
        async with self._lock:
            graph = self._graphs.get(mission_id)
            if graph:
                return graph.get_task(task_id)
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
