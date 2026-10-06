import pytest
from fastapi.testclient import TestClient
from apps.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "event_bus" in data["subsystems"]


def test_seed_demo_and_query_endpoints(client):
    # Seed demo mission
    seed_res = client.post("/api/missions/seed-demo")
    assert seed_res.status_code == 200
    seeded = seed_res.json()
    mission_id = seeded["mission_id"]
    assert seeded["tasks_count"] == 6

    # Fetch mission details
    get_res = client.get(f"/api/missions/{mission_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Add CSV Import Validation"

    # Fetch task graph
    tasks_res = client.get(f"/api/missions/{mission_id}/tasks")
    assert tasks_res.status_code == 200
    task_data = tasks_res.json()
    assert len(task_data["tasks"]) == 6
    assert len(task_data["graph"]["nodes"]) == 6

    # Fetch timeline
    timeline_res = client.get(f"/api/missions/{mission_id}/timeline")
    assert timeline_res.status_code == 200
    assert "timeline" in timeline_res.json()
    assert len(timeline_res.json()["timeline"]) >= 1

    # Pause mission
    pause_res = client.post(f"/api/missions/{mission_id}/pause", json={"reason": "Operator test pause"})
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "paused"


def test_natural_language_draft_mission(client):
    # Test drafting with natural language goal
    goal = "Fix the authentication failures and handle expired session tokens properly"
    draft_res = client.post("/api/missions/draft", json={"goal": goal})
    assert draft_res.status_code == 200
    draft = draft_res.json()

    assert draft["goal"] == goal
    assert "Authentication" in draft["title"] or "Fix" in draft["title"]
    assert len(draft["proposed_tasks"]) >= 3
    assert len(draft["suggested_agents"]) >= 1
    assert "Claude Code" in draft["suggested_agents"][0] or "claude" in draft["suggested_agents"][0].lower()
    assert draft["verification_plan"]["isolated_sandbox"] is True
    assert draft["verification_plan"]["automated_tests"] is True

    # Test creating mission directly with the draft's decomposed tasks
    create_res = client.post("/api/missions", json={
        "title": draft["title"],
        "goal": draft["goal"],
        "repository_path": draft["repository_path"],
        "tasks": draft["proposed_tasks"]
    })
    assert create_res.status_code == 200
    created = create_res.json()
    assert created["title"] == draft["title"]
    assert created["status"] in ["CREATED", "PLANNING", "RUNNING"]

    # Verify initialized tasks exist on the mission
    tasks_res = client.get(f"/api/missions/{created['id']}/tasks")
    assert tasks_res.status_code == 200
    tasks_data = tasks_res.json()
    assert len(tasks_data["tasks"]) == len(draft["proposed_tasks"])

