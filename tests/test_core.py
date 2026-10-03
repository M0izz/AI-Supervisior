import pytest
import asyncio
from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.events.store import InMemoryEventStore
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus
from core.tasks.models import Task, TaskGraph, TaskStatus
from core.tasks.manager import TaskManager
from core.policies.models import PolicyConfig, AutonomyLevel
from core.state.models import AgentContextPackage


@pytest.mark.asyncio
async def test_event_bus_and_store():
    bus = EventBus()
    store = InMemoryEventStore()

    received_events = []

    async def on_event(ev: Event):
        received_events.append(ev)
        await store.append(ev)

    await bus.subscribe(on_event)

    ev1 = Event(
        mission_id="msn_test_1",
        type=EventType.MISSION_STARTED,
        payload={"msg": "hello"}
    )
    await bus.publish(ev1)

    assert len(received_events) == 1
    assert received_events[0].event_id == ev1.event_id

    # Check store query
    stored = await store.query(mission_id="msn_test_1")
    assert len(stored) == 1
    assert stored[0].mission_id == "msn_test_1"


@pytest.mark.asyncio
async def test_mission_manager_lifecycle():
    bus = EventBus()
    mgr = MissionManager(event_bus=bus)

    mission_events = []
    await bus.subscribe(lambda ev: mission_events.append(ev), event_type=EventType.MISSION_STATUS_CHANGED)

    mission = await mgr.create_mission(
        title="Add CSV import",
        goal="Parse CSV files without database modification"
    )
    assert mission.status in (MissionStatus.PENDING, MissionStatus.CREATED)

    await mgr.update_status(mission.id, MissionStatus.RUNNING)
    assert len(mission_events) == 1
    assert mission_events[0].payload["new_status"] == "RUNNING"

    await mgr.pause_mission(mission.id, reason="Loop detected")
    m = await mgr.get_mission(mission.id)
    assert m.status == MissionStatus.PAUSED


@pytest.mark.asyncio
async def test_task_graph_dag_resolution():
    bus = EventBus()
    task_mgr = TaskManager(event_bus=bus)

    t1 = Task(id="TASK-001", mission_id="msn_1", title="Inspect data model", order=1)
    t2 = Task(id="TASK-002", mission_id="msn_1", title="Design parser", dependencies=["TASK-001"], order=2)
    t3 = Task(id="TASK-003", mission_id="msn_1", title="Implement importer", dependencies=["TASK-002"], order=3)

    graph = await task_mgr.initialize_mission_tasks("msn_1", [t1, t2, t3])

    # Initially, only TASK-001 is ready
    ready = graph.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].id == "TASK-001"

    # Complete TASK-001
    await task_mgr.complete_task("msn_1", "TASK-001", summary="Inspected data models")
    ready_after = graph.get_ready_tasks()
    assert len(ready_after) == 1
    assert ready_after[0].id == "TASK-002"


def test_policies():
    policy = PolicyConfig(autonomy_level=AutonomyLevel.SUPERVISED)

    assert policy.is_command_dangerous("rm -rf /tmp/data") is True
    assert policy.is_command_dangerous("pytest tests/") is False

    assert policy.is_path_protected("database/migrations/001_init.sql") is True
    assert policy.is_path_protected("src/importer.py") is False
