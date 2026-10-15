import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from core.missions.models import MissionStatus


@pytest.fixture
def client():
    return TestClient(app)


def test_request_creates_persistent_mission_and_preserves_request(client):
    # 1. A new request creates a persistent mission & preserves original request verbatim
    raw_request = "Implement user authentication with JWT session cookies and regression tests"
    res = client.post("/api/missions", json={"title": "Auth Mission", "goal": raw_request})
    assert res.status_code == 200
    mission = res.json()
    mission_id = mission["id"]

    assert mission["original_request"] == raw_request
    assert mission["goal"] == raw_request
    # 2. Planning does not dispatch an agent - mission is awaiting approval, not running
    assert mission["status"] == "AWAITING_APPROVAL"
    assert mission["current_plan_version"] == 1
    assert mission["approved_plan_version"] is None


def test_generated_plan_contains_structured_interpretation_and_acceptance_criteria(client):
    # 4. The generated plan includes structured interpretation & acceptance criteria
    goal = "Implement dark theme palette and local storage preference switcher"
    res = client.post("/api/missions", json={"title": "Dark Mode", "goal": goal})
    assert res.status_code == 200
    mission_id = res.json()["id"]

    plan_res = client.get(f"/api/missions/{mission_id}/plan")
    assert plan_res.status_code == 200
    plan = plan_res.json()

    assert plan["version"] == 1
    assert plan["approval_status"] == "PENDING"
    interp = plan["interpretation"]
    assert interp["original_request"] == goal
    assert len(interp["in_scope"]) > 0
    assert len(interp["explicit_exclusions"]) > 0
    assert len(interp["constraints"]) > 0
    assert "definition_of_success" in interp

    # Each task must have acceptance criteria
    tasks = plan["tasks"]
    assert len(tasks) > 0
    for t in tasks:
        assert "acceptance_criteria" in t
        assert len(t["acceptance_criteria"]) > 0


def test_blocking_questions_prevent_approval_and_can_be_clarified(client):
    # 5. Blocking questions prevent approval
    # Very short or ambiguous goal triggers blocking questions
    vague_goal = "fix it"
    res = client.post("/api/missions", json={"title": "Vague Goal", "goal": vague_goal})
    assert res.status_code == 200
    mission_id = res.json()["id"]

    # Mission status should be NEEDS_CLARIFICATION
    assert res.json()["status"] == "NEEDS_CLARIFICATION"

    plan_res = client.get(f"/api/missions/{mission_id}/plan")
    assert plan_res.status_code == 200
    plan = plan_res.json()
    assert len(plan["interpretation"]["blocking_questions"]) > 0

    # Attempting to approve while blocking questions exist MUST fail with 400
    approve_res = client.post(f"/api/missions/{mission_id}/plan/approve", json={"version": 1})
    assert approve_res.status_code == 400
    assert "BLOCKING_QUESTIONS_UNRESOLVED" in approve_res.json()["detail"]["error"]

    # Clarifying the blocking question resolves it
    blocking_q = plan["interpretation"]["blocking_questions"][0]
    clarify_res = client.post(f"/api/missions/{mission_id}/plan/clarify", json={
        "answers": {blocking_q: "Target the broken auth token expiration handler in src/auth.py"}
    })
    assert clarify_res.status_code == 200
    clarified_plan = clarify_res.json()
    assert len(clarified_plan["interpretation"]["blocking_questions"]) == 0
    assert clarified_plan["version"] == 2

    # Now it can be approved
    approve_res2 = client.post(f"/api/missions/{mission_id}/plan/approve", json={"version": 2})
    assert approve_res2.status_code == 200
    assert approve_res2.json()["status"] == "approved"
    assert approve_res2.json()["plan_version"] == 2


def test_unapproved_plan_cannot_be_dispatched(client):
    # 10. An unapproved plan cannot be dispatched
    goal = "Implement CSV import parsing and validation logic"
    res = client.post("/api/missions", json={"title": "CSV Task", "goal": goal})
    assert res.status_code == 200
    mission_id = res.json()["id"]

    # Mission is AWAITING_APPROVAL; calling /start or /execute without approval MUST reject
    start_res = client.post(f"/api/missions/{mission_id}/start")
    assert start_res.status_code == 400
    assert start_res.json()["detail"]["error"] == "PLAN_NOT_APPROVED"

    exec_res = client.post(f"/api/missions/{mission_id}/execute")
    assert exec_res.status_code == 400
    assert exec_res.json()["detail"]["error"] == "PLAN_NOT_APPROVED"


def test_approval_is_version_specific_and_invalidated_by_edits(client):
    # 7. Valid plan can be approved
    # 8. Approval is tied to specific version
    # 9. Editing the approved plan invalidates approval
    # 11. An outdated plan version cannot be dispatched
    goal = "Add Prometheus metrics endpoint with request latency histogram"
    res = client.post("/api/missions", json={"title": "Metrics", "goal": goal})
    assert res.status_code == 200
    mission_id = res.json()["id"]

    # Approve v1
    approve_v1 = client.post(f"/api/missions/{mission_id}/plan/approve", json={"version": 1, "approved_by": "lead_eng"})
    assert approve_v1.status_code == 200
    assert approve_v1.json()["plan_version"] == 1

    # Check mission state
    m_state = client.get(f"/api/missions/{mission_id}").json()
    assert m_state["status"] == "APPROVED"
    assert m_state["approved_plan_version"] == 1

    # User makes material edit to plan
    edit_res = client.post(f"/api/missions/{mission_id}/plan/edit", json={
        "interpretation": {
            "constraints": ["Include latency percentiles p90, p95, and p99", "Preserve existing /health endpoint"]
        }
    })
    assert edit_res.status_code == 200
    edited_plan = edit_res.json()
    assert edited_plan["version"] == 2
    assert edited_plan["approval_status"] == "PENDING"

    # Mission state must be invalidated back to AWAITING_APPROVAL and approved_plan_version cleared
    m_state2 = client.get(f"/api/missions/{mission_id}").json()
    assert m_state2["status"] == "AWAITING_APPROVAL"
    assert m_state2["approved_plan_version"] is None

    # Stale approval: attempting to approve with old version 1 MUST fail
    stale_app = client.post(f"/api/missions/{mission_id}/plan/approve", json={"version": 1})
    assert stale_app.status_code == 400
    assert "Stale approval attempt" in stale_app.json()["detail"]

    # Attempting to start execution without re-approving v2 MUST fail
    start_fail = client.post(f"/api/missions/{mission_id}/start")
    assert start_fail.status_code == 400
    assert start_fail.json()["detail"]["error"] == "PLAN_NOT_APPROVED"

    # Re-approve v2
    approve_v2 = client.post(f"/api/missions/{mission_id}/plan/approve", json={"version": 2})
    assert approve_v2.status_code == 200
    assert approve_v2.json()["plan_version"] == 2

    m_state3 = client.get(f"/api/missions/{mission_id}").json()
    assert m_state3["status"] == "APPROVED"
    assert m_state3["approved_plan_version"] == 2


def test_plan_rejection(client):
    goal = "Refactor payment processor module"
    res = client.post("/api/missions", json={"title": "Payment Refactor", "goal": goal})
    mission_id = res.json()["id"]

    reject_res = client.post(f"/api/missions/{mission_id}/plan/reject", json={"reason": "Out of scope for this sprint"})
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"

    m_state = client.get(f"/api/missions/{mission_id}").json()
    assert m_state["status"] == "REJECTED"

    # Rejected mission cannot be dispatched
    start_fail = client.post(f"/api/missions/{mission_id}/start")
    assert start_fail.status_code == 400
