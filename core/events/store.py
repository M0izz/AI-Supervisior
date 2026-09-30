import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.events.schema import Event, EventType

logger = logging.getLogger("supervisor.event_store")


class BaseEventStore(ABC):
    """Abstract interface for storing and retrieving events."""

    @abstractmethod
    async def append(self, event: Event) -> None:
        """Store an event."""
        pass

    @abstractmethod
    async def get_by_id(self, event_id: str) -> Optional[Event]:
        """Fetch single event by ID."""
        pass

    @abstractmethod
    async def query(
        self,
        mission_id: Optional[str] = None,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        event_types: Optional[List[EventType]] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Event]:
        """Query events matching filters."""
        pass

    @abstractmethod
    async def get_mission_timeline(self, mission_id: str) -> List[Dict[str, Any]]:
        """Return hierarchical timeline representation for the dashboard."""
        pass


class InMemoryEventStore(BaseEventStore):
    """
    In-memory and file-backed EventStore implementation.
    Optionally dumps to a jsonl file for persistence.
    """

    def __init__(self, persistence_file: Optional[Path] = None):
        self._events: List[Event] = []
        self._events_by_id: Dict[str, Event] = {}
        self._lock = asyncio.Lock()
        self._persistence_file = persistence_file

        if self._persistence_file and self._persistence_file.exists():
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        try:
            with open(self._persistence_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        event = Event.model_validate(data)
                        self._events.append(event)
                        self._events_by_id[event.event_id] = event
            logger.info(f"Loaded {len(self._events)} events from {self._persistence_file}")
        except Exception as e:
            logger.error(f"Failed to load events from {self._persistence_file}: {e}")

    async def append(self, event: Event) -> None:
        async with self._lock:
            self._events.append(event)
            self._events_by_id[event.event_id] = event

            if self._persistence_file:
                self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._persistence_file, "a", encoding="utf-8") as f:
                    f.write(event.model_dump_json() + "\n")

    async def get_by_id(self, event_id: str) -> Optional[Event]:
        async with self._lock:
            return self._events_by_id.get(event_id)

    async def query(
        self,
        mission_id: Optional[str] = None,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        event_types: Optional[List[EventType]] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Event]:
        async with self._lock:
            matched: List[Event] = []
            for ev in self._events:
                if mission_id and ev.mission_id != mission_id:
                    continue
                if task_id and ev.task_id != task_id:
                    continue
                if agent_id and ev.agent_id != agent_id:
                    continue
                if event_types and ev.type not in event_types:
                    continue
                if since and ev.timestamp < since:
                    continue
                matched.append(ev)

            return matched[offset:offset + limit]

    async def get_mission_timeline(self, mission_id: str) -> List[Dict[str, Any]]:
        """Construct structured chronological timeline suitable for the visual UI."""
        events = await self.query(mission_id=mission_id, limit=1000)
        timeline = []
        for ev in events:
            timeline.append({
                "id": ev.event_id,
                "timestamp": ev.timestamp.isoformat(),
                "type": ev.type.value,
                "severity": ev.severity.value,
                "task_id": ev.task_id,
                "agent_id": ev.agent_id,
                "summary": self._format_summary(ev),
                "payload": ev.payload
            })
        return timeline

    def _format_summary(self, ev: Event) -> str:
        t = ev.type
        p = ev.payload
        if t == EventType.TOOL_CALL:
            return f"Agent {ev.agent_id} called tool '{p.get('tool')}' on {p.get('target', 'workspace')}"
        elif t == EventType.TEST_RESULT:
            return f"Test run: {p.get('passed', 0)} passed, {p.get('failed', 0)} failed"
        elif t == EventType.SUPERVISOR_ALERT:
            return f"Supervisor Alert: [{p.get('anomaly_type')}] {p.get('description')}"
        elif t == EventType.SUPERVISOR_DECISION:
            return f"Supervisor Decision: {p.get('decision')} (Confidence: {p.get('confidence', 0):.0%})"
        elif t == EventType.TASK_STATUS_CHANGED:
            return f"Task {ev.task_id} status changed to {p.get('new_status')}"
        elif t == EventType.MISSION_STATUS_CHANGED:
            return f"Mission status: {p.get('new_status')}"
        return f"{ev.type.value}"
