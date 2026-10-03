import asyncio
import os
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.state import app_state
from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus
from core.tasks.manager import TaskManager
from core.tasks.models import Task, TaskStatus
from agents.registry import AgentRegistry
from execution.manager import ExecutionManager
from execution.models import ExecutionRequest, ExecutionStatus
from integrations.nebius.provider import NebiusNemotronProvider, MockReasoningProvider
from integrations.jenkins.client import JenkinsHttpClient
from integrations.jenkins.mock import MockJenkinsProvider
from supervisor.engine import SupervisorEngine
from supervisor.reasoning import SupervisoryReasoner


@pytest.fixture
def client():
    return TestClient(app)


# --- 1. Health and Readiness Probes ---
def test_phase10_health_endpoint(client):
    """Test that /health returns service health and active subsystem overview."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "AI Work Supervisor"
    assert "version" in data
    assert "subsystems" in data
    assert data["subsystems"]["supervisor_engine"] == "watching"


def test_phase10_readiness_probe(client):
    """Test that /ready returns combined readiness across model, execution, CI, and supervisor."""
    res = client.get("/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert "model_provider" in data
    assert "execution_backend" in data
    assert "jenkins_ci" in data
    assert "supervisor" in data
    assert data["model_provider"]["safe_fallback_active"] is True


def test_phase10_model_health_endpoint(client):
    """Test /health/model returns provider diagnostics without exposing secrets."""
    res = client.get("/health/model")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "model" in data
    assert "provider" in data
    # Ensure no API keys or secrets are exposed in payload
    serialized = str(data).lower()
    assert "api_key" not in data
    assert "bearer" not in serialized


def test_phase10_jenkins_health_endpoint(client):
    """Test /health/jenkins returns CI diagnostics without exposing tokens."""
    res = client.get("/health/jenkins")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "url" in data
    assert "api_token" not in data
    assert "password" not in data


def test_phase10_execution_health_endpoint(client):
    """Test /health/execution returns status of both local and Docker sandboxes."""
    res = client.get("/health/execution")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "local_backend" in data
    assert "docker_backend" in data
    assert data["local_backend"]["available"] is True


# --- 2. Nemotron Environment Configuration & Safe Fallback ---
@pytest.mark.asyncio
async def test_nemotron_provider_fallback_without_key():
    """Ensure NebiusNemotronProvider falls back to local deterministic mock when no key is set."""
    provider = NebiusNemotronProvider(api_key="", base_url="https://api.studio.nebius.ai/v1")
    health = await provider.check_health()
    assert health["status"] == "healthy"
    assert health["mode"] == "fallback_local"
    assert health["safe_fallback_active"] is True

    # Test reasoning fallback works deterministically
    decision = await provider.reason_about_situation({
        "anomaly_type": "LOOP_DETECTED",
        "error_signature": "TEST_FAIL_SIGNATURE"
    })
    assert decision.decision == "DELEGATE"
    assert decision.target_agent == "reviewer_01"


@pytest.mark.asyncio
async def test_nemotron_provider_cloud_error_safe_fallback():
    """Ensure NebiusNemotronProvider catches network/endpoint errors and falls back safely."""
    provider = NebiusNemotronProvider(
        api_key="fake-key-for-test",
        base_url="http://127.0.0.1:9999/v1",  # Non-existent endpoint
        timeout_seconds=0.5
    )
    health = await provider.check_health()
    assert health["status"] == "degraded"
    assert health["mode"] == "fallback_local"

    # Must NOT raise exception; must return valid deterministic fallback decision
    decision = await provider.reason_about_situation({
        "anomaly_type": "NO_PROGRESS"
    })
    assert decision.decision == "CHANGE_STRATEGY"
    assert decision.confidence > 0.8


# --- 3. Jenkins Client Health Check ---
@pytest.mark.asyncio
async def test_jenkins_mock_provider_health():
    """Test mock Jenkins provider reports healthy status in local test mode."""
    mock_jenkins = MockJenkinsProvider(default_mode="SUCCESS")
    health = await mock_jenkins.check_health()
    assert health["status"] == "healthy"
    assert "mock" in health["mode"]


@pytest.mark.asyncio
async def test_jenkins_http_client_offline_handling():
    """Test production Jenkins HTTP client handles unreachable server safely without crashing."""
    http_jenkins = JenkinsHttpClient(url="http://127.0.0.1:9999", timeout_seconds=0.5)
    health = await http_jenkins.check_health()
    assert health["status"] == "offline"
    assert "Cannot reach Jenkins" in health["reason"]


# --- 4. End-to-End Mission Deployment Lifecycle Test ---
@pytest.mark.asyncio
async def test_phase10_end_to_end_mission_lifecycle():
    """
    Test the full end-to-end supervisory pipeline:
    Mission -> Worker -> Supervisor -> Nemotron -> Execution (Docker/Local) -> Jenkins -> Verifier -> Completed Mission.
    Explicitly tags: [LOCAL TEST / DETERMINISTIC RUNTIME].
    """
    bus = EventBus()
    mission_mgr = MissionManager(event_bus=bus)
    task_mgr = TaskManager(event_bus=bus)
    registry = AgentRegistry(event_bus=bus)
    exec_mgr = ExecutionManager(event_bus=bus, default_backend="local")
    reasoning_provider = MockReasoningProvider()
    reasoner = SupervisoryReasoner(provider=reasoning_provider)
    jenkins = MockJenkinsProvider(default_mode="DYNAMIC_WORKSPACE")

    supervisor = SupervisorEngine(
        event_bus=bus,
        mission_manager=mission_mgr,
        task_manager=task_mgr,
        reasoner=reasoner,
        registry=registry
    )

    # 1. Create Mission
    mission = await mission_mgr.create_mission(
        title="Deployable CSV Import",
        goal="Add CSV parser and verify via Jenkins CI and isolated execution"
    )
    await mission_mgr.start_mission(mission.id)
    assert (await mission_mgr.get_mission(mission.id)).status == MissionStatus.RUNNING

    # 2. Initialize Tasks
    task_1 = Task(id="T-IMPL", mission_id=mission.id, title="Implement parser", expected_files=["src/parser.py"])
    task_2 = Task(id="T-VERIF", mission_id=mission.id, title="Verify with CI", dependencies=["T-IMPL"], expected_files=["tests/test_parser.py"])
    await task_mgr.initialize_mission_tasks(mission.id, [task_1, task_2])

    # 3. Register Worker & Execute Sandbox Request
    await registry.register_agent("worker_01", "WORKER", mission_id=mission.id, task_id="T-IMPL")
    exec_req = ExecutionRequest(
        command="python -c \"print('Sandbox execution successful')\"",
        workspace_root="./demo/sample-project",
        mission_id=mission.id,
        task_id="T-IMPL",
        agent_id="worker_01"
    )
    exec_result = await exec_mgr.execute(exec_req)
    assert exec_result.status == ExecutionStatus.SUCCESS
    assert "Sandbox execution successful" in exec_result.stdout

    # 4. Trigger Jenkins CI Verification
    trigger_res = await jenkins.trigger_build(job_name="csv-import-job")
    assert trigger_res.queued is True
    build_result = await jenkins.get_build_result(trigger_res.build_id, "csv-import-job")
    assert build_result.build_id == trigger_res.build_id

    # 5. Complete Tasks and Verify Mission Completion
    await task_mgr.complete_task(mission.id, "T-IMPL", summary="Implemented parser")
    await task_mgr.complete_task(mission.id, "T-VERIF", summary="Tests passing")

    completed_mission = await mission_mgr.complete_mission(mission.id)
    assert completed_mission.status == MissionStatus.COMPLETED
