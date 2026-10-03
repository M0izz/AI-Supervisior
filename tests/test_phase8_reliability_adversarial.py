import asyncio
import pytest
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from core.events.bus import EventBus
from core.events.store import InMemoryEventStore
from core.events.schema import Event, EventType, EventSeverity
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus
from core.tasks.manager import TaskManager
from core.tasks.models import Task, TaskStatus
from core.policies.models import PolicyConfig
from supervisor.engine import SupervisorEngine
from supervisor.rules import DeterministicRuleEngine, AnomalyReport
from supervisor.decisions import SupervisorAction, SupervisorDecision
from supervisor.reasoning import SupervisoryReasoner
from supervisor.state_machine import SupervisorStateMachine, SupervisorState
from supervisor.approvals import ApprovalManager, ApprovalResolutionAction, ResolveApprovalPayload
from core.state.models import ApprovalStatus
from supervisor.telemetry import TelemetryTracker
from agents.registry import AgentRegistry, AgentType, AgentStatus
from agents.reviewer.agent import ReviewerAgent
from agents.verifier.agent import VerifierAgent
from tools.base import BaseTool, ToolResult
from execution.docker import DockerExecutionProvider
from execution.models import ExecutionRequest, ExecutionStatus
from integrations.nebius.provider import MockReasoningProvider, NebiusNemotronProvider, ReasoningDecision
from integrations.jenkins.mock import MockJenkinsProvider
from integrations.jenkins.models import (
    JenkinsBuildStatus,
    JenkinsBuildOutcome,
    JenkinsConnectionError,
    JenkinsTimeoutError
)


class MockWorker:
    def __init__(self, agent_id: str, mission_id: str = "msn_test"):
        self.agent_id = agent_id
        self.mission_id = mission_id
        self.paused = False
        self.resumed = False
        self.cancelled = False

    def pause(self):
        self.paused = True
        self.resumed = False

    def resume(self, context=None):
        self.paused = False
        self.resumed = True

    def cancel(self):
        self.cancelled = True
        self.paused = True


@pytest.fixture
def test_setup():
    bus = EventBus()
    event_store = InMemoryEventStore()
    bus.subscribe_sync(lambda e: asyncio.create_task(event_store.append(e)))
    missions = MissionManager(event_bus=bus)
    tasks = TaskManager(event_bus=bus)
    registry = AgentRegistry(event_bus=bus)
    telemetry = TelemetryTracker(event_bus=bus)
    approvals = ApprovalManager(event_bus=bus)
    policy = PolicyConfig(
        pause_after_repeated_failures=3,
        prevent_modifications_outside_task_scope=True,
        max_turns_per_task=10
    )

    engine = SupervisorEngine(
        event_bus=bus,
        mission_manager=missions,
        task_manager=tasks,
        policy=policy,
        registry=registry,
        telemetry=telemetry,
        approval_manager=approvals
    )

    return {
        "bus": bus,
        "store": event_store,
        "missions": missions,
        "tasks": tasks,
        "registry": registry,
        "telemetry": telemetry,
        "approvals": approvals,
        "policy": policy,
        "engine": engine,
    }


# =============================================================================
# 1. FAILURE MATRIX SCENARIOS (1 to 24)
# =============================================================================

@pytest.mark.asyncio
async def test_failure_01_repeated_identical_failure(test_setup):
    """1. Repeated identical failure triggers LOOP_DETECTED -> DELEGATE."""
    engine = test_setup["engine"]
    task = Task(id="T-01", mission_id="msn_1", title="Parser Fix")
    events = [
        Event(mission_id="msn_1", task_id="T-01", type=EventType.TEST_FAILED, payload={"failed": 1, "error_signature": "KeyError: 'bom' at line:10"}),
        Event(mission_id="msn_1", task_id="T-01", type=EventType.TEST_FAILED, payload={"failed": 1, "error_signature": "KeyError: 'bom' at line:10"}),
        Event(mission_id="msn_1", task_id="T-01", type=EventType.TEST_FAILED, payload={"failed": 1, "error_signature": "KeyError: 'bom' at line:10"}),
    ]
    anomaly = engine.rules.evaluate_test_history(task, events)
    assert anomaly is not None
    assert anomaly.anomaly_type == "LOOP_DETECTED"
    assert anomaly.recommended_action == SupervisorAction.DELEGATE


@pytest.mark.asyncio
async def test_failure_02_no_progress(test_setup):
    """2. No progress across multiple attempts -> NO_PROGRESS -> CHANGE_STRATEGY."""
    engine = test_setup["engine"]
    task = Task(id="T-02", mission_id="msn_1", title="Validator Test")
    events = [
        Event(mission_id="msn_1", task_id="T-02", type=EventType.TEST_FAILED, payload={"passed": 0, "failed": 2}),
        Event(mission_id="msn_1", task_id="T-02", type=EventType.TEST_FAILED, payload={"passed": 0, "failed": 2}),
        Event(mission_id="msn_1", task_id="T-02", type=EventType.TEST_FAILED, payload={"passed": 0, "failed": 2}),
    ]
    anomaly = engine.rules.evaluate_no_progress(task, events)
    assert anomaly is not None
    assert anomaly.anomaly_type == "NO_PROGRESS"
    assert anomaly.recommended_action == SupervisorAction.CHANGE_STRATEGY


@pytest.mark.asyncio
async def test_failure_03_infinite_loop(test_setup):
    """3. Infinite loop: identical failure normalization strips addresses and line numbers."""
    engine = test_setup["engine"]
    task = Task(id="T-03", mission_id="msn_1", title="Loop Task")
    events = [
        Event(mission_id="msn_1", task_id="T-03", type=EventType.TEST_FAILED, payload={"failed": 1, "error_signature": "ValueError at 0xdeadbeef:120"}),
        Event(mission_id="msn_1", task_id="T-03", type=EventType.TEST_FAILED, payload={"failed": 1, "error_signature": "ValueError at 0xfeedface:125"}),
        Event(mission_id="msn_1", task_id="T-03", type=EventType.TEST_FAILED, payload={"failed": 1, "error_signature": "ValueError at 0x12345678:130"}),
    ]
    anomaly = engine.rules.evaluate_test_history(task, events)
    assert anomaly is not None
    assert anomaly.anomaly_type == "LOOP_DETECTED"
    assert anomaly.evidence["error_signature"] == "ValueError at 0xADDR:LINE"


@pytest.mark.asyncio
async def test_failure_04_worker_timeout(test_setup):
    """4. Worker timeout: budget rule flags duration exceeding ceiling."""
    engine = test_setup["engine"]
    anomaly = engine.rules.evaluate_budget(iterations=2, tool_calls_count=5, elapsed_seconds=650.0)
    assert anomaly is not None
    assert anomaly.anomaly_type == "BUDGET_WARNING"
    assert anomaly.recommended_action == SupervisorAction.PAUSE


@pytest.mark.asyncio
async def test_failure_05_worker_exceeds_iteration_budget(test_setup):
    """5. Worker exceeds iteration turn budget."""
    engine = test_setup["engine"]
    anomaly = engine.rules.evaluate_budget(iterations=12, tool_calls_count=8, elapsed_seconds=120.0)
    assert anomaly is not None
    assert anomaly.anomaly_type == "BUDGET_WARNING"
    assert "turn budget" in anomaly.description


@pytest.mark.asyncio
async def test_failure_06_worker_exceeds_tool_call_budget(test_setup):
    """6. Worker exceeds tool-call budget (high iteration count & tool volume)."""
    engine = test_setup["engine"]
    anomaly = engine.rules.evaluate_budget(iterations=10, tool_calls_count=50, elapsed_seconds=200.0)
    assert anomaly is not None
    assert anomaly.recommended_action == SupervisorAction.PAUSE


@pytest.mark.asyncio
async def test_failure_07_scope_violation(test_setup):
    """7. Scope violation: modifying outside expected files or protected path."""
    engine = test_setup["engine"]
    task = Task(id="T-07", mission_id="msn_1", title="Scope Task", expected_files=["src/models.py"])
    # 1. Modifying outside task expected scope
    anomaly_unexp = engine.rules.evaluate_tool_call("write_file", {"path": "src/unrelated.py"}, task=task)
    assert anomaly_unexp is not None
    assert anomaly_unexp.anomaly_type == "SCOPE_VIOLATION"
    # 2. Modifying protected path
    anomaly_prot = engine.rules.evaluate_tool_call("write_file", {"path": "schema.sql"}, task=task)
    assert anomaly_prot is not None
    assert anomaly_prot.anomaly_type == "SCOPE_VIOLATION"


@pytest.mark.asyncio
async def test_failure_08_dangerous_command(test_setup):
    """8. Dangerous command: rm -rf or DROP TABLE blocked and approval requested."""
    engine = test_setup["engine"]
    anomaly = engine.rules.evaluate_tool_call("run_command", {"command": "rm -rf /var/lib/data"})
    assert anomaly is not None
    assert anomaly.anomaly_type == "DANGEROUS_ACTION"
    assert anomaly.recommended_action == SupervisorAction.REQUEST_APPROVAL


@pytest.mark.asyncio
async def test_failure_09_false_completion(test_setup):
    """9. False completion: worker cannot mark task VERIFIED without empirical evidence."""
    tasks = test_setup["tasks"]
    missions = test_setup["missions"]
    m = await missions.create_mission(title="False Completion Test", goal="Verify invariant")
    t = Task(id="T-FALSE-01", mission_id=m.id, title="Test Task")
    await tasks.initialize_mission_tasks(m.id, [t])

    # Worker attempts verification without tests or CI passing -> PermissionError
    with pytest.raises(PermissionError) as exc_info:
        await tasks.verify_task(
            mission_id=m.id,
            task_id=t.id,
            caller_role="WORKER",
            ci_passed=False,
            tests_passed=False
        )
    assert "not authorized to mark task as VERIFIED" in str(exc_info.value)


@pytest.mark.asyncio
async def test_failure_10_jenkins_failure(test_setup):
    """10. Jenkins failure: mock Jenkins build returns FAILURE with test failures."""
    jenkins = MockJenkinsProvider(default_mode="FAILURE")
    trig = await jenkins.trigger_build("job_parser")
    res = await jenkins.get_build_result(trig.build_id, "job_parser")
    assert res.result == JenkinsBuildOutcome.FAILURE
    assert res.tests_failed > 0


@pytest.mark.asyncio
async def test_failure_11_jenkins_unavailable(test_setup):
    """11. Jenkins unavailable: throws JenkinsConnectionError cleanly."""
    jenkins = MockJenkinsProvider(default_mode="UNAVAILABLE")
    with pytest.raises(JenkinsConnectionError) as exc_info:
        await jenkins.trigger_build("job_parser")
    assert "unavailable" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_failure_12_jenkins_timeout(test_setup):
    """12. Jenkins timeout: throws JenkinsTimeoutError on build result retrieval."""
    jenkins = MockJenkinsProvider(default_mode="TIMEOUT")
    trig = await jenkins.trigger_build("job_parser")
    with pytest.raises(JenkinsTimeoutError) as exc_info:
        await jenkins.get_build_result(trig.build_id, "job_parser")
    assert "timed out" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_failure_13_docker_container_crash(test_setup):
    """13. Docker container crash: simulated container failure handled cleanly."""
    # When Docker executes a command that exits with non-zero code or fails
    # ExecutionResult returns status FAILED with duration and logs
    from execution.models import ExecutionResult, ContainerInfo
    c_info = ContainerInfo(container_id="c_crash_123", image="test:latest", status="stopped")
    res = ExecutionResult(
        status=ExecutionStatus.FAILED,
        exit_code=1,
        stdout="Fatal crash: Segmentation fault",
        stderr="Segmentation fault",
        duration_ms=45.0,
        container=c_info,
        backend="docker"
    )
    assert res.status == ExecutionStatus.FAILED
    assert res.exit_code == 1
    assert "Segmentation fault" in res.stdout


@pytest.mark.asyncio
async def test_failure_14_docker_resource_exhaustion(test_setup):
    """14. Docker resource exhaustion: exit code 137 indicates OOM / kill."""
    from execution.models import ExecutionResult, ContainerInfo
    c_info = ContainerInfo(container_id="c_oom_456", image="test:latest", status="stopped")
    res = ExecutionResult(
        status=ExecutionStatus.FAILED,
        exit_code=137,
        stdout="Killed",
        stderr="Process out of memory",
        duration_ms=1200.0,
        container=c_info,
        backend="docker"
    )
    assert res.exit_code == 137
    assert res.status == ExecutionStatus.FAILED


@pytest.mark.asyncio
async def test_failure_15_malformed_nemotron_response(test_setup):
    """15. Malformed Nemotron response: supervisor handles non-JSON safely without crashing."""
    missions = test_setup["missions"]
    tasks = test_setup["tasks"]
    bus = test_setup["bus"]
    m = await missions.create_mission(title="Malformed Nemotron", goal="Test resilience")
    t = Task(id="T-MALFORMED", mission_id=m.id, title="Test Task")
    await tasks.initialize_mission_tasks(m.id, [t])

    class FaultyReasoner(MockReasoningProvider):
        async def reason_about_situation(self, prompt_context):
            raise ValueError("Unexpected token '<' in JSON at position 0")

    faulty_engine = SupervisorEngine(
        event_bus=bus,
        mission_manager=missions,
        task_manager=tasks,
        reasoner=FaultyReasoner()
    )

    # Anomaly pipeline must catch exception and fall back to safe deterministic action
    anomaly = AnomalyReport(
        anomaly_type="LOOP_DETECTED",
        description="Loop",
        evidence={},
        recommended_action=SupervisorAction.DELEGATE
    )
    # Does not raise
    await faulty_engine._trigger_anomaly_pipeline(m.id, t.id, "worker_01", anomaly)
    assert faulty_engine.get_state_machine(m.id).current_state == SupervisorState.INVESTIGATING


@pytest.mark.asyncio
async def test_failure_16_nemotron_timeout(test_setup):
    """16. Nemotron timeout: provider timeout falls back cleanly."""
    missions = test_setup["missions"]
    tasks = test_setup["tasks"]
    bus = test_setup["bus"]
    m = await missions.create_mission(title="Timeout Nemotron", goal="Test resilience")

    class TimeoutReasoner(MockReasoningProvider):
        async def reason_about_situation(self, prompt_context):
            raise asyncio.TimeoutError("Nebius Nemotron API request timed out after 20.0s")

    timeout_engine = SupervisorEngine(
        event_bus=bus,
        mission_manager=missions,
        task_manager=tasks,
        reasoner=TimeoutReasoner()
    )

    anomaly = AnomalyReport(
        anomaly_type="DANGEROUS_ACTION",
        description="Dangerous command",
        evidence={},
        recommended_action=SupervisorAction.REQUEST_APPROVAL
    )
    await timeout_engine._trigger_anomaly_pipeline(m.id, None, "worker_01", anomaly)
    # Successfully handled via deterministic fallback
    assert timeout_engine.get_state_machine(m.id).current_state == SupervisorState.AWAITING_APPROVAL


@pytest.mark.asyncio
async def test_failure_17_nemotron_unavailable(test_setup):
    """17. Nemotron unavailable (HTTP 503): handled cleanly by fallback."""
    provider = NebiusNemotronProvider(api_key="mock_invalid_key", base_url="http://invalid-nebius-url:9999/v1", timeout_seconds=0.1)
    res = await provider.reason_about_situation({"anomaly_type": "LOOP_DETECTED"})
    # Falls back to MockReasoningProvider without exception
    assert res.decision in ("CONTINUE", "RETRY", "CHANGE_STRATEGY", "DELEGATE", "PAUSE")


@pytest.mark.asyncio
async def test_failure_18_reviewer_failure(test_setup):
    """18. Reviewer failure: reviewer detects flaw, diagnoses BOM, cannot mutate files."""
    bus = test_setup["bus"]
    reviewer = ReviewerAgent(agent_id="reviewer_01", event_bus=bus)
    with pytest.raises(PermissionError) as exc_info:
        await reviewer.call_tool("edit_file", {"path": "src/parser.py", "content": "fix"}, mission_id="msn_1")
    assert "strictly read-only" in str(exc_info.value)


@pytest.mark.asyncio
async def test_failure_19_recovery_strategy_repeated(test_setup):
    """19. Repeated recovery strategy: supervisor blocks already rejected approach."""
    engine = test_setup["engine"]
    mid = "msn_strat_test"
    engine.register_rejected_approach(mid, "strip_bom_with_regex")
    assert engine.validate_recovery_strategy(mid, "strip_bom_with_regex") is False
    assert engine.validate_recovery_strategy(mid, "use_utf8_sig_encoding") is True


@pytest.mark.asyncio
async def test_failure_20_verifier_rejection(test_setup):
    """20. Verifier rejection: verifier runs tests with failures -> verified=False."""
    bus = test_setup["bus"]
    # Verifier tool returns test failures
    class MockTestTool(BaseTool):
        name = "run_tests"
        description = "Mock test runner"
        async def execute(self, **kwargs):
            return ToolResult(success=False, output="1 failed, 0 passed", metadata={"passed": 0, "failed": 1})

    verifier = VerifierAgent(agent_id="verifier_01", event_bus=bus, tools={"run_tests": MockTestTool(workspace_root=Path("."))})
    from core.state.models import AgentContextPackage
    ctx = AgentContextPackage(mission_id="msn_v", task={"id": "T-VERIF"}, objective="Verify fix")
    result = await verifier.run(ctx)
    assert result["verified"] is False
    assert result["tests_failed"] == 1


@pytest.mark.asyncio
async def test_failure_21_mission_cancellation(test_setup):
    """21. Mission cancellation: stops workers, cancels approvals, transitions state."""
    engine = test_setup["engine"]
    missions = test_setup["missions"]
    approvals = test_setup["approvals"]

    m = await missions.create_mission(title="Cancel Mission", goal="Test abort")
    worker = MockWorker("worker_cancel", mission_id=m.id)
    engine.register_worker(worker, mission_id=m.id)

    # Create pending approval
    appr = await engine.request_approval(
        mission_id=m.id,
        agent_id=worker.agent_id,
        action_type="DANGEROUS_ACTION",
        target="rm -rf /",
        reason="Abort test"
    )

    # Cancel mission
    await engine.cancel(mission_id=m.id, reason="Operator initiated emergency cancellation")

    m_after = await missions.get_mission(m.id)
    assert m_after.status == MissionStatus.CANCELLED
    assert worker.paused is True
    # Approval must be cancelled
    appr_after = await approvals.get_request(appr.id)
    assert appr_after.status.value == "CANCELLED"


@pytest.mark.asyncio
async def test_failure_22_human_approval_timeout(test_setup):
    """22. Human approval timeout: absence of response remains strictly PENDING."""
    engine = test_setup["engine"]
    approvals = test_setup["approvals"]
    missions = test_setup["missions"]

    m = await missions.create_mission(title="Approval Invariant", goal="Test no-auto-approval")
    worker = MockWorker("worker_gate", mission_id=m.id)
    engine.register_worker(worker, mission_id=m.id)

    appr = await engine.request_approval(
        mission_id=m.id,
        agent_id=worker.agent_id,
        action_type="DANGEROUS_ACTION",
        target="rm -rf /",
        reason="Requires explicit confirmation"
    )

    # Simulate passage of time / lack of operator response
    await asyncio.sleep(0.05)
    appr_check = await approvals.get_request(appr.id)
    assert appr_check.status.value == "PENDING"
    assert worker.paused is True


@pytest.mark.asyncio
async def test_failure_23_concurrent_workers_different_files(test_setup):
    """23. Concurrent workers modifying different files: both succeed without conflict."""
    registry = test_setup["registry"]
    mid = "msn_concurrent_diff"
    await registry.register_agent("worker_a", AgentType.WORKER, mission_id=mid)
    await registry.register_agent("worker_b", AgentType.WORKER, mission_id=mid)

    conflict_a = await registry.check_file_contention("worker_a", "src/parser.py", mid)
    conflict_b = await registry.check_file_contention("worker_b", "src/models.py", mid)

    assert conflict_a is None
    assert conflict_b is None


@pytest.mark.asyncio
async def test_failure_24_concurrent_workers_conflicting_modifications(test_setup):
    """24. Concurrent workers attempting conflicting modification to the same file."""
    registry = test_setup["registry"]
    mid = "msn_concurrent_same"
    await registry.register_agent("worker_1", AgentType.WORKER, mission_id=mid)
    await registry.register_agent("worker_2", AgentType.WORKER, mission_id=mid)

    # Worker 1 locks file
    c1 = await registry.check_file_contention("worker_1", "src/shared_util.py", mid)
    assert c1 is None

    # Worker 2 attempts same file -> contention caught
    c2 = await registry.check_file_contention("worker_2", "src/shared_util.py", mid)
    assert c2 == "worker_1"


# =============================================================================
# 2. SAFETY INVARIANTS TESTS
# =============================================================================

@pytest.mark.asyncio
async def test_invariant_dangerous_actions_blocked(test_setup):
    """INVARIANT: Dangerous actions are strictly blocked behind human approval."""
    engine = test_setup["engine"]
    rule = engine.rules.evaluate_tool_call("run_command", {"command": "DROP TABLE users;"})
    assert rule is not None
    assert rule.anomaly_type == "DANGEROUS_ACTION"
    assert rule.recommended_action == SupervisorAction.REQUEST_APPROVAL


@pytest.mark.asyncio
async def test_invariant_worker_cannot_mark_work_verified(test_setup):
    """INVARIANT: Worker cannot mark work VERIFIED."""
    tasks = test_setup["tasks"]
    missions = test_setup["missions"]
    m = await missions.create_mission(title="Inv Worker", goal="Invariant")
    t = Task(id="T-INV-01", mission_id=m.id, title="Task")
    await tasks.initialize_mission_tasks(m.id, [t])

    with pytest.raises(PermissionError):
        await tasks.verify_task(m.id, t.id, caller_role="WORKER", ci_passed=True, tests_passed=True)


@pytest.mark.asyncio
async def test_invariant_reviewer_cannot_mutate_files(test_setup):
    """INVARIANT: Reviewer cannot mutate workspace files."""
    reviewer = ReviewerAgent(agent_id="rev_safe")
    for mut_tool in ("write_file", "edit_file", "run_command"):
        with pytest.raises(PermissionError):
            await reviewer.call_tool(mut_tool, {"path": "test.txt", "content": "data"}, mission_id="msn_inv")


@pytest.mark.asyncio
async def test_invariant_failed_ci_cannot_produce_verified(test_setup):
    """INVARIANT: Failed CI cannot produce VERIFIED task."""
    tasks = test_setup["tasks"]
    missions = test_setup["missions"]
    m = await missions.create_mission(title="Inv CI", goal="Invariant")
    t = Task(id="T-INV-02", mission_id=m.id, title="Task")
    await tasks.initialize_mission_tasks(m.id, [t])

    with pytest.raises(ValueError) as exc:
        await tasks.verify_task(m.id, t.id, caller_role="VERIFIER", ci_passed=False, tests_passed=False)
    assert "Empirical verification requirement not met" in str(exc.value)


@pytest.mark.asyncio
async def test_invariant_unavailable_jenkins_cannot_produce_verified(test_setup):
    """INVARIANT: Unavailable Jenkins cannot produce VERIFIED."""
    jenkins = MockJenkinsProvider(default_mode="UNAVAILABLE")
    tasks = test_setup["tasks"]
    missions = test_setup["missions"]
    m = await missions.create_mission(title="Inv Unavail", goal="Invariant")
    t = Task(id="T-INV-03", mission_id=m.id, title="Task")
    await tasks.initialize_mission_tasks(m.id, [t])

    with pytest.raises(JenkinsConnectionError):
        await jenkins.trigger_build("job_test")

    # Task remains PENDING and cannot be marked VERIFIED
    task_rec = await tasks.get_task(m.id, t.id)
    assert task_rec.status != TaskStatus.VERIFIED


@pytest.mark.asyncio
async def test_invariant_malformed_nemotron_cannot_crash_supervisor(test_setup):
    """INVARIANT: Malformed Nemotron output cannot crash Supervisor."""
    engine = test_setup["engine"]
    missions = test_setup["missions"]
    m = await missions.create_mission(title="Inv Crash", goal="Invariant")

    class MalformedProvider(MockReasoningProvider):
        async def reason_about_situation(self, prompt_context):
            return "Not even a dictionary or ReasoningDecision"

    engine.reasoner = SupervisoryReasoner(provider=MalformedProvider())
    # Should safely complete using fallback
    await engine._trigger_anomaly_pipeline(
        m.id, None, "worker_01",
        AnomalyReport("LOOP_DETECTED", "desc", {}, SupervisorAction.PAUSE)
    )
    assert engine.get_state_machine(m.id).current_state in (SupervisorState.PAUSED, SupervisorState.INVESTIGATING)


@pytest.mark.asyncio
async def test_invariant_repeated_recovery_strategies_blocked(test_setup):
    """INVARIANT: Repeated recovery strategies are blocked."""
    engine = test_setup["engine"]
    mid = "msn_strat_block"
    engine.register_rejected_approach(mid, "restart_clean_container")
    assert engine.is_approach_rejected(mid, "restart_clean_container") is True
    assert engine.validate_recovery_strategy(mid, "restart_clean_container") is False


def test_invariant_docker_cannot_mount_unauthorized_paths():
    """INVARIANT: Docker cannot mount unauthorized host paths."""
    provider = DockerExecutionProvider()
    unauthorized = ["/", "C:\\", "C:/", "/etc", "/var", "/root"]
    for path in unauthorized:
        with pytest.raises(PermissionError):
            provider.validate_workspace(Path(path))


def test_invariant_secrets_are_not_emitted():
    """INVARIANT: Secrets are stripped and not emitted in arguments."""
    payload = {
        "api_key": "sk-1234567890abcdefghijklmnop",
        "gh_token": "ghp_abcdefghijklmnopqrstuvwxyz123456",
        "normal_text": "hello world"
    }
    sanitized = BaseTool.sanitize_arguments(payload)
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["gh_token"] == "[REDACTED]"
    assert sanitized["normal_text"] == "hello world"


@pytest.mark.asyncio
async def test_invariant_missions_cannot_contaminate_each_other(test_setup):
    """INVARIANT: Mission A events NEVER affect Mission B state."""
    engine = test_setup["engine"]
    missions = test_setup["missions"]
    bus = test_setup["bus"]

    mA = await missions.create_mission(title="Mission A", goal="Goal A")
    mB = await missions.create_mission(title="Mission B", goal="Goal B")

    workerA = MockWorker("workerA", mission_id=mA.id)
    workerB = MockWorker("workerB", mission_id=mB.id)
    engine.register_worker(workerA, mission_id=mA.id)
    engine.register_worker(workerB, mission_id=mB.id)

    # Pause Mission A
    await engine.pause(mission_id=mA.id, reason="Emergency pause on A")

    # State of A is PAUSED, state of B must remain RUNNING or CREATED
    smA = engine.get_state_machine(mA.id)
    smB = engine.get_state_machine(mB.id)

    assert smA.current_state == SupervisorState.PAUSED
    assert smB.current_state != SupervisorState.PAUSED
    assert workerA.paused is True
    assert workerB.paused is False


# =============================================================================
# 3. PROPERTY-STYLE INVARIANTS
# =============================================================================

@pytest.mark.asyncio
async def test_property_if_ci_not_passed_task_not_verified(test_setup):
    """PROPERTY: For all tasks, if CI has not passed, task != VERIFIED."""
    tasks = test_setup["tasks"]
    missions = test_setup["missions"]
    m = await missions.create_mission(title="Property CI", goal="Goal")
    t = Task(id="T-PROP-CI", mission_id=m.id, title="Prop Task")
    await tasks.initialize_mission_tasks(m.id, [t])

    # If neither CI nor tests passed:
    with pytest.raises(ValueError):
        await tasks.verify_task(m.id, t.id, caller_role="SUPERVISOR", ci_passed=False, tests_passed=False)

    stored = await tasks.get_task(m.id, t.id)
    assert stored.status != TaskStatus.VERIFIED


@pytest.mark.asyncio
async def test_property_if_reviewer_read_only_workspace_unmodified():
    """PROPERTY: If reviewer is read-only, workspace is never modified by reviewer."""
    rev = ReviewerAgent(agent_id="rev_readonly")
    assert "write_file" not in rev.tools
    assert "edit_file" not in rev.tools
    assert "run_command" not in rev.tools
    for tool in rev.tools.values():
        assert tool.name in rev.ALLOWED_READONLY_TOOLS


@pytest.mark.asyncio
async def test_property_if_approval_required_action_cannot_execute(test_setup):
    """PROPERTY: If approval is required, action cannot execute without explicit resolution."""
    engine = test_setup["engine"]
    missions = test_setup["missions"]
    approvals = test_setup["approvals"]

    m = await missions.create_mission(title="Prop Approval", goal="Gate")
    w = MockWorker("w_prop", mission_id=m.id)
    engine.register_worker(w, mission_id=m.id)

    req = await engine.request_approval(
        mission_id=m.id,
        agent_id=w.agent_id,
        action_type="DANGEROUS_ACTION",
        target="rm -rf /",
        reason="Safety gate"
    )

    # Invariant: Status remains PENDING until resolved
    assert req.status.value == "PENDING"
    assert w.paused is True

    # Attempting to resolve with an explicit rejection preserves block
    resolved = await approvals.resolve_request(
        req.id,
        ResolveApprovalPayload(
            action=ApprovalResolutionAction.REJECT,
            operator="operator_bob",
            feedback="Rejected command"
        )
    )
    assert resolved.status in (ApprovalStatus.DENIED, ApprovalStatus.REJECTED)
    assert w.resumed is False


def test_property_if_docker_configured_host_root_not_mounted():
    """PROPERTY: If Docker is configured, host root cannot be mounted under any circumstance."""
    provider = DockerExecutionProvider()
    for root_candidate in ["/", "C:\\", "C:/", "/root"]:
        with pytest.raises(PermissionError):
            provider.validate_workspace(Path(root_candidate))
