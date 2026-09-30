import asyncio
import pytest
from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.missions.manager import MissionManager
from core.tasks.manager import TaskManager
from core.tasks.models import Task
from core.policies.models import PolicyConfig
from supervisor.engine import SupervisorEngine
from supervisor.decisions import SupervisorAction
from supervisor.rules import DeterministicRuleEngine
from supervisor.state_machine import SupervisorStateMachine, SupervisorState
from supervisor.reasoning import SupervisoryReasoner
from integrations.nebius.provider import MockReasoningProvider, NebiusNemotronProvider, BaseReasoningProvider, ReasoningDecision


def test_repeated_failure_detector():
    rules = DeterministicRuleEngine(PolicyConfig(pause_after_repeated_failures=3))
    task = Task(id="t1", mission_id="m1", title="Task 1", attempts=3)

    events = [
        Event(mission_id="m1", task_id="t1", type=EventType.TEST_RESULT, payload={"failed": 2, "error_signature": "KeyError at 0x7fa2:42"}),
        Event(mission_id="m1", task_id="t1", type=EventType.TEST_RESULT, payload={"failed": 2, "error_signature": "KeyError at 0x7fb9:42"}),
        Event(mission_id="m1", task_id="t1", type=EventType.TEST_RESULT, payload={"failed": 2, "error_signature": "KeyError at 0x7fc1:42"}),
    ]

    anomaly = rules.evaluate_test_history(task, events)
    assert anomaly is not None
    assert anomaly.anomaly_type == "LOOP_DETECTED"
    assert anomaly.recommended_action == SupervisorAction.DELEGATE


def test_no_progress_detector():
    rules = DeterministicRuleEngine(PolicyConfig(pause_after_repeated_failures=3))
    task = Task(id="t1", mission_id="m1", title="Task 1", attempts=3)

    # Different error signatures, but exact same passed/failed counts (no improvement)
    events = [
        Event(mission_id="m1", task_id="t1", type=EventType.TEST_RESULT, payload={"passed": 10, "failed": 3, "error_signature": "SIG_A"}),
        Event(mission_id="m1", task_id="t1", type=EventType.TEST_RESULT, payload={"passed": 10, "failed": 3, "error_signature": "SIG_B"}),
        Event(mission_id="m1", task_id="t1", type=EventType.TEST_RESULT, payload={"passed": 10, "failed": 3, "error_signature": "SIG_C"}),
    ]

    anomaly = rules.evaluate_no_progress(task, events)
    assert anomaly is not None
    assert anomaly.anomaly_type == "NO_PROGRESS"
    assert anomaly.recommended_action == SupervisorAction.CHANGE_STRATEGY


def test_scope_violation_detector():
    rules = DeterministicRuleEngine(PolicyConfig(prevent_modifications_outside_task_scope=True))
    task = Task(id="t1", mission_id="m1", title="Task 1", expected_files=["src/parser.py"])

    # Within scope
    ok_anomaly = rules.evaluate_tool_call("write_file", {"path": "src/parser.py"}, task=task)
    assert ok_anomaly is None

    # Outside scope
    violation = rules.evaluate_tool_call("write_file", {"path": "database/schema.sql"}, task=task)
    assert violation is not None
    assert violation.anomaly_type == "SCOPE_VIOLATION"


def test_budget_detector():
    rules = DeterministicRuleEngine(PolicyConfig(max_turns_per_task=10))

    anomaly = rules.evaluate_budget(iterations=10, tool_calls_count=15, elapsed_seconds=30.0)
    assert anomaly is not None
    assert anomaly.anomaly_type == "BUDGET_WARNING"


def test_supervisor_state_machine_transitions():
    sm = SupervisorStateMachine()
    assert sm.current_state == SupervisorState.IDLE

    sm.transition(SupervisorAction.CONTINUE)
    assert sm.current_state == SupervisorState.RUNNING

    sm.transition(SupervisorAction.DELEGATE)
    assert sm.current_state == SupervisorState.INVESTIGATING

    sm.transition(SupervisorAction.CHANGE_STRATEGY)
    assert sm.current_state == SupervisorState.RECOVERING

    sm.transition(SupervisorAction.CONTINUE)
    assert sm.current_state == SupervisorState.RUNNING

    sm.transition(SupervisorAction.PAUSE)
    assert sm.current_state == SupervisorState.PAUSED


class BrokenReasoningProvider(BaseReasoningProvider):
    async def reason_about_situation(self, prompt_context):
        raise ConnectionError("Nebius timeout or API error")


@pytest.mark.asyncio
async def test_nemotron_failure_fallback():
    # If reasoning provider crashes, supervisor must not crash and fallback to safe deterministic action
    reasoner = SupervisoryReasoner(provider=BrokenReasoningProvider())

    bus = EventBus()
    mission_mgr = MissionManager(bus)
    task_mgr = TaskManager(bus)
    supervisor = SupervisorEngine(
        event_bus=bus,
        mission_manager=mission_mgr,
        task_manager=task_mgr,
        reasoner=reasoner
    )

    mission = await mission_mgr.create_mission("Test Fallback", "Test")
    task = Task(id="t_fb", mission_id=mission.id, title="Test Task", attempts=3)
    await task_mgr.initialize_mission_tasks(mission.id, [task])

    # Send 3 identical failures to trigger anomaly pipeline with broken provider
    for _ in range(3):
        await bus.publish(
            Event(
                mission_id=mission.id,
                task_id=task.id,
                type=EventType.TEST_RESULT,
                payload={"failed": 1, "error_signature": "FATAL_SIG"}
            )
        )
        await asyncio.sleep(0.01)

    # Supervisor should have safely handled the anomaly without raising exception
    assert supervisor.state_machine.current_state in (SupervisorState.INVESTIGATING, SupervisorState.PAUSED)
