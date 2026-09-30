from pathlib import Path
from typing import Optional
from core.events.bus import EventBus
from core.events.store import InMemoryEventStore
from core.missions.manager import MissionManager
from core.tasks.manager import TaskManager
from core.policies.models import PolicyConfig


class AppState:
    """Singleton application state holding core services."""
    def __init__(self):
        self.event_bus = EventBus()
        # Persist events to supervisor_events.jsonl in workspace
        self.event_store = InMemoryEventStore(persistence_file=Path("./supervisor_events.jsonl"))
        self.mission_manager = MissionManager(event_bus=self.event_bus)
        self.task_manager = TaskManager(event_bus=self.event_bus)
        self.policy_config = PolicyConfig()

        # Wire event store to automatically record all published events
        self.event_bus._global_subscribers.append(self.event_store.append)


# Global instance
app_state = AppState()
