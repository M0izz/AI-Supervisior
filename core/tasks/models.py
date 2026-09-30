from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field
import uuid


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"


def generate_task_id(seq: Optional[int] = None) -> str:
    if seq is not None:
        return f"TASK-{seq:03d}"
    return f"task_{uuid.uuid4().hex[:8]}"


class Task(BaseModel):
    id: str = Field(default_factory=generate_task_id)
    mission_id: str
    title: str
    description: str = ""
    assigned_agent_id: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = Field(default_factory=list)  # task_ids that must complete first
    expected_files: List[str] = Field(default_factory=list)  # Scope boundaries
    actual_modified_files: List[str] = Field(default_factory=list)
    attempts: int = 0
    failures: int = 0
    last_error_signature: Optional[str] = None
    order: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskGraph(BaseModel):
    mission_id: str
    tasks: Dict[str, Task] = Field(default_factory=dict)

    def add_task(self, task: Task) -> None:
        self.tasks[task.id] = task

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def get_ready_tasks(self) -> List[Task]:
        """Returns pending tasks whose dependencies are all COMPLETED."""
        completed_ids = {
            t.id for t in self.tasks.values() if t.status == TaskStatus.COMPLETED
        }
        ready = []
        for t in self.tasks.values():
            if t.status == TaskStatus.PENDING:
                if all(dep_id in completed_ids for dep_id in t.dependencies):
                    ready.append(t)
        # Order by sequence/order
        ready.sort(key=lambda x: x.order)
        return ready

    def is_all_completed(self) -> bool:
        return len(self.tasks) > 0 and all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
            for t in self.tasks.values()
        )

    def has_failures(self) -> bool:
        return any(t.status == TaskStatus.FAILED for t in self.tasks.values())

    def to_graph_data(self) -> Dict[str, Any]:
        """Export nodes and edges for React Flow rendering."""
        nodes = []
        edges = []
        for t in sorted(self.tasks.values(), key=lambda x: x.order):
            nodes.append({
                "id": t.id,
                "data": {
                    "label": t.title,
                    "status": t.status.value,
                    "agent": t.assigned_agent_id,
                    "attempts": t.attempts,
                    "failures": t.failures,
                },
                "position": {"x": t.order * 220, "y": 100},
            })
            for dep in t.dependencies:
                edges.append({
                    "id": f"edge-{dep}-{t.id}",
                    "source": dep,
                    "target": t.id,
                    "animated": t.status == TaskStatus.IN_PROGRESS,
                })
        return {"nodes": nodes, "edges": edges}
