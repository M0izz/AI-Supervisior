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
    PLANNER = "planner"
    WORKER = "worker"
    REVIEWER = "reviewer"
    VERIFIER = "verifier"
    SUPERVISOR = "supervisor"


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
    type: str = "worker"
    model: str = "nemotron"
    status: AgentStatus = AgentStatus.IDLE
    current_task: Optional[str] = None
    mission_id: Optional[str] = None
    iterations: int = 0
    tool_calls: int = 0
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    health: AgentHealth = AgentHealth.HEALTHY
    active_files: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
        agent_type: str = "worker",
        model: str = "nemotron",
        mission_id: Optional[str] = None,
        agent_instance: Optional[Any] = None,
        status: AgentStatus = AgentStatus.IDLE
    ) -> AgentRecord:
        async with self._lock:
            record = AgentRecord(
                agent_id=agent_id,
                type=agent_type,
                model=model,
                mission_id=mission_id,
                status=status
            )
            self._records[agent_id] = record
            if agent_instance:
                self._instances[agent_id] = agent_instance
            logger.info(f"[REGISTRY] Registered agent {agent_id} (type={agent_type}, mission={mission_id})")
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
                agents = [a for a in agents if a.type == agent_type]
            if status:
                agents = [a for a in agents if a.status.value == status]
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
        async with self._lock:
            existing_holder = self._file_locks.get(file_path)
            if existing_holder and existing_holder != agent_id:
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
            self._file_locks[file_path] = agent_id
            record = self._records.get(agent_id)
            if record and file_path not in record.active_files:
                record.active_files.append(file_path)
            return None

    async def release_file(self, agent_id: str, file_path: str) -> None:
        async with self._lock:
            if self._file_locks.get(file_path) == agent_id:
                del self._file_locks[file_path]
            record = self._records.get(agent_id)
            if record and file_path in record.active_files:
                record.active_files.remove(file_path)

    async def handle_event(self, event: Event) -> None:
        """Update live telemetry and agent records based on EventBus events."""
        agent_id = event.agent_id
        if not agent_id or agent_id == "supervisor" or agent_id == "system":
            return

        async with self._lock:
            if agent_id not in self._records:
                # Dynamically discover and register agent
                guessed_type = "worker"
                if "reviewer" in agent_id:
                    guessed_type = "reviewer"
                elif "verifier" in agent_id:
                    guessed_type = "verifier"
                elif "planner" in agent_id:
                    guessed_type = "planner"

                self._records[agent_id] = AgentRecord(
                    agent_id=agent_id,
                    type=guessed_type,
                    mission_id=event.mission_id
                )

            record = self._records[agent_id]
            record.last_activity = datetime.now(timezone.utc)
            if event.mission_id and not record.mission_id:
                record.mission_id = event.mission_id
            if event.task_id:
                record.current_task = event.task_id

            # Update status
            if event.type == EventType.AGENT_STARTED:
                record.status = AgentStatus.RUNNING
            elif event.type == EventType.AGENT_PAUSED:
                record.status = AgentStatus.PAUSED
            elif event.type == EventType.AGENT_RESUMED:
                record.status = AgentStatus.RUNNING
            elif event.type == EventType.AGENT_COMPLETED:
                record.status = AgentStatus.COMPLETED
            elif event.type == EventType.AGENT_FAILED:
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
            elif event.type == EventType.VERIFICATION_FAILED:
                record.health = AgentHealth.DEGRADED
