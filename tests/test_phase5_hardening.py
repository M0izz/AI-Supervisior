import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.events.bus import EventBus
from core.events.store import InMemoryEventStore
from core.events.schema import Event, EventType, EventSeverity
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus
from core.tasks.manager import TaskManager
from core.tasks.models import Task, TaskStatus
from core.policies.models import PolicyConfig
from supervisor.engine import SupervisorEngine
from supervisor.rules import AnomalyReport
from supervisor.decisions import SupervisorAction, SupervisorDecision
from supervisor.approvals import ApprovalManager, ApprovalResolutionAction, ResolveApprovalPayload
from supervisor.telemetry import TelemetryTracker
from supervisor.timeline import SupervisorTimelineBuilder
from agents.registry import AgentRegistry, AgentStatus, AgentHealth
from agents.worker.agent import WorkerAgent
from agents.reviewer.agent import ReviewerAgent, ReviewerDiagnosis
from agents.verifier.agent import VerifierAgent
from tools.base import ToolResult, BaseTool
from tools.shell import RunCommandTool
from tools.testing import RunTestsTool
from integrations.nebius.provider import MockReasoningProvider, NebiusNemotronProvider
from supervisor.reasoning import SupervisoryReasoner
from core.state.models import AgentContextPackage


@pytest.fixture
def clean_env(tmp_path):
    bus = EventBus()
    store = InMemoryEventStore()
    bus._global_subscribers.append(store.append)
    mission_mgr = MissionManager(event_bus=bus)
    task_mgr = TaskManager(event_bus=bus)
    policy = PolicyConfig(
        max_iterations_per_task=5,
        max_tool_calls_per_task=10,
        pause_after_repeated_failures=3,
        prohibited_commands=["rm -rf", "drop table"]
    )
    registry = AgentRegistry(event_bus=bus)
    telemetry = TelemetryTracker(event_bus=bus)
    approval_mgr = ApprovalManager(event_bus=bus)
    supervisor = SupervisorEngine(
        event_bus=bus,
        mission_manager=mission_mgr,
        task_manager=task_mgr,
        policy=policy,
        reasoner=MockReasoningProvider(),
        registry=registry,
        telemetry=telemetry,
        approval_manager=approval_mgr
    )
    return {
        "bus": bus,
        "store": store,
        "mission_mgr": mission_mgr,
        "task_mgr": task_mgr,
        "policy": policy,
        "registry": registry,
        "telemetry": telemetry,
        "approval_mgr": approval_mgr,
        "supervisor": supervisor,
        "workspace": tmp_path
    }


# 1. Worker Loops
@pytest.mark.asyncio
async def test_worker_loops_detected(clean_env):
    bus = clean_env["bus"]
    mission_mgr = clean_env["mission_mgr"]
    task_mgr = clean_env["task_mgr"]
    supervisor = clean_env["supervisor"]

    mission = await mission_mgr.create_mission(title="Loop Test", goal="Detect infinite loop")
    task = Task(id="TASK-LOOP", mission_id=mission.id, title="Buggy task")
    await task_mgr.initialize_mission_tasks(mission.id, [task])

    worker = WorkerAgent(agent_id="worker_loop", event_bus=bus, tools={})
    supervisor.register_worker(worker)

    # 3 consecutive identical test failures
    for _ in range(3):
        await bus.publish(
            Event(
                mission_id=mission.id,
                task_id=task.id,
                agent_id="worker_loop",
                type=EventType.TEST_RESULT,
                payload={"passed": 10, "failed": 2, "error_signature": "SAME_SYNTAX_ERROR"}
            )
        )

    assert worker.state.value == "PAUSED"
    # Verify alert event
    events = [e for e in clean_env["store"]._events if e.type == EventType.SUPERVISOR_ALERT]
    assert len(events) >= 1
    assert "LOOP" in events[0].payload["anomaly_type"]


# 2. Worker Hangs / Timeout
@pytest.mark.asyncio
async def test_worker_timeout(clean_env):
    bus = clean_env["bus"]
    worker = WorkerAgent(agent_id="worker_hang", event_bus=bus, tools={})
    worker.timeout_seconds = 0.2

    # Mock next action to hang
    async def slow_action(*args, **kwargs):
        await asyncio.sleep(0.5)
        return MagicMock(action="complete", arguments={}, thought_summary="done")

    with patch.object(worker, "_ask_model_for_next_action", side_effect=slow_action):
        res = await worker.run_task(
            mission_id="MSN-TIMEOUT",
            task={"id": "TASK-TIMEOUT", "title": "Slow task", "expected_files": []}
        )
        assert res["status"] == "FAILED"
        assert "timed out" in res["error"].lower()


# 3. Worker Exceeds Budget
@pytest.mark.asyncio
async def test_worker_exceeds_budget(clean_env):
    bus = clean_env["bus"]
    mission_mgr = clean_env["mission_mgr"]
    task_mgr = clean_env["task_mgr"]
    supervisor = clean_env["supervisor"]

    mission = await mission_mgr.create_mission(title="Budget Test", goal="Detect budget exceeded")
    task = Task(id="TASK-BUDGET", mission_id=mission.id, title="Heavy task")
    await task_mgr.initialize_mission_tasks(mission.id, [task])

    worker = WorkerAgent(agent_id="worker_budget", event_bus=bus, tools={})
    supervisor.register_worker(worker)

    # Emit task progress iterations exceeding max_turns_per_task (policy has max_turns_per_task=50, let's configure 5)
    supervisor.policy.max_turns_per_task = 5
    for i in range(6):
        await bus.publish(
            Event(
                mission_id=mission.id,
                task_id=task.id,
                agent_id="worker_budget",
                type=EventType.TASK_PROGRESS,
                payload={"iteration": i}
            )
        )

    alerts = [e for e in clean_env["store"]._events if e.type == EventType.SUPERVISOR_ALERT and "BUDGET" in e.payload.get("anomaly_type", "")]
    assert len(alerts) >= 1
    assert alerts[0].payload["anomaly_type"] == "BUDGET_WARNING"


# 4. Worker Modifies Wrong File (Scope Violation)
@pytest.mark.asyncio
async def test_worker_scope_violation(clean_env):
    bus = clean_env["bus"]
    mission_mgr = clean_env["mission_mgr"]
    task_mgr = clean_env["task_mgr"]
    supervisor = clean_env["supervisor"]

    mission = await mission_mgr.create_mission(title="Scope Test", goal="Guard boundaries")
    task = Task(id="TASK-SCOPE", mission_id=mission.id, title="Scoped task", expected_files=["src/parser.py"])
    await task_mgr.initialize_mission_tasks(mission.id, [task])

    worker = WorkerAgent(agent_id="worker_scope", event_bus=bus, tools={})
    supervisor.register_worker(worker)

    # Worker attempts to edit out-of-scope database migration
    await bus.publish(
        Event(
            mission_id=mission.id,
            task_id=task.id,
            agent_id="worker_scope",
            type=EventType.TOOL_CALLED,
            payload={"tool": "edit_file", "arguments": {"path": "database/migrations/001.sql"}}
        )
    )

    alerts = [e for e in clean_env["store"]._events if e.type == EventType.SUPERVISOR_ALERT and "SCOPE" in e.payload.get("anomaly_type", "")]
    assert len(alerts) >= 1
    assert alerts[0].payload["anomaly_type"] == "SCOPE_VIOLATION"


# 5. Worker Attempts Dangerous Command
@pytest.mark.asyncio
async def test_worker_dangerous_command_blocked(clean_env):
    bus = clean_env["bus"]
    mission_mgr = clean_env["mission_mgr"]
    task_mgr = clean_env["task_mgr"]
    supervisor = clean_env["supervisor"]
    workspace = clean_env["workspace"]

    mission = await mission_mgr.create_mission(title="Danger Test", goal="Block destructive commands")
    task = Task(id="TASK-DANGER", mission_id=mission.id, title="Dangerous task")
    await task_mgr.initialize_mission_tasks(mission.id, [task])

    shell_tool = RunCommandTool(workspace_root=workspace)
    worker = WorkerAgent(agent_id="worker_danger", event_bus=bus, tools={"run_command": shell_tool})
    supervisor.register_worker(worker)

    # Attempt destructive command
    res = await worker.call_tool("run_command", {"command": "rm -rf /"}, mission_id=mission.id, task_id=task.id)
    assert not res.success
    assert res.metadata.get("danger_detected")

    danger_events = [e for e in clean_env["store"]._events if e.type == EventType.DANGER_DETECTED]
    assert len(danger_events) >= 1
    # Worker must be paused
    assert worker.state.value == "PAUSED"


# 6. Nemotron Unavailable / Fallback
@pytest.mark.asyncio
async def test_nemotron_unavailable_safe_fallback(clean_env):
    bus = clean_env["bus"]
    mission_mgr = clean_env["mission_mgr"]
    task_mgr = clean_env["task_mgr"]

    mission = await mission_mgr.create_mission(title="Fallback Test", goal="Test fallback")
    task = Task(id="TASK-FALLBACK", mission_id=mission.id, title="Test fallback")
    await task_mgr.initialize_mission_tasks(mission.id, [task])

    # Reasoner whose decide method raises an exception
    failing_reasoner = SupervisoryReasoner()
    failing_reasoner.decide = AsyncMock(side_effect=Exception("Nebius 503 Service Unavailable"))

    supervisor = SupervisorEngine(
        event_bus=bus,
        mission_manager=mission_mgr,
        task_manager=task_mgr,
        reasoner=failing_reasoner
    )

    anomaly = AnomalyReport(
        anomaly_type="LOOP_DETECTED",
        description="Repeated loop",
        evidence={"error_signature": "SIG_123"},
        recommended_action=SupervisorAction.DELEGATE
    )

    # Pipeline should complete without unhandled exception using fallback
    await supervisor._trigger_anomaly_pipeline(mission.id, task.id, "worker_fb", anomaly)

    decisions = [e for e in clean_env["store"]._events if e.type == EventType.SUPERVISOR_DECISION]
    assert len(decisions) >= 1
    assert decisions[0].payload["model_source"] == "deterministic_fallback"


# 7. Nemotron Produces Malformed JSON
@pytest.mark.asyncio
async def test_nemotron_malformed_json_fallback():
    provider = NebiusNemotronProvider(api_key="valid_dummy_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "This is definitely not valid json {"}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        decision = await provider.reason_about_situation({"anomaly_type": "LOOP_DETECTED", "error_signature": "TEST"})
        # Should gracefully fall back to mock provider's DELEGATE decision
        assert decision.decision == "DELEGATE"


# 8. Reviewer Cannot Diagnose (Inconclusive / UNKNOWN)
@pytest.mark.asyncio
async def test_reviewer_unknown_diagnosis_fallback(clean_env):
    bus = clean_env["bus"]
    reviewer = ReviewerAgent(agent_id="reviewer_unknown", event_bus=bus, tools={})

    ctx = AgentContextPackage(
        mission_id="MSN-UNK",
        objective="Investigate obscure glitch",
        task={"id": "TASK-UNK", "title": "Obscure task", "last_error_signature": "UNKNOWN_KERNEL_PANIC_0x99"},
        previous_attempts=[{"error_signature": "UNKNOWN_KERNEL_PANIC_0x99"}]
    )

    diag = await reviewer.run(ctx)
    assert diag.failure_category == "UNKNOWN"
    assert diag.confidence < 0.50
    assert "human" in diag.recommended_strategy.lower() or "operator" in diag.recommended_strategy.lower()


# 9. Recovery Strategy Repeats Prevention
@pytest.mark.asyncio
async def test_recovery_strategy_repeats_prevention(clean_env):
    bus = clean_env["bus"]
    supervisor = clean_env["supervisor"]
    mission_mgr = clean_env["mission_mgr"]

    mission = await mission_mgr.create_mission(title="Repetition Guard", goal="Prevent repeat failures")
    supervisor.register_rejected_approach(mission.id, "Direct header comparison without BOM normalization")

    worker = WorkerAgent(agent_id="worker_repeat", event_bus=bus, tools={})
    supervisor.register_worker(worker)

    # Worker attempts action mentioning rejected strategy
    await bus.publish(
        Event(
            mission_id=mission.id,
            task_id="TASK-REP",
            agent_id="worker_repeat",
            type=EventType.TOOL_CALLED,
            payload={
                "tool": "edit_file",
                "arguments": {"path": "src/parser.py"},
                "target": "Direct header comparison without BOM normalization"
            }
        )
    )

    repeated_events = [e for e in clean_env["store"]._events if e.type == EventType.RECOVERY_STRATEGY_REPEATED]
    assert len(repeated_events) >= 1
    assert worker.state.value == "PAUSED"


# 10 & 11. VERIFIER REJECTS WORKER RESULT -> TASK REOPENED (CRITICAL PRODUCT BEHAVIOR)
@pytest.mark.asyncio
async def test_verifier_rejects_worker_claim_and_reopens_task(clean_env):
    bus = clean_env["bus"]
    mission_mgr = clean_env["mission_mgr"]
    task_mgr = clean_env["task_mgr"]
    supervisor = clean_env["supervisor"]
    telemetry = clean_env["telemetry"]

    mission = await mission_mgr.create_mission(title="Verifier Gate", goal="Prove verifier rejects false completion")
    task = Task(id="TASK-VERIF-TEST", mission_id=mission.id, title="CSV Parsing Implementation")
    await task_mgr.initialize_mission_tasks(mission.id, [task])

    worker = WorkerAgent(agent_id="worker_overconfident", event_bus=bus, tools={})
    supervisor.register_worker(worker)

    # Worker claims: "I am finished!"
    await bus.publish(
        Event(
            mission_id=mission.id,
            task_id=task.id,
            agent_id="worker_overconfident",
            type=EventType.TASK_PROGRESS,
            payload={"status": "execution_finished", "summary": "Worker claims task is complete"}
        )
    )

    # Independent Verifier runs tests and FAILS! (e.g. 45 passed, 2 failed)
    await bus.publish(
        Event(
            mission_id=mission.id,
            task_id=task.id,
            agent_id="verifier_01",
            type=EventType.VERIFICATION_RESULT,
            payload={"passed": 45, "failed": 2, "error_signature": "CSV_HEADER_MISMATCH_BOM"}
        )
    )

    # Verification must emit VERIFICATION_FAILED
    failed_verif_events = [e for e in clean_env["store"]._events if e.type == EventType.VERIFICATION_FAILED]
    assert len(failed_verif_events) >= 1

    # Task must be REOPENED in TaskManager
    reopened_events = [e for e in clean_env["store"]._events if e.type == EventType.TASK_REOPENED]
    assert len(reopened_events) >= 1
    assert reopened_events[0].task_id == task.id

    updated_task = await task_mgr.get_task(mission.id, task.id)
    assert updated_task.status == TaskStatus.IN_PROGRESS
    assert updated_task.metadata.get("reopened") is True

    # Worker must be actively paused
    assert worker.state.value == "PAUSED"

    # Telemetry reliability must record verification failure
    m_telem = await telemetry.get_mission_telemetry(mission.id)
    assert m_telem.reliability.verification_failures >= 1


# 12. Two Agents Modify Same File (Contention Detection)
@pytest.mark.asyncio
async def test_two_agents_file_contention_detection(clean_env):
    bus = clean_env["bus"]
    mission_mgr = clean_env["mission_mgr"]
    task_mgr = clean_env["task_mgr"]
    supervisor = clean_env["supervisor"]
    registry = clean_env["registry"]

    mission = await mission_mgr.create_mission(title="Multi-Agent Contention", goal="Coordinate 2 workers")
    task_a = Task(id="TASK-A", mission_id=mission.id, title="Worker A task")
    task_b = Task(id="TASK-B", mission_id=mission.id, title="Worker B task")
    await task_mgr.initialize_mission_tasks(mission.id, [task_a, task_b])

    worker_a = WorkerAgent(agent_id="worker_a", event_bus=bus, tools={})
    worker_b = WorkerAgent(agent_id="worker_b", event_bus=bus, tools={})
    supervisor.register_worker(worker_a)
    supervisor.register_worker(worker_b)
    await registry.register_agent("worker_a", "worker", mission_id=mission.id, agent_instance=worker_a)
    await registry.register_agent("worker_b", "worker", mission_id=mission.id, agent_instance=worker_b)

    # Worker A starts writing to src/parser.py
    await bus.publish(
        Event(
            mission_id=mission.id,
            task_id=task_a.id,
            agent_id="worker_a",
            type=EventType.TOOL_CALLED,
            payload={"tool": "write_file", "arguments": {"path": "src/parser.py"}}
        )
    )

    # Worker B simultaneously attempts to write to the same file
    await bus.publish(
        Event(
            mission_id=mission.id,
            task_id=task_b.id,
            agent_id="worker_b",
            type=EventType.TOOL_CALLED,
            payload={"tool": "write_file", "arguments": {"path": "src/parser.py"}}
        )
    )

    # Contention event emitted
    contention_events = [e for e in clean_env["store"]._events if e.type == EventType.FILE_CONTENTION_DETECTED]
    assert len(contention_events) >= 1
    assert contention_events[0].payload["current_holder"] == "worker_a"
    assert contention_events[0].payload["requesting_agent"] == "worker_b"
    # Worker B must be paused to protect file integrity
    assert worker_b.state.value == "PAUSED"


# 13. Mission Cancelled
@pytest.mark.asyncio
async def test_mission_cancelled_lifecycle(clean_env):
    mission_mgr = clean_env["mission_mgr"]
    mission = await mission_mgr.create_mission(title="To be cancelled", goal="Stop execution")
    await mission_mgr.start_mission(mission.id)
    assert (await mission_mgr.get_mission(mission.id)).status == MissionStatus.RUNNING

    cancelled_mission = await mission_mgr.cancel_mission(mission.id, reason="User abort")
    assert cancelled_mission.status == MissionStatus.CANCELLED


# 14. Human Approval Workflow (Approve Once, Deny, Take Control)
@pytest.mark.asyncio
async def test_human_approval_workflow(clean_env):
    approval_mgr = clean_env["approval_mgr"]

    # Create request
    req = await approval_mgr.create_request(
        mission_id="MSN-APPR",
        agent_id="worker_01",
        action_type="destructive_command",
        target="DROP TABLE users;",
        reason="Agent proposed table truncation",
        risk_level="critical"
    )
    assert req.status.value == "PENDING"

    # Human resolves with DENY
    resolved = await approval_mgr.resolve_request(
        req.id,
        ResolveApprovalPayload(
            action=ApprovalResolutionAction.DENY,
            operator="admin_alice",
            feedback="Do not drop production tables"
        )
    )
    assert resolved.status.value == "DENIED"
    assert resolved.resolved_by == "admin_alice"


# 15. Supervisor Narrative Timeline Generation
@pytest.mark.asyncio
async def test_supervisor_narrative_timeline_builder():
    events = [
        Event(type=EventType.TOOL_CALLED, agent_id="worker_01", payload={"tool": "run_tests", "target": "tests"}),
        Event(type=EventType.TEST_RESULT, payload={"passed": 45, "failed": 2, "error_signature": "CSV_HEADER_MISMATCH_BOM"}),
        Event(type=EventType.SUPERVISOR_ALERT, payload={"anomaly_type": "LOOP_DETECTED", "description": "3 identical failures"}),
        Event(type=EventType.AGENT_PAUSED, agent_id="worker_01", payload={}),
        Event(type=EventType.SUPERVISOR_DECISION, payload={"decision": "DELEGATE", "target_agent": "reviewer", "confidence": 0.94, "reason": "Loop detected"}),
        Event(type=EventType.VERIFICATION_RESULT, payload={"passed": 47, "failed": 0})
    ]

    timeline = SupervisorTimelineBuilder.build_narrative_timeline(events)
    assert len(timeline) == 6
    assert timeline[0].actor == "WORKER"
    assert timeline[0].title == "run_tests()"
    assert timeline[1].actor == "TEST"
    assert "45 passed / 2 failed" in timeline[1].title
    assert timeline[2].actor == "SUPERVISOR"
    assert timeline[2].title == "LOOP DETECTED"
    assert timeline[4].actor == "NEMOTRON"
    assert "DELEGATE → reviewer" in timeline[4].title
    assert timeline[5].actor == "VERIFIER"
    assert "47/47 tests passed" in timeline[5].title
