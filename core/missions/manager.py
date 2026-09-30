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

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
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
            return self._missions.get(mission_id)

    async def list_missions(self) -> List[Mission]:
        async with self._lock:
            return list(self._missions.values())

    async def update_status(
        self,
        mission_id: str,
        new_status: MissionStatus,
        reason: Optional[str] = None
    ) -> Optional[Mission]:
        async with self._lock:
            mission = self._missions.get(mission_id)
            if not mission:
                return None

            old_status = mission.status
            mission.status = new_status
            mission.updated_at = datetime.now(timezone.utc)

            if new_status == MissionStatus.RUNNING and not mission.metrics.started_at:
                mission.metrics.started_at = mission.updated_at
            elif new_status in (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED):
                mission.metrics.completed_at = mission.updated_at

        # Determine severity and event type
        severity = EventSeverity.INFO
        if new_status in (MissionStatus.PAUSED, MissionStatus.AWAITING_APPROVAL, MissionStatus.INVESTIGATING):
            severity = EventSeverity.WARNING
        elif new_status == MissionStatus.FAILED:
            severity = EventSeverity.ERROR

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
        return mission

    async def pause_mission(self, mission_id: str, reason: str) -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.PAUSED, reason=reason)

    async def resume_mission(self, mission_id: str) -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.RUNNING, reason="Resumed by operator or supervisor")

    async def complete_mission(self, mission_id: str, summary: Optional[str] = None) -> Optional[Mission]:
        return await self.update_status(mission_id, MissionStatus.COMPLETED, reason=summary or "Verified and completed")
