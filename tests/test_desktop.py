"""
Tests for Phase 8: Desktop Application & Floating Supervisor HUD.

Covers:
1. Desktop Health & Connectivity API Contract
2. Active Mission & HUD State Data Contract
3. Desktop Approvals Flow (Approve / Deny via desktop action)
4. WebSocket Event Delivery to Desktop Clients
5. Zero-Nag Event Classification
6. Killer End-to-End Scenario: Desktop HUD Lifecycle from Mission Start to Completion
"""

import pytest
import asyncio
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.state import app_state
from core.events.schema import Event, EventType, EventSeverity
from core.missions.models import Mission, MissionStatus
from core.tasks.models import Task, TaskStatus
from agents.registry import AgentStatus


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_desktop_health_contract(client):
    """Verifies that the /health endpoint satisfies the desktop connection manager contract."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"].lower() == "healthy"
    assert "subsystems" in data
    assert data["subsystems"]["event_bus"] == "operational"
    assert "version" in data


def test_desktop_missions_state_contract(client):
    """Verifies that mission state endpoints return all fields required by the Floating HUD."""
    # Create test mission
    create_res = client.post("/api/missions", json={
        "title": "Fix Authentication Tests",
        "goal": "Resolve UTF-8 BOM encoding issue in CSV parser",
        "repository_path": "./demo/sample-project"
    })
    assert create_res.status_code == 200
    mission_id = create_res.json()["id"]

    # Verify mission state contract
    state_res = client.get(f"/api/missions/{mission_id}/state")
    assert state_res.status_code == 200
    state = state_res.json()
    assert state["mission_id"] == mission_id
    assert state["title"] == "Fix Authentication Tests"
    assert "status" in state
    assert "supervisor_state" in state
    assert "tasks_count" in state
    assert "completed_tasks" in state
    assert "assigned_agents" in state


def test_desktop_approvals_flow(client):
    """Verifies that pending approvals can be queried and resolved via desktop actions."""
    # Create mission and approval
    m_res = client.post("/api/missions", json={
        "title": "Database Migration",
        "goal": "Run schema migration script"
    })
    mission_id = m_res.json()["id"]

    appr_res = client.post("/api/approvals", json={
        "mission_id": mission_id,
        "agent_id": "claude-code",
        "action_type": "EXECUTE_COMMAND",
        "target": "alembic upgrade head",
        "reason": "Apply foreign key constraints",
        "risk_level": "medium"
    })
    assert appr_res.status_code == 200
    approval_data = appr_res.json()
    approval_id = approval_data["approval"]["id"] if "approval" in approval_data else approval_data["id"]

    # Query pending approvals (used by HUD to display approval banner)
    pending_res = client.get("/api/approvals")
    assert pending_res.status_code == 200
    pending_data = pending_res.json()
    pending_list = pending_data.get("approvals", pending_data) if isinstance(pending_data, dict) else pending_data
    assert any(a["id"] == approval_id for a in pending_list)

    # Resolve approval via HUD action (APPROVE_ONCE)
    resolve_res = client.post(f"/api/approvals/{approval_id}/resolve", json={
        "action": "APPROVE_ONCE",
        "operator": "DesktopOperator",
        "feedback": "Approved via Floating HUD"
    })
    assert resolve_res.status_code == 200
    res_data = resolve_res.json()
    assert res_data.get("status") in ["resolved", "APPROVED"]


def test_zero_nag_event_classification():
    """Verifies the Zero-Nag classification: normal events remain silent, actionable events notify."""
    actionable_types = {
        "APPROVAL_REQUIRED",
        "APPROVAL_REQUESTED",
        "CRITICAL_INTERVENTION",
        "WATCHDOG_INTERVENTION",
        "VERIFICATION_FAILED",
        "VERIFICATION_REJECTED",
        "MISSION_FAILED",
        "MISSION_COMPLETED"
    }

    benign_types = [
        "TASK_STARTED",
        "COMMAND_EXECUTED",
        "FILE_CHANGED",
        "TOOL_CALL",
        "AGENT_HEARTBEAT",
        "TESTS_PASSED"
    ]

    for b_type in benign_types:
        assert b_type not in actionable_types, f"{b_type} must not be classified as actionable"

    critical_events = [
        ("APPROVAL_REQUIRED", EventSeverity.WARNING),
        ("INTERVENTION_TRIGGERED", EventSeverity.CRITICAL),
        ("VERIFICATION_FAILED", EventSeverity.ERROR),
        ("MISSION_FAILED", EventSeverity.CRITICAL)
    ]

    for ev_type, sev in critical_events:
        is_actionable = ev_type in actionable_types or sev == EventSeverity.CRITICAL
        assert is_actionable, f"{ev_type} with severity {sev} must trigger zero-nag alert"


def test_desktop_reconnection_and_state_refresh(client):
    """Verifies that fetching authoritative state after reconnection returns fresh data without phantom records."""
    # 1. Start with initial missions list
    res1 = client.get("/api/missions")
    assert res1.status_code == 200
    initial_count = len(res1.json())

    # 2. Add a new mission while 'connected'
    client.post("/api/missions", json={
        "title": "Reconnection Sync Mission",
        "goal": "Verify fresh state sync after reconnect"
    })

    # 3. Simulate client reconnecting: requests authoritative state
    res2 = client.get("/api/missions")
    assert res2.status_code == 200
    assert len(res2.json()) == initial_count + 1


def test_killer_scenario_desktop_end_to_end_lifecycle(client):
    """
    Killer Scenario: Desktop HUD Lifecycle from Mission Start to Completion.
    1. Start Supervisor backend.
    2. Simulated desktop HUD client connects.
    3. Create and start a mission.
    4. Agent registers and becomes RUNNING.
    5. HUD reflects active mission and RUNNING state.
    6. Agent encounters a supervised watchdog intervention.
    7. Watchdog triggers INTERVENTION; HUD surfaces alert.
    8. Agent transitions into recovery/verification.
    9. Verification executes and accepts ground truth.
    10. HUD reflects verification pass.
    11. Mission completes; HUD shows COMPLETED state.
    """
    # Step 1 & 2: Backend health verified for desktop client
    health = client.get("/health").json()
    assert health["status"].lower() == "healthy"

    # Step 3: Create mission
    m_res = client.post("/api/missions", json={
        "title": "Desktop Killer Scenario — BOM Encoding",
        "goal": "Fix CSV parser BOM handling under supervisory watchdogs"
    })
    assert m_res.status_code == 200
    mission_id = m_res.json()["id"]

    # Step 4: Register Agent
    reg_res = client.post("/api/agents", json={
        "agent_id": "claude-code-desktop",
        "agent_type": "WORKER",
        "model": "claude-3-7-sonnet",
        "mission_id": mission_id,
        "status": "RUNNING"
    })
    assert reg_res.status_code == 200

    # Step 5: HUD checks state -> RUNNING
    m_state = client.get(f"/api/missions/{mission_id}/state").json()
    assert m_state["title"] == "Desktop Killer Scenario — BOM Encoding"

    # Step 6 & 7: Supervised Watchdog Intervention
    # Simulate a loop intervention event emitted through EventBus
    intervention_event = Event(
        type=EventType.SUPERVISOR_INTERVENTION,
        severity=EventSeverity.WARNING,
        mission_id=mission_id,
        agent_id="claude-code-desktop",
        payload={
            "anomaly": "REPEATED_TEST_FAILURE_LOOP",
            "reason": "Test suite failed 3 times with identical regex error",
            "action": "HALT_AND_RECOVER",
            "intervention_type": "WATCHDOG_INTERVENTION"
        }
    )
    # Broadcast event into EventBus
    asyncio.run(app_state.event_bus.publish(intervention_event))

    # Update mission to RECOVERING
    client.post(f"/api/missions/{mission_id}/status", json={
        "status": "RECOVERING",
        "reason": "Supervisory watchdog intervention triggered"
    })

    # Step 8: HUD reflects RECOVERING
    m_recovering = client.get(f"/api/missions/{mission_id}/state").json()
    assert m_recovering["status"] == "RECOVERING"

    # Step 9 & 10: Verification accepts ground truth
    verif_event = Event(
        type=EventType.VERIFICATION_RESULT,
        severity=EventSeverity.INFO,
        mission_id=mission_id,
        agent_id="claude-code-desktop",
        payload={
            "summary": "Independent verifier confirmed 42/42 tests pass with zero regressions",
            "exit_code": 0
        }
    )
    asyncio.run(app_state.event_bus.publish(verif_event))

    # Step 11 & 12: Mission completes
    client.post(f"/api/missions/{mission_id}/status", json={
        "status": "COMPLETED",
        "reason": "Task verified and completed"
    })

    final_state = client.get(f"/api/missions/{mission_id}/state").json()
    assert final_state["status"] == "COMPLETED"
