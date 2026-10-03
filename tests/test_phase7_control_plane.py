import asyncio
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus, MissionConstraints
from core.tasks.manager import TaskManager
from core.tasks.models import Task, TaskStatus
from core.policies.models import PolicyConfig
from agents.registry import AgentRegistry, AgentType, AgentStatus, AgentHealth
from supervisor.engine import SupervisorEngine
from supervisor.decisions import SupervisorAction
from supervisor.state_machine import SupervisorState
from supervisor.approvals import ApprovalManager, ApprovalResolutionAction, ResolveApprovalPayload
from supervisor.telemetry import TelemetryTracker
from apps.api.main import app


class DummyWorker:
    """Mock worker agent supporting pause and resume hooks."""
    def __init__(self, agent_id: str, mission_id: str = "msn_1"):
        self.agent_id = agent_id
        self.mission_id = mission_id
        self.paused = False
        self.resumed = False

    def pause(self):
        self.paused = True
        self.resumed = False

    def resume(self, context=None):
        self.paused = False
        self.resumed = True


@pytest.fixture
def test_setup():
    bus = EventBus()
    mission_mgr = MissionManager(event_bus=bus)
    task_mgr = TaskManager(event_bus=bus)
    registry = AgentRegistry(event_bus=bus)
    telemetry = TelemetryTracker(event_bus=bus)
    approval_mgr = ApprovalManager(event_bus=bus)
    policy = PolicyConfig(pause_after_repeated_failures=3)

    engine = SupervisorEngine(
        event_bus=bus,
        mission_manager=mission_mgr,
        task_manager=task_mgr,
        policy=policy,
        registry=registry,
        telemetry=telemetry,
        approval_manager=approval_mgr
    )

    return {
        "bus": bus,
        "missions": mission_mgr,
        "tasks": task_mgr,
        "registry": registry,
        "telemetry": telemetry,
        "approvals": approval_mgr,
        "engine": engine,
        "policy": policy
    }


# =============================================================================
# 1. State Transitions & Mission Lifecycle Tests
# =============================================================================

@pytest.mark.asyncio
async def test_mission_lifecycle_transitions(test_setup):
    mgr = test_setup["missions"]
    bus = test_setup["bus"]
    recorded_events = []
    await bus.subscribe(lambda e: recorded_events.append(e), event_type=EventType.MISSION_STATUS_CHANGED)

    # CREATED
    m = await mgr.create_mission(title="Data Pipeline", goal="ETL data safely")
    assert m.status == MissionStatus.CREATED

    # -> PLANNING
    m = await mgr.plan_mission(m.id)
    assert m.status == MissionStatus.PLANNING

    # -> RUNNING
    m = await mgr.start_mission(m.id)
    assert m.status == MissionStatus.RUNNING

    # -> PAUSED
    m = await mgr.pause_mission(m.id, reason="Operator check")
    assert m.status == MissionStatus.PAUSED

    # -> INVESTIGATING
    m = await mgr.investigate_mission(m.id, reason="Anomaly spotted")
    assert m.status == MissionStatus.INVESTIGATING

    # -> RECOVERING
    m = await mgr.recover_mission(m.id, reason="Applying fix")
    assert m.status == MissionStatus.RECOVERING

    # -> VERIFYING
    m = await mgr.verify_mission(m.id, reason="Running independent verification")
    assert m.status == MissionStatus.VERIFYING

    # -> COMPLETED
    m = await mgr.complete_mission(m.id, summary="Mission verified and completed")
    assert m.status == MissionStatus.COMPLETED

    # Ensure status changed events were published
    assert len(recorded_events) >= 7


@pytest.mark.asyncio
async def test_mission_failure_states(test_setup):
    mgr = test_setup["missions"]

    # FAILED
    m1 = await mgr.create_mission(title="Failing Mission", goal="Fail cleanly")
    await mgr.start_mission(m1.id)
    await mgr.fail_mission(m1.id, reason="Unrecoverable error")
    assert (await mgr.get_mission(m1.id)).status == MissionStatus.FAILED

    # BLOCKED
    m2 = await mgr.create_mission(title="Blocked Mission", goal="Block cleanly")
    await mgr.start_mission(m2.id)
    await mgr.block_mission(m2.id, reason="Resource dependency missing")
    assert (await mgr.get_mission(m2.id)).status == MissionStatus.BLOCKED

    # WAITING_APPROVAL
    m3 = await mgr.create_mission(title="Approval Mission", goal="Wait cleanly")
    await mgr.start_mission(m3.id)
    await mgr.wait_approval_mission(m3.id, reason="Dangerous operation pending")
    assert (await mgr.get_mission(m3.id)).status == MissionStatus.WAITING_APPROVAL

    # CANCELLED
    m4 = await mgr.create_mission(title="Cancelled Mission", goal="Cancel cleanly")
    await mgr.start_mission(m4.id)
    await mgr.cancel_mission(m4.id, reason="User requested abort")
    assert (await mgr.get_mission(m4.id)).status == MissionStatus.CANCELLED


# =============================================================================
# 2. Agent Registry Tests
# =============================================================================

@pytest.mark.asyncio
async def test_agent_registry_tracking_and_types(test_setup):
    reg = test_setup["registry"]
    bus = test_setup["bus"]

    # Register each agent type
    planner = await reg.register_agent("planner_1", AgentType.PLANNER, model="nemotron-340b", mission_id="msn_1")
    worker = await reg.register_agent("worker_a", AgentType.WORKER, model="nemotron-70b", mission_id="msn_1", task_id="task_1")
    reviewer = await reg.register_agent("reviewer_1", AgentType.REVIEWER, model="nemotron-340b", mission_id="msn_1")
    verifier = await reg.register_agent("verifier_1", AgentType.VERIFIER, model="nemotron-340b", mission_id="msn_1")
    supervisor = await reg.register_agent("supervisor_1", AgentType.SUPERVISOR, model="nemotron-340b", mission_id="msn_1")

    assert planner.agent_type == "PLANNER"
    assert worker.agent_type == "WORKER"
    assert reviewer.agent_type == "REVIEWER"
    assert verifier.agent_type == "VERIFIER"
    assert supervisor.agent_type == "SUPERVISOR"

    # Verify query by agent type & mission
    workers = await reg.list_agents(mission_id="msn_1", agent_type="WORKER")
    assert len(workers) == 1
    assert workers[0].agent_id == "worker_a"
    assert workers[0].current_task == "task_1"

    # Simulate activity via EventBus
    await bus.publish(Event(mission_id="msn_1", task_id="task_1", agent_id="worker_a", type=EventType.TASK_PROGRESS, payload={"step": 1}))
    await bus.publish(Event(mission_id="msn_1", task_id="task_1", agent_id="worker_a", type=EventType.TOOL_CALLED, payload={"tool": "read_file"}))
    await bus.publish(Event(mission_id="msn_1", task_id="task_1", agent_id="worker_a", type=EventType.SUPERVISOR_INTERVENTION, payload={"intervention": "PAUSE"}))

    rec = await reg.get_agent("worker_a")
    assert rec.iterations == 1
    assert rec.tool_calls == 1
    assert rec.interventions == 1


# =============================================================================
# 3. Multi-Agent Support & Mission Isolation Tests
# =============================================================================

@pytest.mark.asyncio
async def test_multi_agent_execution_under_one_mission(test_setup):
    engine = test_setup["engine"]
    task_mgr = test_setup["tasks"]
    missions = test_setup["missions"]

    m = await missions.create_mission(title="Multi-Worker Mission", goal="Parallel tasks")
    t1 = Task(id="T-01", mission_id=m.id, title="Subtask 1", order=1)
    t2 = Task(id="T-02", mission_id=m.id, title="Subtask 2", order=2)
    await task_mgr.initialize_mission_tasks(m.id, [t1, t2])

    worker_a = DummyWorker("worker_a", mission_id=m.id)
    worker_b = DummyWorker("worker_b", mission_id=m.id)
    engine.register_worker(worker_a, mission_id=m.id)
    engine.register_worker(worker_b, mission_id=m.id)

    await task_mgr.start_task(m.id, t1.id, worker_a.agent_id)
    await task_mgr.start_task(m.id, t2.id, worker_b.agent_id)

    # Pause only worker_a
    await engine.pause(mission_id=m.id, reason="Worker A pause", agent_id="worker_a")
    assert worker_a.paused is True
    assert worker_b.paused is False

    # Resume worker_a
    await engine.resume(mission_id=m.id, reason="Worker A resume", agent_id="worker_a")
    assert worker_a.paused is False
    assert worker_a.resumed is True


@pytest.mark.asyncio
async def test_mission_isolation_no_cross_contamination(test_setup):
    engine = test_setup["engine"]
    missions = test_setup["missions"]

    m1 = await missions.create_mission(title="Mission 1", goal="Isolated 1")
    m2 = await missions.create_mission(title="Mission 2", goal="Isolated 2")

    worker_1 = DummyWorker("worker_m1", mission_id=m1.id)
    worker_2 = DummyWorker("worker_m2", mission_id=m2.id)
    engine.register_worker(worker_1, mission_id=m1.id)
    engine.register_worker(worker_2, mission_id=m2.id)

    # Pause mission 1 only
    await engine.pause(mission_id=m1.id, reason="Pause m1")

    assert worker_1.paused is True
    assert worker_2.paused is False

    # State machines must be isolated
    sm1 = engine.get_state_machine(m1.id)
    sm2 = engine.get_state_machine(m2.id)
    assert sm1.current_state == SupervisorState.PAUSED
    assert sm2.current_state != SupervisorState.PAUSED


# =============================================================================
# 4. Human Intervention & Approval Flow Tests
# =============================================================================

@pytest.mark.asyncio
async def test_approval_flow_explicit_resolution(test_setup):
    engine = test_setup["engine"]
    approvals = test_setup["approvals"]
    missions = test_setup["missions"]

    m = await missions.create_mission(title="Approval Flow", goal="Test safety gate")
    worker = DummyWorker("worker_crit", mission_id=m.id)
    engine.register_worker(worker, mission_id=m.id)

    # Request approval for dangerous command
    req = await engine.request_approval(
        mission_id=m.id,
        agent_id=worker.agent_id,
        action_type="DANGEROUS_ACTION",
        target="rm -rf /var/lib/data",
        reason="Dangerous directory deletion",
        risk_level="critical"
    )

    assert req is not None
    assert req.status.value == "PENDING"
    assert worker.paused is True

    # Absence of response must remain pending
    pending_list = await approvals.list_requests(mission_id=m.id)
    assert len(pending_list) == 1
    assert pending_list[0].status.value == "PENDING"

    # Explicit Operator Approval
    resolved = await approvals.resolve_request(
        req.id,
        ResolveApprovalPayload(
            action=ApprovalResolutionAction.APPROVE_ONCE,
            operator="lead_engineer",
            feedback="Reviewed and approved for temp directory"
        )
    )
    assert resolved.status.value == "APPROVED"
    assert resolved.resolved_by == "lead_engineer"


@pytest.mark.asyncio
async def test_human_required_and_take_control(test_setup):
    engine = test_setup["engine"]
    missions = test_setup["missions"]

    m = await missions.create_mission(title="Unrecoverable Flow", goal="Test intervention")
    worker = DummyWorker("worker_err", mission_id=m.id)
    engine.register_worker(worker, mission_id=m.id)

    # Trigger HUMAN_REQUIRED
    req = await engine.human_required(
        mission_id=m.id,
        reason="Exceeded maximum recovery attempts",
        agent_id=worker.agent_id
    )

    assert req.action_type == "HUMAN_REQUIRED"
    assert (await missions.get_mission(m.id)).status == MissionStatus.WAITING_APPROVAL
    assert worker.paused is True

    # Operator takes control
    await engine.take_control(mission_id=m.id, operator="admin_alice", reason="Manual diagnosis")
    m_after = await missions.get_mission(m.id)
    assert m_after.status == MissionStatus.PAUSED


# =============================================================================
# 5. Telemetry Tracking Tests
# =============================================================================

@pytest.mark.asyncio
async def test_telemetry_execution_reliability_risk_ci(test_setup):
    bus = test_setup["bus"]
    telem_tracker = test_setup["telemetry"]
    mid = "msn_telemetry_test"

    # 1. Execution events
    await bus.publish(Event(mission_id=mid, task_id="t1", agent_id="w1", type=EventType.TOOL_CALLED, payload={"tool": "read_file"}))
    await bus.publish(Event(mission_id=mid, task_id="t1", agent_id="w1", type=EventType.TASK_PROGRESS, payload={"step": 1}))
    await bus.publish(Event(mission_id=mid, task_id="t1", agent_id="w1", type=EventType.TASK_COMPLETED, payload={}))

    # 2. Reliability & Failures
    await bus.publish(Event(mission_id=mid, task_id="t2", agent_id="w1", type=EventType.TEST_FAILED, payload={"failed": 1}))
    await bus.publish(Event(mission_id=mid, task_id="t2", agent_id="w1", type=EventType.SUPERVISOR_INTERVENTION, payload={"intervention": "PAUSE"}))
    await bus.publish(Event(mission_id=mid, task_id="t2", agent_id="w1", type=EventType.RECOVERY_STARTED, payload={}))
    await bus.publish(Event(mission_id=mid, task_id="t2", agent_id="w1", type=EventType.VERIFICATION_FAILED, payload={}))

    # 3. Risk
    await bus.publish(Event(mission_id=mid, agent_id="w1", type=EventType.DANGER_DETECTED, payload={"error": "blocked"}))
    await bus.publish(Event(mission_id=mid, agent_id="w1", type=EventType.APPROVAL_REQUESTED, payload={}))

    # 4. CI
    await bus.publish(Event(mission_id=mid, agent_id="w1", type=EventType.CI_BUILD_TRIGGERED, payload={"build_id": "1"}))
    await bus.publish(Event(mission_id=mid, agent_id="w1", type=EventType.CI_BUILD_FAILED, payload={"build_id": "1"}))
    await bus.publish(Event(mission_id=mid, agent_id="w1", type=EventType.CI_TEST_RESULTS_AVAILABLE, payload={"tests_failed": 2}))

    m_telem = await telem_tracker.get_mission_telemetry(mid)

    # Check Execution
    assert m_telem.execution.tool_calls == 1
    assert m_telem.execution.iteration_count == 1
    assert m_telem.execution.iterations == 1
    assert m_telem.execution.completed_tasks == 1
    assert m_telem.execution.runtime_seconds >= 0.0

    # Check Reliability
    assert m_telem.reliability.interventions >= 1
    assert m_telem.reliability.recovery_attempts == 1
    assert m_telem.reliability.verification_failures >= 1

    # Check Risk
    assert m_telem.risk.dangerous_actions == 1
    assert m_telem.risk.approval_requests >= 1

    # Check CI
    assert m_telem.ci.jenkins_builds == 1
    assert m_telem.ci.build_failures == 1
    assert m_telem.ci.test_failures == 2

    # Check Per-Agent Telemetry
    assert "w1" in m_telem.agents
    assert m_telem.agents["w1"].tool_calls == 1

    # Verify no fabricated token/costs if provider doesn't expose them
    assert m_telem.cost.estimated_cost_usd == 0.0


# =============================================================================
# 6. API Endpoints Tests
# =============================================================================

def test_api_full_control_plane_endpoints():
    client = TestClient(app)

    # 1. Create Mission
    res_m = client.post("/api/missions", json={"title": "API Mission", "goal": "Verify all endpoints"})
    assert res_m.status_code == 200
    mid = res_m.json()["id"]

    # 2. Get Mission State
    res_st = client.get(f"/api/missions/{mid}/state")
    assert res_st.status_code == 200
    assert res_st.json()["mission_id"] == mid
    assert res_st.json()["status"] == "CREATED"

    # 3. Transition Mission State
    res_up = client.post(f"/api/missions/{mid}/status", json={"status": "PLANNING", "reason": "Planning started"})
    assert res_up.status_code == 200
    assert res_up.json()["mission"]["status"] == "PLANNING"

    # 4. Register Agent
    res_ag = client.post("/api/agents", json={
        "agent_id": "api_worker_1",
        "agent_type": "WORKER",
        "mission_id": mid,
        "task_id": "T-API-01"
    })
    assert res_ag.status_code == 200
    assert res_ag.json()["agent"]["agent_id"] == "api_worker_1"

    # 5. Get and Update Agent State
    res_ag_st = client.get("/api/agents/api_worker_1/state")
    assert res_ag_st.status_code == 200
    assert res_ag_st.json()["agent_id"] == "api_worker_1"

    res_ag_put = client.put("/api/agents/api_worker_1/state", json={"status": "RUNNING", "health": "HEALTHY"})
    assert res_ag_put.status_code == 200
    assert res_ag_put.json()["agent"]["status"] == "RUNNING"

    # 6. Create, Query and Update Task
    res_t_post = client.post(f"/api/missions/{mid}/tasks", json={
        "id": "T-API-01",
        "title": "Validate API routes",
        "expected_files": ["apps/api/main.py"]
    })
    assert res_t_post.status_code == 200

    res_t_get = client.get(f"/api/missions/{mid}/tasks/T-API-01")
    assert res_t_get.status_code == 200
    assert res_t_get.json()["title"] == "Validate API routes"

    res_t_stat = client.post(f"/api/missions/{mid}/tasks/T-API-01/status", json={"status": "COMPLETED", "summary": "Routes validated"})
    assert res_t_stat.status_code == 200
    assert res_t_stat.json()["task"]["status"] == "COMPLETED"

    # 7. Approvals Flow via API
    res_appr_post = client.post("/api/approvals", json={
        "mission_id": mid,
        "agent_id": "api_worker_1",
        "action_type": "DANGEROUS_ACTION",
        "target": "drop database",
        "reason": "Test approval",
        "risk_level": "critical"
    })
    assert res_appr_post.status_code == 200
    appr_id = res_appr_post.json()["approval"]["id"]

    res_appr_get = client.get(f"/api/approvals/{appr_id}")
    assert res_appr_get.status_code == 200
    assert res_appr_get.json()["status"] == "PENDING"

    res_appr_res = client.post(f"/api/approvals/{appr_id}/resolve", json={"action": "DENY", "operator": "lead"})
    assert res_appr_res.status_code == 200
    assert res_appr_res.json()["approval"]["status"] == "DENIED"

    # 8. Pause, Resume, Cancel via API
    res_pause = client.post(f"/api/missions/{mid}/pause", json={"reason": "Operator pause"})
    assert res_pause.status_code == 200
    assert res_pause.json()["status"] == "paused"

    res_res = client.post(f"/api/missions/{mid}/resume")
    assert res_res.status_code == 200
    assert res_res.json()["status"] == "resumed"

    res_cancel = client.post(f"/api/missions/{mid}/cancel", params={"reason": "Operator cancel"})
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "cancelled"

    # 9. Query Supervisor Events via API
    res_ev = client.get("/api/supervisor/events", params={"mission_id": mid})
    assert res_ev.status_code == 200
    assert "events" in res_ev.json()


# =============================================================================
# 7. WebSocket Event Streaming Tests
# =============================================================================

def test_websocket_event_streaming_and_keepalive():
    client = TestClient(app)

    with client.websocket_connect("/ws/events") as websocket:
        # Ping / Keepalive test
        websocket.send_text("ping")
        resp = websocket.receive_json()
        assert resp["type"] == "pong"
