import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity

logger = logging.getLogger("supervisor.registry")


class AgentType(str, Enum):
    PLANNER = "PLANNER"
    WORKER = "WORKER"
    REVIEWER = "REVIEWER"
    VERIFIER = "VERIFIER"
    SUPERVISOR = "SUPERVISOR"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None


class AgentStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    INVESTIGATING = "INVESTIGATING"
    PAUSED = "PAUSED"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    ANOMALOUS = "ANOMALOUS"
    OFFLINE = "OFFLINE"


class AgentRecord(BaseModel):
    agent_id: str
    agent_type: str = "WORKER"
    type: str = "WORKER"  # Compatibility alias
    model: str = "nemotron"
    status: AgentStatus = AgentStatus.IDLE
    current_task: Optional[str] = None
    task_id: Optional[str] = None
    mission_id: Optional[str] = None
    iterations: int = 0
    tool_calls: int = 0
    interventions: int = 0
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    health: AgentHealth = AgentHealth.HEALTHY
    active_files: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if self.agent_type and not self.type:
            self.type = self.agent_type
        elif self.type and not self.agent_type:
            self.agent_type = self.type
        if self.task_id and not self.current_task:
            self.current_task = self.task_id
        elif self.current_task and not self.task_id:
            self.task_id = self.current_task


class AgentRegistry:
    """
    Central registry for all agents across missions.
    Subscribes to the EventBus to maintain live measurable state,
    detect file contention between concurrent agents, and provide control hooks.
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._records: Dict[str, AgentRecord] = {}
        self._instances: Dict[str, Any] = {}  # agent_id -> BaseAgent instance
        self._file_locks: Dict[str, str] = {}  # file_path -> agent_id (contention detection)
        self._lock = asyncio.Lock()

        if self._event_bus:
            self._event_bus.subscribe_sync(self.handle_event)

    async def register_agent(
        self,
        agent_id: str,
        agent_type: str = "WORKER",
        model: str = "nemotron",
        mission_id: Optional[str] = None,
        agent_instance: Optional[Any] = None,
        status: AgentStatus = AgentStatus.IDLE,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentRecord:
        raw_val = agent_type.value if hasattr(agent_type, "value") else str(agent_type)
        norm_type = raw_val.upper() if raw_val.upper() in ("PLANNER", "WORKER", "REVIEWER", "VERIFIER", "SUPERVISOR") else raw_val
        async with self._lock:
            record = AgentRecord(
                agent_id=agent_id,
                agent_type=norm_type,
                type=norm_type,
                model=model,
                mission_id=mission_id,
                status=status,
                task_id=task_id,
                current_task=task_id,
                metadata=metadata or {}
            )
            self._records[agent_id] = record
            if agent_instance:
                self._instances[agent_id] = agent_instance
            logger.info(f"[REGISTRY] Registered agent {agent_id} (type={norm_type}, mission={mission_id})")
            return record

    async def get_agent(self, agent_id: str) -> Optional[AgentRecord]:
        async with self._lock:
            return self._records.get(agent_id)

    def get_agent_sync(self, agent_id: str) -> Optional[AgentRecord]:
        return self._records.get(agent_id)

    def get_agent_instance(self, agent_id: str) -> Optional[Any]:
        return self._instances.get(agent_id)

    async def list_agents(
        self,
        mission_id: Optional[str] = None,
        agent_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[AgentRecord]:
        async with self._lock:
            agents = list(self._records.values())
            if mission_id:
                agents = [a for a in agents if a.mission_id == mission_id]
            if agent_type:
                agents = [a for a in agents if (a.agent_type.lower() == agent_type.lower() or a.type.lower() == agent_type.lower())]
            if status:
                agents = [a for a in agents if a.status.value.lower() == status.lower()]
            return agents

    async def pause_agent(self, agent_id: str) -> bool:
        async with self._lock:
            record = self._records.get(agent_id)
            if not record:
                return False
            record.status = AgentStatus.PAUSED
            record.last_activity = datetime.now(timezone.utc)
            instance = self._instances.get(agent_id)
            if instance and hasattr(instance, "pause"):
                instance.pause()
            logger.info(f"[REGISTRY] Paused agent {agent_id}")
            return True

    async def resume_agent(self, agent_id: str, context_package: Optional[Any] = None) -> bool:
        async with self._lock:
            record = self._records.get(agent_id)
            if not record:
                return False
            record.status = AgentStatus.RUNNING
            record.last_activity = datetime.now(timezone.utc)
            instance = self._instances.get(agent_id)
            if instance and hasattr(instance, "resume"):
                instance.resume(context_package)
            logger.info(f"[REGISTRY] Resumed agent {agent_id}")
            return True

    async def check_file_contention(
        self,
        agent_id: str,
        file_path: str,
        mission_id: str
    ) -> Optional[str]:
        """
        Detects if another agent is already modifying the target file.
        Returns the conflicting agent_id if contention is detected, else None.
        """
        existing_holder = None
        contention_detected = False
        async with self._lock:
            existing_holder = self._file_locks.get(file_path)
            if existing_holder and existing_holder != agent_id:
                contention_detected = True
            else:
                self._file_locks[file_path] = agent_id
                record = self._records.get(agent_id)
                if record and file_path not in record.active_files:
                    record.active_files.append(file_path)

        if contention_detected:
            logger.warning(
                f"[REGISTRY] File contention detected: '{file_path}' active by {existing_holder}, requested by {agent_id}"
            )
            if self._event_bus:
                await self._event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        agent_id=agent_id,
                        type=EventType.FILE_CONTENTION_DETECTED,
                        severity=EventSeverity.WARNING,
                        payload={
                            "file_path": file_path,
                            "current_holder": existing_holder,
                            "requesting_agent": agent_id,
                            "action": "blocked"
                        }
                    )
                )
            return existing_holder
        return None

    async def release_file(self, agent_id: str, file_path: str) -> None:
        async with self._lock:
            if self._file_locks.get(file_path) == agent_id:
                del self._file_locks[file_path]
            record = self._records.get(agent_id)
            if record and file_path in record.active_files:
                record.active_files.remove(file_path)

    async def update_agent(
        self,
        agent_id: str,
        status: Optional[AgentStatus] = None,
        health: Optional[AgentHealth] = None,
        task_id: Optional[str] = None,
        model: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[AgentRecord]:
        async with self._lock:
            record = self._records.get(agent_id)
            if not record:
                return None
            if status is not None:
                record.status = status
            if health is not None:
                record.health = health
            if task_id is not None:
                record.task_id = task_id
                record.current_task = task_id
            if model is not None:
                record.model = model
            if metadata is not None:
                record.metadata.update(metadata)
            record.last_activity = datetime.now(timezone.utc)
            return record

    async def record_intervention(self, agent_id: str) -> None:
        async with self._lock:
            record = self._records.get(agent_id)
            if record:
                record.interventions += 1
                record.last_activity = datetime.now(timezone.utc)

    async def handle_event(self, event: Event) -> None:
        """Update live telemetry and agent records based on EventBus events."""
        target_agent = event.payload.get("target_agent") or event.payload.get("target_agent_id")
        agent_id = event.agent_id
        if (not agent_id or agent_id in ("supervisor", "system")) and target_agent:
            agent_id = target_agent

        if not agent_id or agent_id in ("supervisor", "system"):
            return

        async with self._lock:
            if agent_id not in self._records:
                # Dynamically discover and register agent
                guessed_type = "WORKER"
                if "reviewer" in agent_id.lower():
                    guessed_type = "REVIEWER"
                elif "verifier" in agent_id.lower():
                    guessed_type = "VERIFIER"
                elif "planner" in agent_id.lower():
                    guessed_type = "PLANNER"
                elif "supervisor" in agent_id.lower():
                    guessed_type = "SUPERVISOR"

                self._records[agent_id] = AgentRecord(
                    agent_id=agent_id,
                    agent_type=guessed_type,
                    type=guessed_type,
                    mission_id=event.mission_id
                )

            record = self._records[agent_id]
            record.last_activity = datetime.now(timezone.utc)
            if event.mission_id and not record.mission_id:
                record.mission_id = event.mission_id
            if event.task_id:
                record.current_task = event.task_id
                record.task_id = event.task_id

            # Update status
            if event.type == EventType.AGENT_STARTED or event.type == EventType.TASK_STARTED:
                record.status = AgentStatus.RUNNING
            elif event.type == EventType.AGENT_PAUSED:
                record.status = AgentStatus.PAUSED
            elif event.type == EventType.AGENT_RESUMED:
                record.status = AgentStatus.RUNNING
            elif event.type == EventType.AGENT_COMPLETED or event.type == EventType.TASK_COMPLETED:
                record.status = AgentStatus.COMPLETED
            elif event.type == EventType.AGENT_FAILED or event.type == EventType.TASK_FAILED:
                record.status = AgentStatus.FAILED
                record.health = AgentHealth.DEGRADED
            elif event.type == EventType.TASK_PROGRESS:
                record.iterations += 1
            elif event.type in (EventType.TOOL_CALL, EventType.TOOL_CALLED):
                record.tool_calls += 1
                # Check write/edit operations for contention
                tool_name = event.payload.get("tool", "")
                if tool_name in ("write_file", "edit_file"):
                    target_path = event.payload.get("arguments", {}).get("path")
                    if target_path:
                        # Schedule contention check asynchronously without blocking lock
                        asyncio.create_task(
                            self.check_file_contention(agent_id, target_path, event.mission_id or "")
                        )
            elif event.type == EventType.DANGER_DETECTED or event.type == EventType.SUPERVISOR_ALERT:
                record.health = AgentHealth.ANOMALOUS
                record.interventions += 1
            elif event.type in (EventType.SUPERVISOR_INTERVENTION, EventType.APPROVAL_REQUESTED, EventType.SUPERVISOR_HUMAN_REQUIRED):
                record.interventions += 1
            elif event.type == EventType.VERIFICATION_FAILED:
                record.health = AgentHealth.DEGRADED
