import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from core.events.bus import EventBus
from core.events.store import InMemoryEventStore
from core.events.schema import Event, EventType, EventSeverity
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus
from core.tasks.manager import TaskManager
from core.tasks.models import Task, TaskStatus
from core.policies.models import PolicyConfig
from supervisor.engine import SupervisorEngine
from supervisor.state_machine import SupervisorState
from supervisor.decisions import SupervisorAction
from integrations.nebius.provider import MockReasoningProvider
from memory.store import MemoryStore
from memory.provenance import FactStatus
from agents.worker.agent import WorkerAgent
from agents.verifier.agent import VerifierAgent
from agents.reviewer.agent import ReviewerAgent
from core.state.models import AgentContextPackage

from integrations.jenkins.models import (
    JenkinsBuildStatus,
    JenkinsBuildOutcome,
    JenkinsBuildResult,
    JenkinsConnectionError,
    JenkinsAuthError,
    JenkinsJobNotFoundError,
    JenkinsTimeoutError
)
from integrations.jenkins.client import JenkinsHttpClient
from integrations.jenkins.mock import MockJenkinsProvider
from integrations.jenkins.adapter import JenkinsVerificationAdapter


@pytest.fixture
def clean_ci_env(tmp_path):
    bus = EventBus()
    store = InMemoryEventStore()
    bus._global_subscribers.append(store.append)
    mission_mgr = MissionManager(event_bus=bus)
    task_mgr = TaskManager(event_bus=bus)
    memory_store = MemoryStore(event_bus=bus)
    policy = PolicyConfig(pause_after_repeated_failures=3)
    supervisor = SupervisorEngine(
        event_bus=bus,
        mission_manager=mission_mgr,
        task_manager=task_mgr,
        policy=policy,
        reasoner=MockReasoningProvider()
    )
    mock_provider = MockJenkinsProvider(workspace_path=str(tmp_path))
    adapter = JenkinsVerificationAdapter(provider=mock_provider, event_bus=bus)

    return {
        "bus": bus,
        "store": store,
        "mission_mgr": mission_mgr,
        "task_mgr": task_mgr,
        "memory_store": memory_store,
        "supervisor": supervisor,
        "mock_provider": mock_provider,
        "adapter": adapter,
        "workspace": tmp_path
    }


# =========================================================================
# 1. PROVIDER TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_mock_jenkins_success():
    provider = MockJenkinsProvider(default_mode="SUCCESS")
    trig = await provider.trigger_build(job_name="test-job")
    assert trig.queued
    assert trig.build_id is not None

    status = await provider.get_build_status(trig.build_id)
    assert status == JenkinsBuildStatus.COMPLETED

    res = await provider.get_build_result(trig.build_id)
    assert res.is_success
    assert res.tests_passed == 47
    assert res.tests_failed == 0
    assert res.status == JenkinsBuildStatus.COMPLETED
    assert res.result == JenkinsBuildOutcome.SUCCESS


@pytest.mark.asyncio
async def test_mock_jenkins_failure():
    provider = MockJenkinsProvider(default_mode="FAILURE")
    trig = await provider.trigger_build(job_name="test-job")
    res = await provider.get_build_result(trig.build_id)

    assert res.is_failure
    assert res.tests_passed == 45
    assert res.tests_failed == 2
    assert res.error_signature == "CSV_HEADER_MISMATCH_BOM"
    assert len(res.test_cases) == 2


@pytest.mark.asyncio
async def test_mock_jenkins_unavailable():
    provider = MockJenkinsProvider(default_mode="UNAVAILABLE")
    with pytest.raises(JenkinsConnectionError):
        await provider.trigger_build(job_name="test-job")

    with pytest.raises(JenkinsConnectionError):
        await provider.get_build_status("481")

    with pytest.raises(JenkinsConnectionError):
        await provider.get_build_result("481")


@pytest.mark.asyncio
async def test_mock_jenkins_timeout():
    provider = MockJenkinsProvider(default_mode="TIMEOUT")
    status = await provider.get_build_status("481")
    assert status == JenkinsBuildStatus.RUNNING

    with pytest.raises(JenkinsTimeoutError):
        await provider.poll_build_completion("481", timeout_seconds=0.1)


@pytest.mark.asyncio
async def test_mock_jenkins_build_polling():
    provider = MockJenkinsProvider()
    provider.set_sequence(["SUCCESS"])
    trig = await provider.trigger_build()
    res = await provider.poll_build_completion(trig.build_id, poll_interval=0.01)
    assert res.is_success
    assert res.tests_passed == 47


@pytest.mark.asyncio
async def test_jenkins_http_client_connection_error():
    # Attempting to talk to non-existent port raises JenkinsConnectionError
    client = JenkinsHttpClient(url="http://127.0.0.1:59999", timeout_seconds=1.0)
    with pytest.raises(JenkinsConnectionError):
        await client.trigger_build()


@pytest.mark.asyncio
async def test_jenkins_http_client_auth_error():
    client = JenkinsHttpClient(url="http://localhost:8080")
    mock_resp = MagicMock()
    mock_resp.status_code = 401

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        with patch.object(client, "_get_crumb", new_callable=AsyncMock) as mock_crumb:
            mock_crumb.return_value = {}
            mock_post.return_value = mock_resp
            with pytest.raises(JenkinsAuthError):
                await client.trigger_build()


@pytest.mark.asyncio
async def test_jenkins_http_client_job_not_found():
    client = JenkinsHttpClient(url="http://localhost:8080")
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        with patch.object(client, "_get_crumb", new_callable=AsyncMock) as mock_crumb:
            mock_crumb.return_value = {}
            mock_post.return_value = mock_resp
            with pytest.raises(JenkinsJobNotFoundError):
                await client.trigger_build()


@pytest.mark.asyncio
async def test_jenkins_http_client_crumb_and_queue_resolution():
    client = JenkinsHttpClient(url="http://localhost:8080", username="user", api_token="secret_token")
    mock_crumb_resp = MagicMock()
    mock_crumb_resp.status_code = 200
    mock_crumb_resp.json.return_value = {"crumbRequestField": "Jenkins-Crumb", "crumb": "test_crumb_val"}

    mock_build_resp = MagicMock()
    mock_build_resp.status_code = 201
    mock_build_resp.headers = {"Location": "http://localhost:8080/queue/item/101/"}

    mock_queue_resp = MagicMock()
    mock_queue_resp.status_code = 200
    mock_queue_resp.json.return_value = {"executable": {"number": 481, "url": "http://localhost:8080/job/test/481/"}}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [mock_crumb_resp, mock_queue_resp]
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_build_resp

            trig = await client.trigger_build()
            assert trig.queued
            assert "101" in trig.queue_item_url

            build_id = await client.resolve_queue_item(trig.queue_item_url, timeout=2.0)
            assert build_id == "481"


# =========================================================================
# 2. EVENT TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_ci_events_on_success(clean_ci_env):
    adapter = clean_ci_env["adapter"]
    mock_provider = clean_ci_env["mock_provider"]
    store = clean_ci_env["store"]
    mock_provider.set_mode("SUCCESS")

    res = await adapter.trigger_and_verify(mission_id="MSN-TEST-1", task_id="TASK-1", agent_id="worker_01")
    assert res.is_success

    types = [e.type for e in store._events]
    assert EventType.CI_BUILD_TRIGGERED in types
    assert EventType.CI_BUILD_STARTED in types
    assert EventType.CI_BUILD_COMPLETED in types
    assert EventType.CI_TEST_RESULTS_AVAILABLE in types

    completed_evt = next(e for e in store._events if e.type == EventType.CI_BUILD_COMPLETED)
    assert completed_evt.payload["tests_passed"] == 47
    assert completed_evt.payload["tests_failed"] == 0
    assert completed_evt.payload["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_ci_events_on_failure(clean_ci_env):
    adapter = clean_ci_env["adapter"]
    mock_provider = clean_ci_env["mock_provider"]
    store = clean_ci_env["store"]
    mock_provider.set_mode("FAILURE")

    res = await adapter.trigger_and_verify(mission_id="MSN-TEST-2", task_id="TASK-2", agent_id="worker_01")
    assert res.is_failure

    types = [e.type for e in store._events]
    assert EventType.CI_BUILD_TRIGGERED in types
    assert EventType.CI_BUILD_FAILED in types
    assert EventType.CI_TEST_RESULTS_AVAILABLE in types

    failed_evt = next(e for e in store._events if e.type == EventType.CI_BUILD_FAILED)
    assert failed_evt.payload["tests_failed"] == 2
    assert failed_evt.payload["error_signature"] == "CSV_HEADER_MISMATCH_BOM"


@pytest.mark.asyncio
async def test_ci_events_on_unavailable(clean_ci_env):
    adapter = clean_ci_env["adapter"]
    mock_provider = clean_ci_env["mock_provider"]
    store = clean_ci_env["store"]
    mock_provider.set_mode("UNAVAILABLE")

    res = await adapter.trigger_and_verify(mission_id="MSN-TEST-3", task_id="TASK-3", agent_id="worker_01")
    assert res.status == JenkinsBuildStatus.UNAVAILABLE

    types = [e.type for e in store._events]
    assert EventType.CI_UNAVAILABLE in types


@pytest.mark.asyncio
async def test_ci_events_on_timeout(clean_ci_env):
    adapter = clean_ci_env["adapter"]
    mock_provider = clean_ci_env["mock_provider"]
    store = clean_ci_env["store"]
    mock_provider.set_mode("TIMEOUT")

    res = await adapter.trigger_and_verify(mission_id="MSN-TEST-4", task_id="TASK-4", agent_id="worker_01")
    assert res.status == JenkinsBuildStatus.TIMEOUT

    types = [e.type for e in store._events]
    assert EventType.CI_TIMEOUT in types


# =========================================================================
# 3. SUPERVISOR INTEGRATION TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_worker_completion_plus_ci_failure_prevents_verified(clean_ci_env):
    """Core rule: Worker completion != verified result."""
    bus = clean_ci_env["bus"]
    mission_mgr = clean_ci_env["mission_mgr"]
    task_mgr = clean_ci_env["task_mgr"]
    supervisor = clean_ci_env["supervisor"]
    adapter = clean_ci_env["adapter"]
    mock_provider = clean_ci_env["mock_provider"]
    mock_provider.set_mode("FAILURE")

    mission = await mission_mgr.create_mission(title="CI Verification Gate", goal="Validate CSV import")
    task = Task(id="TASK-CI-GATE", mission_id=mission.id, title="Implement Parser")
    await task_mgr.initialize_mission_tasks(mission.id, [task])

    worker = WorkerAgent(agent_id="worker_01", event_bus=bus, tools={})
    supervisor.register_worker(worker)

    # 1. Worker claims task finished
    await bus.publish(
        Event(
            mission_id=mission.id,
            task_id=task.id,
            agent_id="worker_01",
            type=EventType.TASK_PROGRESS,
            payload={"status": "execution_finished", "summary": "Worker claims task is done."}
        )
    )

    # 2. Independent Jenkins CI runs and finds 2 test failures
    ci_res = await adapter.trigger_and_verify(
        mission_id=mission.id,
        task_id=task.id,
        agent_id="worker_01"
    )
    assert ci_res.is_failure

    # 3. Assertions: Task was NOT marked verified; was reopened; worker paused
    updated_task = await task_mgr.get_task(mission.id, task.id)
    assert updated_task.status == TaskStatus.IN_PROGRESS
    assert updated_task.metadata.get("reopened") is True
    assert worker.state.value == "PAUSED"
    assert supervisor.state_machine.current_state == SupervisorState.INVESTIGATING


@pytest.mark.asyncio
async def test_ci_failure_triggers_nemotron_reasoning(clean_ci_env):
    bus = clean_ci_env["bus"]
    mission_mgr = clean_ci_env["mission_mgr"]
    task_mgr = clean_ci_env["task_mgr"]
    supervisor = clean_ci_env["supervisor"]
    adapter = clean_ci_env["adapter"]
    store = clean_ci_env["store"]
    clean_ci_env["mock_provider"].set_mode("FAILURE")

    mission = await mission_mgr.create_mission(title="Reasoning Test", goal="Inspect CI error")
    task = Task(id="TASK-REASON", mission_id=mission.id, title="Buggy Task")
    await task_mgr.initialize_mission_tasks(mission.id, [task])

    worker = WorkerAgent(agent_id="worker_01", event_bus=bus, tools={})
    supervisor.register_worker(worker)

    await adapter.trigger_and_verify(mission_id=mission.id, task_id=task.id, agent_id="worker_01")

    decisions = [e for e in store._events if e.type == EventType.SUPERVISOR_DECISION]
    assert len(decisions) >= 1
    assert decisions[0].payload["decision"] == "DELEGATE"
    assert "reviewer" in decisions[0].payload["target_agent"]


@pytest.mark.asyncio
async def test_ci_success_triggers_verifier_handoff(clean_ci_env):
    bus = clean_ci_env["bus"]
    mission_mgr = clean_ci_env["mission_mgr"]
    task_mgr = clean_ci_env["task_mgr"]
    supervisor = clean_ci_env["supervisor"]
    adapter = clean_ci_env["adapter"]
    clean_ci_env["mock_provider"].set_mode("SUCCESS")

    mission = await mission_mgr.create_mission(title="Pass Test", goal="Pass verification")
    task = Task(id="TASK-PASS", mission_id=mission.id, title="Passing Task")
    await task_mgr.initialize_mission_tasks(mission.id, [task])

    worker = WorkerAgent(agent_id="worker_01", event_bus=bus, tools={})
    supervisor.register_worker(worker)

    ci_res = await adapter.trigger_and_verify(mission_id=mission.id, task_id=task.id, agent_id="worker_01")
    assert ci_res.is_success

    # CI pass does not automatically mark mission complete without Verifier
    current_mission = await mission_mgr.get_mission(mission.id)
    assert current_mission.status != MissionStatus.COMPLETED

    # When Verifier confirms, task and mission can complete
    verifier = VerifierAgent(agent_id="verifier_01", event_bus=bus, tools={})
    ver_res = await verifier.run(AgentContextPackage(mission_id=mission.id, objective="Verify", task=task.model_dump()))
    await mission_mgr.complete_mission(mission.id, summary="Verified")
    final_mission = await mission_mgr.get_mission(mission.id)
    assert final_mission.status == MissionStatus.COMPLETED


@pytest.mark.asyncio
async def test_jenkins_unavailable_safe_state(clean_ci_env):
    bus = clean_ci_env["bus"]
    mission_mgr = clean_ci_env["mission_mgr"]
    task_mgr = clean_ci_env["task_mgr"]
    supervisor = clean_ci_env["supervisor"]
    adapter = clean_ci_env["adapter"]
    clean_ci_env["mock_provider"].set_mode("UNAVAILABLE")

    mission = await mission_mgr.create_mission(title="Offline CI Test", goal="Handle offline CI")
    task = Task(id="TASK-OFFLINE", mission_id=mission.id, title="Offline Task")
    await task_mgr.initialize_mission_tasks(mission.id, [task])

    worker = WorkerAgent(agent_id="worker_01", event_bus=bus, tools={})
    supervisor.register_worker(worker)

    res = await adapter.trigger_and_verify(mission_id=mission.id, task_id=task.id, agent_id="worker_01")
    assert res.status == JenkinsBuildStatus.UNAVAILABLE

    # Safe state: Worker paused, task NOT verified
    assert worker.state.value == "PAUSED"
    updated_task = await task_mgr.get_task(mission.id, task.id)
    assert updated_task.status != TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_jenkins_memory_provenance_integration(clean_ci_env):
    memory_store = clean_ci_env["memory_store"]

    # Store verified finding from Jenkins evidence into project memory
    record = await memory_store.add_record(
        mission_id="MSN-MEM",
        fact="CSV parser tests require BOM normalization",
        source="jenkins_build_482",
        created_by="verifier",
        status=FactStatus.VERIFIED,
        confidence=0.99
    )
    assert record.source == "jenkins_build_482"
    assert record.status == FactStatus.VERIFIED
    assert record.confidence == 0.99

    stored = await memory_store.get_by_mission("MSN-MEM")
    assert len(stored) == 1
    assert "BOM" in stored[0].fact


@pytest.mark.asyncio
async def test_real_jenkins_integration_or_skip():
    """Integration test against live Jenkins server if configured; skips cleanly otherwise."""
    enabled = os.getenv("JENKINS_ENABLED", "false").lower() in ("true", "1", "yes")
    url = os.getenv("JENKINS_URL", "http://localhost:8080")

    if not enabled:
        pytest.skip("Live Jenkins testing disabled (JENKINS_ENABLED is not set to true).")

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{url.rstrip('/')}/api/json")
            if res.status_code not in (200, 401, 403):
                pytest.skip(f"Live Jenkins server at {url} returned status {res.status_code}")
    except Exception as e:
        pytest.skip(f"Live Jenkins server at {url} is offline ({e}).")

    # If reachable, trigger and query
    http_client = JenkinsHttpClient(url=url)
    trig = await http_client.trigger_build()
    assert trig.queued
