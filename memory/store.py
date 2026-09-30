import asyncio
import logging
from typing import Any, Dict, List, Optional
from core.events.bus import EventBus
from core.events.schema import Event, EventType
from memory.provenance import FactStatus, MemoryRecord

logger = logging.getLogger("supervisor.memory")


class MemoryStore:
    """Stores structured project memory with provenance validation."""

    def __init__(self, event_bus: Optional[EventBus] = None):
        self._records: Dict[str, MemoryRecord] = {}
        self._lock = asyncio.Lock()
        self.event_bus = event_bus

    async def add_record(
        self,
        mission_id: str,
        fact: str,
        source: str,
        created_by: str,
        status: FactStatus = FactStatus.OBSERVED,
        confidence: float = 1.0,
        category: str = "fact",
        details: Optional[str] = None
    ) -> MemoryRecord:
        record = MemoryRecord(
            mission_id=mission_id,
            fact=fact,
            source=source,
            created_by=created_by,
            status=status,
            confidence=confidence,
            category=category,
            details=details
        )
        async with self._lock:
            self._records[record.id] = record

        if self.event_bus:
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    type=EventType.MEMORY_UPDATED,
                    payload={
                        "record_id": record.id,
                        "fact": record.fact,
                        "status": record.status.value,
                        "category": record.category,
                        "created_by": record.created_by
                    }
                )
            )
        return record

    async def get_by_mission(
        self,
        mission_id: str,
        category: Optional[str] = None,
        status: Optional[FactStatus] = None
    ) -> List[MemoryRecord]:
        async with self._lock:
            records = [r for r in self._records.values() if r.mission_id == mission_id]
            if category:
                records = [r for r in records if r.category == category]
            if status:
                records = [r for r in records if r.status == status]
            return records

    async def get_structured_summary(self, mission_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Provides categorized memory for Screen 05 (Memory Screen)."""
        all_records = await self.get_by_mission(mission_id)
        return {
            "verified_facts": [
                r.model_dump() for r in all_records if r.status == FactStatus.VERIFIED
            ],
            "decisions": [
                r.model_dump() for r in all_records if r.category == "decision"
            ],
            "rejected_approaches": [
                r.model_dump() for r in all_records if r.status == FactStatus.REJECTED or r.category == "rejected_approach"
            ],
            "known_issues": [
                r.model_dump() for r in all_records if r.category == "known_issue"
            ],
        }
