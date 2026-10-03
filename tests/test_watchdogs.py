import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional
import pytest

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.policies.models import PolicyConfig
from core.protocol.schema import WorkProtocolEvent, TaskDispatchPackage
from core.protocol.actions import ActionInfo, TelemetryInfo
from core.protocol.events import ProtocolEventType
from supervisor.rules import DeterministicRuleEngine
from supervisor.watchdogs import (
    WatchdogAction,
    WatchdogDecision,
    InterventionRecord,
    WatchdogEngine,
    InterventionController,
    _normalize_event,
)
from adapters.base import AgentAdapter
from adapters.models import (
    AdapterIdentity,
    AdapterAvailability,
    AdapterAvailabilityStatus,
    AdapterProcessStatus,
    AdapterExecutionResult,
)
from adapters.registry import AdapterRegistry
from adapters.claude_code import ClaudeCodeAdapter
from execution.worktree import GitWorktreeManager
from storage.sqlite import DatabaseManager, EventRepository, ApprovalRepository, MissionRepository



# ============================================================================
# TEST FIXTURES & MOCKS
# ============================================================================

class MockAdapter(AgentAdapter):
    """Deterministic mock adapter to verify intervention controller actions."""

    def __init__(self, adapter_id: str = "mock_agent"):
        self._identity = AdapterIdentity(
            provider="mock_provider",
            adapter_id=adapter_id,
            display_name="Mock Agent",
            version="1.0.0",
            capabilities=["code_execution", "terminal_execution"],
        )
        self.cancel_calls: List[str] = []
        self.cancelled_tasks: set = set()

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def check_availability(self) -> AdapterAvailability:
        return AdapterAvailability(
            status=AdapterAvailabilityStatus.AVAILABLE,
            available=True,
            message="Mock adapter available",
        )

    async def execute(self, dispatch: TaskDispatchPackage) -> AdapterExecutionResult:
        return AdapterExecutionResult(
            status=AdapterProcessStatus.COMPLETED,
            exit_code=0,
            workspace=dispatch.workspace,
            summary="Mock completed",
            duration=0.1,
        )

    async def cancel(self, task_id: str) -> bool:
        self.cancel_calls.append(task_id)
        self.cancelled_tasks.add(task_id)
        return True

    async def status(self, task_id: str) -> AdapterProcessStatus:
        if task_id in self.cancelled_tasks:
            return AdapterProcessStatus.CANCELLED
        return AdapterProcessStatus.RUNNING

    async def cleanup(self, task_id: str) -> None:
        pass


# ============================================================================
# TEST GROUP A: EVENT EVALUATION & NORMALIZATION
# ============================================================================

def test_event_normalizer_work_protocol_event():
    event = WorkProtocolEvent(
        mission_id="m-1",
        task_id="t-1",
        agent_id="claude_code",
        event_type=ProtocolEventType.COMMAND_STARTED,
        action=ActionInfo(action_type="command_execute", target="pytest -q"),
        telemetry=TelemetryInfo(step_number=1, duration_ms=150),
    )
    d = _normalize_event(event)
    assert d["mission_id"] == "m-1"
    assert d["task_id"] == "t-1"
    assert d["agent_id"] == "claude_code"
    assert d["event_type"] == ProtocolEventType.COMMAND_STARTED.value
    assert d["action"]["target"] == "pytest -q"
    assert d["telemetry"]["step_number"] == 1


def test_event_normalizer_eventbus_event():
    event = Event(
        mission_id="m-2",
        task_id="t-2",
        agent_id="claude_code",
        type=EventType.AGENT_ACTION,
        payload={"command": "git status", "event_type": "command.started"},
    )
    d = _normalize_event(event)
    assert d["mission_id"] == "m-2"
    assert d["task_id"] == "t-2"
    assert d["event_type"] == "command.started"
    assert d["payload"]["command"] == "git status"



def test_watchdog_malformed_event_handled_safely():
    engine = WatchdogEngine()
    # Passing an object that can't be normalized
    decision = engine.evaluate_event(None)  # type: ignore
    assert decision.action in (WatchdogAction.ALLOW, WatchdogAction.WARN)
    assert decision.rule_id in ("PERMITTED", "MALFORMED_EVENT")


def test_watchdog_benign_event_allowed():
    engine = WatchdogEngine()
    event = WorkProtocolEvent(
        mission_id="m-1",
        task_id="t-1",
        agent_id="claude_code",
        event_type=ProtocolEventType.COMMAND_STARTED,
        action=ActionInfo(action_type="command_execute", target="pytest tests/test_math.py"),
    )
    decision = engine.evaluate_event(event)
    assert decision.action == WatchdogAction.ALLOW
    assert decision.rule_id == "PERMITTED"


# ============================================================================
# TEST GROUP B: LOOP DETECTION & ERROR NORMALIZATION
# ============================================================================

def test_loop_detection_triggers_on_three_identical_failures():
    engine = WatchdogEngine()
    engine.register_task_scope(task_id="t-loop", allowed_files=["src/auth.py"])

    # Failures 1 & 2
    for i in range(2):
        event = WorkProtocolEvent(
            mission_id="m-loop",
            task_id="t-loop",
            agent_id="claude_code",
            event_type=ProtocolEventType.TEST_FAILED,
            payload={"error": "AssertionError: Expected 200 got 401 at auth.py:42"},
        )
        dec = engine.evaluate_event(event)
        assert dec.action == WatchdogAction.ALLOW

    # Failure 3 with same normalized signature (line number different, normalized away)
    event3 = WorkProtocolEvent(
        mission_id="m-loop",
        task_id="t-loop",
        agent_id="claude_code",
        event_type=ProtocolEventType.TEST_FAILED,
        payload={"error": "AssertionError: Expected 200 got 401 at auth.py:99"},
    )
    dec3 = engine.evaluate_event(event3)
    assert dec3.action == WatchdogAction.CANCEL
    assert dec3.rule_id == "LOOP_DETECTED"
    assert dec3.severity == "critical"
    assert "Repeated failure loop detected" in dec3.reason
    assert dec3.evidence["consecutive_failures"] == 3


def test_loop_detection_does_not_trigger_on_different_failures():
    engine = WatchdogEngine()
    engine.register_task_scope(task_id="t-mixed", allowed_files=["src/auth.py"])

    # Failure A
    engine.evaluate_event(WorkProtocolEvent(
        mission_id="m-1",
        task_id="t-mixed",
        agent_id="claude_code",
        event_type=ProtocolEventType.TEST_FAILED,
        payload={"error": "ImportError: No module named 'jwt'"},
    ))
    # Failure A
    engine.evaluate_event(WorkProtocolEvent(
        mission_id="m-1",
        task_id="t-mixed",
        agent_id="claude_code",
        event_type=ProtocolEventType.TEST_FAILED,
        payload={"error": "ImportError: No module named 'jwt'"},
    ))
    # Failure B (different error signature)
    dec = engine.evaluate_event(WorkProtocolEvent(
        mission_id="m-1",
        task_id="t-mixed",
        agent_id="claude_code",
        event_type=ProtocolEventType.TEST_FAILED,
        payload={"error": "TypeError: 'NoneType' object is not iterable"},
    ))

    # Threshold not reached because signatures differ
    assert dec.action == WatchdogAction.ALLOW


# ============================================================================
# TEST GROUP C: SCOPE VIOLATION DETECTION
# ============================================================================

def test_scope_allowed_file_modification():
    engine = WatchdogEngine()
    engine.register_task_scope(
        task_id="t-scope",
        allowed_files=["src/auth/jwt.py", "tests/test_auth.py"],
    )

    event = WorkProtocolEvent(
        mission_id="m-1",
        task_id="t-scope",
        agent_id="claude_code",
        event_type=ProtocolEventType.FILE_CHANGED,
        action=ActionInfo(action_type="file_write", target="src/auth/jwt.py"),
    )
    decision = engine.evaluate_event(event)
    assert decision.action == WatchdogAction.ALLOW


def test_scope_unauthorized_file_modification_triggers_cancel():
    engine = WatchdogEngine()
    engine.register_task_scope(
        task_id="t-scope",
        allowed_files=["src/auth/*"],
    )

    # Attempt to modify billing file
    event = WorkProtocolEvent(
        mission_id="m-1",
        task_id="t-scope",
        agent_id="claude_code",
        event_type=ProtocolEventType.FILE_CHANGED,
        action=ActionInfo(action_type="file_write", target="src/billing/stripe.py"),
    )
    decision = engine.evaluate_event(event)
    assert decision.action == WatchdogAction.CANCEL
    assert decision.rule_id == "SCOPE_VIOLATION"
    assert "violates declared task scope" in decision.reason


def test_scope_path_traversal_detection():
    engine = WatchdogEngine()
    engine.register_task_scope(task_id="t-scope", allowed_files=["src/auth.py"])

    # Path traversal attempt
    event = WorkProtocolEvent(
        mission_id="m-1",
        task_id="t-scope",
        agent_id="claude_code",
        event_type=ProtocolEventType.FILE_CHANGED,
        action=ActionInfo(action_type="file_write", target="../../etc/shadow"),
    )
    decision = engine.evaluate_event(event)
    assert decision.action == WatchdogAction.CANCEL
    assert decision.rule_id == "SCOPE_VIOLATION"
    assert "Path traversal" in decision.reason


def test_scope_protected_path_env_detection():
    engine = WatchdogEngine()
    engine.register_task_scope(task_id="t-scope", allowed_files=["*"])

    event = WorkProtocolEvent(
        mission_id="m-1",
        task_id="t-scope",
        agent_id="claude_code",
        event_type=ProtocolEventType.FILE_CHANGED,
        action=ActionInfo(action_type="file_write", target=".env"),
    )
    decision = engine.evaluate_event(event)
    assert decision.action == WatchdogAction.CANCEL
    assert decision.rule_id == "SCOPE_VIOLATION"
    assert "protected path" in decision.reason.lower()


# ============================================================================
# TEST GROUP D: DANGEROUS COMMAND INTERCEPTION
# ============================================================================

def test_dangerous_command_rm_rf_interception():
    engine = WatchdogEngine()
    event = WorkProtocolEvent(
        mission_id="m-cmd",
        task_id="t-cmd",
        agent_id="claude_code",
        event_type=ProtocolEventType.COMMAND_STARTED,
        action=ActionInfo(action_type="command_execute", target="rm -rf /var/data"),
    )
    decision = engine.evaluate_event(event)
    assert decision.action in (WatchdogAction.CANCEL, WatchdogAction.REQUIRE_APPROVAL)
    assert decision.rule_id == "DANGEROUS_COMMAND"
    assert "prohibited dangerous pattern" in decision.reason


def test_dangerous_sql_drop_table_interception():
    engine = WatchdogEngine()
    event = WorkProtocolEvent(
        mission_id="m-cmd",
        task_id="t-cmd",
        agent_id="claude_code",
        event_type=ProtocolEventType.COMMAND_STARTED,
        action=ActionInfo(action_type="command_execute", target="psql -c 'DROP TABLE users CASCADE;'"),
    )
    decision = engine.evaluate_event(event)
    assert decision.action in (WatchdogAction.CANCEL, WatchdogAction.REQUIRE_APPROVAL)
    assert decision.rule_id == "DANGEROUS_COMMAND"


def test_safe_command_remains_allowed():
    engine = WatchdogEngine()
    event = WorkProtocolEvent(
        mission_id="m-cmd",
        task_id="t-cmd",
        agent_id="claude_code",
        event_type=ProtocolEventType.COMMAND_STARTED,
        action=ActionInfo(action_type="command_execute", target="python -m pytest tests/ -v"),
    )
    decision = engine.evaluate_event(event)
    assert decision.action == WatchdogAction.ALLOW


# ============================================================================
# TEST GROUP E: EXECUTION BUDGET ENFORCEMENT
# ============================================================================

def test_turn_budget_enforcement():
    engine = WatchdogEngine()
    engine.register_task_scope(
        task_id="t-budget",
        allowed_files=["*"],
        budget={"max_iterations": 3},
    )

    # 3 commands allowed
    for i in range(3):
        ev = WorkProtocolEvent(
            mission_id="m-1",
            task_id="t-budget",
            agent_id="claude_code",
            event_type=ProtocolEventType.COMMAND_STARTED,
            action=ActionInfo(action_type="command_execute", target=f"echo {i}"),
        )
        dec = engine.evaluate_event(ev)
        assert dec.action == WatchdogAction.ALLOW

    # 4th command exceeds turn budget
    ev4 = WorkProtocolEvent(
        mission_id="m-1",
        task_id="t-budget",
        agent_id="claude_code",
        event_type=ProtocolEventType.COMMAND_STARTED,
        action=ActionInfo(action_type="command_execute", target="echo 4"),
    )
    dec4 = engine.evaluate_event(ev4)
    assert dec4.action == WatchdogAction.CANCEL
    assert dec4.rule_id == "BUDGET_EXCEEDED"
    assert "Turn budget exceeded" in dec4.reason


def test_timeout_budget_enforcement():
    engine = WatchdogEngine()
    engine.register_task_scope(
        task_id="t-timeout",
        allowed_files=["*"],
        timeout=0.01,  # 10ms
    )
    time.sleep(0.02)  # Wait 20ms to expire

    ev = WorkProtocolEvent(
        mission_id="m-1",
        task_id="t-timeout",
        agent_id="claude_code",
        event_type=ProtocolEventType.COMMAND_STARTED,
        action=ActionInfo(action_type="command_execute", target="ls"),
    )
    dec = engine.evaluate_event(ev)
    assert dec.action == WatchdogAction.CANCEL
    assert dec.rule_id == "TIMEOUT_EXCEEDED"


# ============================================================================
# TEST GROUP F: INTERVENTION CONTROLLER & IDEMPOTENCY
# ============================================================================

@pytest.mark.asyncio
async def test_intervention_controller_dispatches_cancel_to_adapter():
    engine = WatchdogEngine()
    adapter = MockAdapter("claude_code")
    registry = AdapterRegistry()
    registry.register_adapter(adapter)
    bus = EventBus()

    controller = InterventionController(
        watchdog_engine=engine,
        adapter_registry=registry,
        event_bus=bus,
    )

    # Emit dangerous command event
    event = WorkProtocolEvent(
        mission_id="m-intv",
        task_id="t-intv-1",
        agent_id="claude_code",
        event_type=ProtocolEventType.COMMAND_STARTED,
        action=ActionInfo(action_type="command_execute", target="rm -rf /"),
    )
    dec = await controller.handle_event(event)

    assert dec.action in (WatchdogAction.CANCEL, WatchdogAction.REQUIRE_APPROVAL)
    assert "t-intv-1" in adapter.cancel_calls
    assert controller.is_task_intervened("t-intv-1")
    assert len(controller.get_audit_records()) == 1


@pytest.mark.asyncio
async def test_intervention_controller_idempotency_prevents_duplicate_cancels():
    engine = WatchdogEngine()
    adapter = MockAdapter("claude_code")
    registry = AdapterRegistry()
    registry.register_adapter(adapter)
    bus = EventBus()

    controller = InterventionController(
        watchdog_engine=engine,
        adapter_registry=registry,
        event_bus=bus,
    )

    event1 = WorkProtocolEvent(
        mission_id="m-intv",
        task_id="t-intv-dup",
        agent_id="claude_code",
        event_type=ProtocolEventType.COMMAND_STARTED,
        action=ActionInfo(action_type="command_execute", target="rm -rf /"),
    )
    event2 = WorkProtocolEvent(
        mission_id="m-intv",
        task_id="t-intv-dup",
        agent_id="claude_code",
        event_type=ProtocolEventType.COMMAND_STARTED,
        action=ActionInfo(action_type="command_execute", target="drop database test"),
    )

    await controller.handle_event(event1)
    await controller.handle_event(event2)

    # Only one adapter cancel call must have been issued
    assert adapter.cancel_calls == ["t-intv-dup"]


@pytest.mark.asyncio
async def test_intervention_controller_approval_flow():
    # Configure policy requiring approval for destructive commands
    policy = PolicyConfig(require_approval_for_destructive_commands=True)
    engine = WatchdogEngine(policy=policy)
    adapter = MockAdapter("claude_code")
    registry = AdapterRegistry()
    registry.register_adapter(adapter)
    bus = EventBus()

    with tempfile.TemporaryDirectory() as tmp_dir:
        db = DatabaseManager(db_path=os.path.join(tmp_dir, "test.db"))
        mission_repo = MissionRepository(db)
        approval_repo = ApprovalRepository(db)
        event_repo = EventRepository(db)

        # Seed mission in DB to satisfy foreign keys
        await mission_repo.save({
            "mission_id": "m-appr",
            "title": "Approval Test",
            "goal": "Verify approvals",
            "repository_path": tmp_dir,
            "status": "IN_PROGRESS",
        })

        controller = InterventionController(
            watchdog_engine=engine,
            adapter_registry=registry,
            event_bus=bus,
            approval_repo=approval_repo,
            event_repo=event_repo,
        )

        event = WorkProtocolEvent(
            mission_id="m-appr",
            task_id="t-appr-1",
            agent_id="claude_code",
            event_type=ProtocolEventType.COMMAND_STARTED,
            action=ActionInfo(action_type="command_execute", target="rm -rf /data"),
        )
        dec = await controller.handle_event(event)

        assert dec.action == WatchdogAction.REQUIRE_APPROVAL
        assert "t-appr-1" in adapter.cancel_calls

        # Verify approval request was recorded in database
        approvals = await approval_repo.list_by_mission("m-appr")
        assert any(a["task_id"] == "t-appr-1" for a in approvals)


# ============================================================================
# TEST GROUP G: KILLER SCENARIO — END-TO-END SUPERVISED EXECUTION
# ============================================================================

@pytest.mark.asyncio
async def test_killer_scenario_claude_repeated_failure_loop_intervened():
    """
    Killer Scenario:
    Claude attempts a test fix. Fails with Signature A.
    Claude attempts another fix. Fails with Signature A.
    Claude attempts another fix. Fails with Signature A.
    Supervisor Watchdog detects repeated failure loop.
    InterventionController cancels Claude process immediately.
    Intervention audit trail is persisted.
    Claude is NOT allowed to continue indefinitely.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "scenario.db")
        db = DatabaseManager(db_path=db_path)
        mission_repo = MissionRepository(db)
        event_repo = EventRepository(db)

        mission_id = "mission-auth-fix"
        task_id = "task-auth-fix"

        # Seed mission in DB to satisfy foreign keys
        await mission_repo.save({
            "mission_id": mission_id,
            "title": "Auth Fix Mission",
            "goal": "Fix failing authentication unit tests",
            "repository_path": tmp_dir,
            "status": "IN_PROGRESS",
        })

        bus = EventBus()
        # Wire SQLite event repo to bus
        bus.subscribe_sync(event_repo.append)

        adapter = MockAdapter("claude_code")
        registry = AdapterRegistry()
        registry.register_adapter(adapter)

        policy = PolicyConfig(pause_after_repeated_failures=3)
        watchdog_engine = WatchdogEngine(policy=policy)
        watchdog_engine.register_task_scope(
            task_id=task_id,
            allowed_files=["src/auth/jwt.py", "tests/test_auth.py"],
        )

        controller = InterventionController(
            watchdog_engine=watchdog_engine,
            adapter_registry=registry,
            event_bus=bus,
            event_repo=event_repo,
        )

        # Step 1: Agent starts and runs command
        await controller.handle_event(WorkProtocolEvent(
            mission_id=mission_id,
            task_id=task_id,
            agent_id="claude_code",
            event_type=ProtocolEventType.AGENT_STARTED,
        ))


        # Step 2: Attempt 1 fails with signature A
        dec1 = await controller.handle_event(WorkProtocolEvent(
            mission_id=mission_id,
            task_id=task_id,
            agent_id="claude_code",
            event_type=ProtocolEventType.TEST_FAILED,
            payload={"error": "AssertionError: Token validation returned 403 Forbidden at auth.py:101"},
        ))
        assert dec1.action == WatchdogAction.ALLOW
        assert len(adapter.cancel_calls) == 0

        # Step 3: Attempt 2 fails with signature A (different line number, normalized away)
        dec2 = await controller.handle_event(WorkProtocolEvent(
            mission_id=mission_id,
            task_id=task_id,
            agent_id="claude_code",
            event_type=ProtocolEventType.TEST_FAILED,
            payload={"error": "AssertionError: Token validation returned 403 Forbidden at auth.py:245"},
        ))
        assert dec2.action == WatchdogAction.ALLOW
        assert len(adapter.cancel_calls) == 0

        # Step 4: Attempt 3 fails with signature A
        dec3 = await controller.handle_event(WorkProtocolEvent(
            mission_id=mission_id,
            task_id=task_id,
            agent_id="claude_code",
            event_type=ProtocolEventType.TEST_FAILED,
            payload={"error": "AssertionError: Token validation returned 403 Forbidden at auth.py:310"},
        ))

        # Step 5: SUPERVISORY INTERVENTION
        assert dec3.action == WatchdogAction.CANCEL
        assert dec3.rule_id == "LOOP_DETECTED"
        assert dec3.severity == "critical"

        # Claude process was cancelled by the Supervisor!
        assert adapter.cancel_calls == [task_id]
        assert controller.is_task_intervened(task_id)

        # Audit trail verified
        audit_trail = controller.get_audit_records(task_id)
        assert len(audit_trail) == 1
        record = audit_trail[0]
        assert record.rule_id == "LOOP_DETECTED"
        assert record.action == WatchdogAction.CANCEL
        assert record.adapter_cancelled is True

        # Step 6: Verify process cannot receive further post-intervention cancellations
        dec4 = await controller.handle_event(WorkProtocolEvent(
            mission_id=mission_id,
            task_id=task_id,
            agent_id="claude_code",
            event_type=ProtocolEventType.TEST_FAILED,
            payload={"error": "AssertionError: Token validation returned 403 Forbidden"},
        ))
        # Cancel was NOT invoked a second time
        assert adapter.cancel_calls == [task_id]
