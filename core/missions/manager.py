import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from core.events.bus import EventBus
from core.events.schema import Event, EventSeverity, EventType
from core.missions.models import Mission, MissionConstraints, MissionStatus

logger = logging.getLogger("supervisor.missions")


class MissionManager:
    """Manages mission lifecycles, states, and event notifications."""

    def __init__(self, event_bus: EventBus, repository: Optional[Any] = None):
        self._event_bus = event_bus
        self._repository = repository
        self._missions: Dict[str, Mission] = {}
        self._lock = asyncio.Lock()

    async def create_mission(
        self,
        title: str,
        goal: str,
        repository_path: str = "./demo/sample-project",
        constraints: Optional[MissionConstraints] = None
    ) -> Mission:
        async with self._lock:
            mission = Mission(
                title=title,
                goal=goal,
                repository_path=repository_path,
                constraints=constraints or MissionConstraints(),
            )
            self._missions[mission.id] = mission

            if self._repository:
                try:
                    await self._repository.save(mission)
                except Exception as e:
                    logger.warning(f"Failed to persist mission {mission.id} to repository: {e}")

        await self._event_bus.publish(
            Event(
                mission_id=mission.id,
                type=EventType.MISSION_CREATED,
                payload={
                    "mission_id": mission.id,
                    "title": mission.title,
                    "goal": mission.goal,
                    "repository_path": mission.repository_path,
                }
            )
        )
        return mission

    async def get_mission(self, mission_id: str) -> Optional[Mission]:
        async with self._lock:
            m = self._missions.get(mission_id)
            if m:
                return m
            if self._repository:
                try:
                    data = await self._repository.get(mission_id)
                    if data:
                        m = Mission.model_validate(data)
                        self._missions[m.id] = m
                        return m
                except Exception as e:
                    logger.warning(f"Failed to load mission {mission_id} from repository: {e}")
            return None

    async def list_missions(self) -> List[Mission]:
        async with self._lock:
            if not self._missions and self._repository:
                try:
                    data_list = await self._repository.list_all()
                    for d in data_list:
                        m = Mission.model_validate(d)
                        self._missions[m.id] = m
                except Exception as e:
                    logger.warning(f"Failed to load missions from repository: {e}")
            return list(self._missions.values())

    def is_valid_transition(self, current: MissionStatus, target: MissionStatus) -> bool:
        if current == target:
            return True
        if current in (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED):
            return False
        return True

    async def assign_agent(self, mission_id: str, agent_id: str) -> Optional[Mission]:
        async with self._lock:
            mission = self._missions.get(mission_id)
            if not mission:
                return None
            if agent_id not in mission.assigned_agents:
                mission.assigned_agents.append(agent_id)
            mission.active_agent_id = agent_id
            mission.updated_at = datetime.now(timezone.utc)

            if self._repository:
                try:
                    await self._repository.save(mission)
                except Exception as e:
                    logger.warning(f"Failed to update mission {mission_id} agent assignment in repository: {e}")
            return mission

    async def update_status(
        self,
        mission_id: str,
        new_status: MissionStatus,
        reason: Optional[str] = None,
        force: bool = False
    ) -> Optional[Mission]:
        async with self._lock:
            mission = self._missions.get(mission_id)
            if not mission:
                return None

            old_status = mission.status
            if not force and not self.is_valid_transition(old_status, new_status):
                logger.warning(
                    f"[MISSION] Invalid transition from terminal/incompatible state {old_status.value} -> {new_status.value} for {mission_id}"
                )
                return mission

            mission.status = new_status
            mission.updated_at = datetime.now(timezone.utc)

            if new_status == MissionStatus.RUNNING and not mission.metrics.started_at:
                mission.metrics.started_at = mission.updated_at
            elif new_status in (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED):
                mission.metrics.completed_at = mission.updated_at

            if self._repository:
                try:
                    await self._repository.save(mission)
                except Exception as e:
                    logger.warning(f"Failed to persist mission status change to repository: {e}")

        # Determine severity and event type
        severity = EventSeverity.INFO
        if new_status in (MissionStatus.PAUSED, MissionStatus.AWAITING_APPROVAL, MissionStatus.WAITING_APPROVAL, MissionStatus.INVESTIGATING, MissionStatus.BLOCKED):
            severity = EventSeverity.WARNING
        elif new_status == MissionStatus.FAILED:
            severity = EventSeverity.ERROR

        # Publish MISSION_STATUS_CHANGED
        await self._event_bus.publish(
            Event(
                mission_id=mission_id,
                type=EventType.MISSION_STATUS_CHANGED,
                severity=severity,
                payload={
                    "old_status": old_status.value,
                    "new_status": new_status.value,
                    "reason": reason,
                }
            )
        )

        # Publish specific lifecycle event if applicable
        specific_event_type = None
        if new_status == MissionStatus.RUNNING and old_status in (MissionStatus.CREATED, MissionStatus.PENDING, MissionStatus.STARTING, MissionStatus.PLANNING):
            specific_event_type = EventType.MISSION_STARTED
        elif new_status == MissionStatus.PAUSED:
            specific_event_type = EventType.MISSION_PAUSED
        elif new_status == MissionStatus.RUNNING and old_status == MissionStatus.PAUSED:
            specific_event_type = EventType.MISSION_RESUMED
        elif new_status == MissionStatus.COMPLETED:
            specific_event_type = EventType.MISSION_COMPLETED
        elif new_status == MissionStatus.FAILED:
            specific_event_type = EventType.MISSION_FAILED

        if specific_event_type:
            await self._event_bus.publish(
                Event(
                    mission_id=mission_id,
                    type=specific_event_type,
                    severity=severity,
                    payload={
                        "status": new_status.value,
                        "reason": reason
                    }
                )
            )

        return mission

    async def plan_mission(self, mission_id: str, reason: str = "Mission planning initiated") -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.PLANNING, reason=reason)

    async def start_mission(self, mission_id: str) -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.RUNNING, reason="Mission started")

    async def investigate_mission(self, mission_id: str, reason: str = "Supervisor investigating anomaly") -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.INVESTIGATING, reason=reason)

    async def wait_approval_mission(self, mission_id: str, reason: str = "Awaiting human operator approval") -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.WAITING_APPROVAL, reason=reason)

    async def pause_mission(self, mission_id: str, reason: str) -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.PAUSED, reason=reason)

    async def resume_mission(self, mission_id: str) -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.RUNNING, reason="Resumed by operator or supervisor")

    async def recover_mission(self, mission_id: str, reason: str = "Initiating recovery") -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.RECOVERING, reason=reason)

    async def verify_mission(self, mission_id: str, reason: str = "Initiating verification") -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.VERIFYING, reason=reason)

    async def block_mission(self, mission_id: str, reason: str = "Mission blocked") -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.BLOCKED, reason=reason)

    async def fail_mission(self, mission_id: str, reason: str = "Mission failed") -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.FAILED, reason=reason)

    async def cancel_mission(self, mission_id: str, reason: str = "Mission cancelled by operator") -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.CANCELLED, reason=reason)

    async def complete_mission(self, mission_id: str, summary: Optional[str] = None) -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.COMPLETED, reason=summary or "Verified and completed")
