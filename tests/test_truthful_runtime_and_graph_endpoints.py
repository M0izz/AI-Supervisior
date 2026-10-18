import pytest
from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app)

def test_adapter_setup_guide_endpoint():
    """Verify setup guide returns safe, verified install information for known adapters."""
    # Test claude_code setup guide
    resp = client.get("/api/adapters/claude_code/setup-guide")
    assert resp.status_code == 200
    data = resp.json()
    assert data["adapter_id"] == "claude_code"
    assert "npm install -g @anthropic-ai/claude-code" in data["install_command"]
    assert "ANTHROPIC_API_KEY" in data["required_env_vars"]
    assert len(data["supported_os"]) > 0

    # Test unknown adapter returns 404
    resp_unknown = client.get("/api/adapters/nonexistent_runtime_xyz/setup-guide")
    assert resp_unknown.status_code == 404

def test_adapter_check_and_test_endpoints():
    """Verify live re-detection probe and non-destructive execution testing."""
    # Test check endpoint
    resp_check = client.post("/api/adapters/worker_01/check")
    assert resp_check.status_code == 200
    assert resp_check.json()["available"] is True

    # Test test execution endpoint on native worker
    resp_test = client.post("/api/adapters/worker_01/test")
    assert resp_test.status_code == 200
    test_data = resp_test.json()
    assert test_data["status"] == "SUCCESS"
    assert "Worker 01 runtime responded" in test_data["output"]

def test_graph_activity_endpoint():
    """Verify that graph activity endpoint returns real structured events."""
    resp = client.get("/api/graph/activity?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "count" in data
    assert isinstance(data["events"], list)
    if data["count"] > 0:
        event = data["events"][0]
        assert "operation_type" in event
        assert "timestamp" in event
        assert "direction" in event
        assert "description" in event

def test_task_agent_reassignment_preserves_approval_gate():
    """
    Verify that manually assigning an agent to a task:
    1. Updates the task's assigned agent.
    2. If the plan was approved, increments plan version and forces reapproval.
    """
    # 1. Create a test mission
    create_resp = client.post("/api/missions", json={
        "title": "Test Agent Assignment Invariant",
        "goal": "Verify agent assignment resets approval status when already approved",
        "repository_path": "./demo/sample-project"
    })
    assert create_resp.status_code == 200
    mission_id = create_resp.json()["id"]

    # 2. Get the mission tasks
    tasks_resp = client.get(f"/api/missions/{mission_id}/tasks")
    assert tasks_resp.status_code == 200
    tasks = tasks_resp.json()["tasks"]
    assert len(tasks) > 0
    target_task_id = tasks[0]["id"]

    # 3. Approve the plan first (version 1)
    approve_resp = client.post(f"/api/missions/{mission_id}/approve", json={
        "operator_id": "operator_test",
        "notes": "Initial plan approval"
    })
    assert approve_resp.status_code == 200
    assert approve_resp.json()["approved_plan_version"] == 1

    # 4. Now assign agent 'worker_01' to target task
    assign_resp = client.post(f"/api/missions/{mission_id}/tasks/{target_task_id}/assign-agent", json={
        "agent_id": "worker_01"
    })
    assert assign_resp.status_code == 200
    assign_data = assign_resp.json()
    assert assign_data["task_id"] == target_task_id
    assert assign_data["assigned_agent_id"] == "worker_01"
    assert assign_data["reapproval_required"] is True
    assert assign_data["plan_version"] == 2  # Invariant: incremented version
    assert assign_data["approval_status"] == "PENDING"  # Invariant: approval reset!

    # 5. Verify the mission record reflects the invalidated approval
    mission_resp = client.get(f"/api/missions/{mission_id}")
    assert mission_resp.status_code == 200
    mission = mission_resp.json()
    assert mission["approved_plan_version"] is None or mission["status"] == "WAITING_APPROVAL"
