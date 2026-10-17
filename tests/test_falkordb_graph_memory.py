"""
Automated Integration Tests for FalkorDB Graph Memory and Coordination Layer.

Validates all 10 core competition requirements:
1. Connection and health reporting.
2. Idempotent creation of missions, tasks, and execution events.
3. Correct task-dependency traversal.
4. Retrieval of previous failures for a related retry.
5. Context retrieval across a handoff.
6. Preservation of distinct execution attempts.
7. Traceability from a verification result to its evidence.
8. Correct handling of unavailable FalkorDB without pretending graph-dependent operations succeeded.
9. Persistence across application restart.
10. Enforcement of the plan-approval gate.
"""

import asyncio
import os
import uuid
import pytest
from fastapi.testclient import TestClient

from storage.graph.client import FalkorDBClient, FalkorDBConfig, FalkorDBUnavailableError
from storage.graph.repository import FalkorDBGraphRepository
from apps.api.main import app
from apps.api.state import app_state


@pytest.fixture(scope="module")
def graph_repo():
    """Initializes a dedicated test graph in FalkorDB."""
    test_graph_name = f"test_graph_{uuid.uuid4().hex[:8]}"
    config = FalkorDBConfig.from_env()
    config.graph_name = test_graph_name
    client = FalkorDBClient(config=config)
    repo = FalkorDBGraphRepository(client)
    repo.initialize_schema()
    yield repo
    # Teardown: delete test graph
    try:
        g = client.get_graph()
        g.delete()
    except Exception:
        pass


# =========================================================================
# 1. Connection and health reporting
# =========================================================================
def test_connection_and_health_reporting(graph_repo):
    health = graph_repo.client.check_health()
    assert health["connected"] is True
    assert health["status"] == "HEALTHY"
    assert health["port"] == 6379
    assert health["latency_ms"] >= 0
    assert "nodes_count" in health
    assert "relationships_count" in health


# =========================================================================
# 2. Idempotent creation of missions, tasks, and execution events
# =========================================================================
@pytest.mark.asyncio
async def test_idempotent_creation(graph_repo):
    mission_id = f"m_idem_{uuid.uuid4().hex[:6]}"
    reqs = [
        {"id": f"{mission_id}_r1", "description": "Support UTF-8 BOM", "category": "in_scope"},
        {"id": f"{mission_id}_r2", "description": "Do not break ASCII parsing", "category": "in_scope"},
    ]

    # First write
    res1 = await graph_repo.save_mission(
        mission_id=mission_id,
        title="BOM Mission",
        goal="Handle UTF-8 BOM parsing",
        repository_path="./demo/sample-project",
        status="AWAITING_APPROVAL",
        requirements=reqs,
    )
    assert res1["mission_id"] == mission_id

    # Second identical write (must be idempotent)
    res2 = await graph_repo.save_mission(
        mission_id=mission_id,
        title="BOM Mission",
        goal="Handle UTF-8 BOM parsing",
        repository_path="./demo/sample-project",
        status="AWAITING_APPROVAL",
        requirements=reqs,
    )
    assert res2["mission_id"] == mission_id

    # Verify requirement node count is exactly 2, not duplicated
    check_query = """
    MATCH (m:Mission {id: $mid})-[:HAS_REQUIREMENT]->(r:Requirement)
    RETURN count(r) AS cnt
    """
    res = graph_repo.client.query(check_query, {"mid": mission_id})
    assert res.result_set[0][0] == 2

    # Idempotent task creation
    tasks = [
        {"id": f"{mission_id}_t1", "title": "Setup Parser", "order": 1, "dependencies": []},
        {"id": f"{mission_id}_t2", "title": "Verify Parser", "order": 2, "dependencies": [f"{mission_id}_t1"]},
    ]
    await graph_repo.save_task_dag(mission_id, tasks)
    await graph_repo.save_task_dag(mission_id, tasks)  # Repeated call

    task_cnt = graph_repo.client.query(
        "MATCH (m:Mission {id: $mid})-[:CONTAINS_TASK]->(t:Task) RETURN count(t) AS cnt",
        {"mid": mission_id},
    )
    assert task_cnt.result_set[0][0] == 2


# =========================================================================
# 3. Correct task-dependency traversal
# =========================================================================
@pytest.mark.asyncio
async def test_task_dependency_traversal(graph_repo):
    mission_id = f"m_dep_{uuid.uuid4().hex[:6]}"
    await graph_repo.save_mission(mission_id, "Pipeline Mission", "Test DAG dependencies")

    t1_id = f"{mission_id}_t1"
    t2_id = f"{mission_id}_t2"
    t3_id = f"{mission_id}_t3"

    # t3 depends on both t1 and t2
    tasks = [
        {"id": t1_id, "title": "Database Schema", "order": 1, "status": "COMPLETED", "dependencies": []},
        {"id": t2_id, "title": "API Handlers", "order": 2, "status": "IN_PROGRESS", "dependencies": []},
        {"id": t3_id, "title": "Integration Tests", "order": 3, "status": "PENDING", "dependencies": [t1_id, t2_id]},
    ]
    await graph_repo.save_task_dag(mission_id, tasks)

    # Traverse context for t3
    ctx = await graph_repo.get_task_graph_context(mission_id, t3_id)
    assert len(ctx["dependencies"]) == 2
    dep_ids = {d["id"] for d in ctx["dependencies"]}
    assert t1_id in dep_ids
    assert t2_id in dep_ids

    # Dependencies are not yet all completed (t2 is IN_PROGRESS)
    assert ctx["dependencies_met"] is False


# =========================================================================
# 4. Retrieval of previous failures for a related retry
# =========================================================================
@pytest.mark.asyncio
async def test_failure_retrieval_for_retry(graph_repo):
    mission_id = f"m_fail_{uuid.uuid4().hex[:6]}"
    task_id = f"{mission_id}_task_parser"
    await graph_repo.save_mission(mission_id, "Fail Mission", "Test failure retrieval")
    await graph_repo.save_task_dag(mission_id, [{"id": task_id, "title": "Parser Task", "order": 1}])
    await graph_repo.register_agent("worker_01", "WORKER", "nemotron", "Autonomous Worker")

    # Record first execution failure
    exec1_id = f"exec_{task_id}_1"
    await graph_repo.record_execution_start(exec1_id, task_id, mission_id, "worker_01", attempt_number=1)
    evt1_id = f"evt_{uuid.uuid4().hex[:8]}"
    await graph_repo.record_execution_event(
        exec1_id,
        evt1_id,
        event_type="TEST_FAILED",
        severity="WARNING",
        payload={"error": "AssertionError: UTF-8 BOM byte mismatch"},
    )
    await graph_repo.record_execution_failure(
        exec1_id,
        error_signature="AssertionError: UTF-8 BOM",
        reason="Initial parser fails BOM check",
        event_id=evt1_id,
    )

    # Retrieve prior failures for this task
    failures = await graph_repo.get_prior_failure_history(mission_id, task_id=task_id)
    assert len(failures) >= 1
    assert failures[0]["execution_id"] == exec1_id
    assert failures[0]["error_signature"] == "AssertionError: UTF-8 BOM"
    assert failures[0]["event_id"] == evt1_id

    # Record recovery decision responding to the failure
    dec_id = f"dec_{uuid.uuid4().hex[:8]}"
    await graph_repo.record_decision(
        decision_id=dec_id,
        mission_id=mission_id,
        task_id=task_id,
        decision_type="SUPERVISORY_RECOVERY",
        action="PATCH_STRIP_BOM",
        reason="Strip \\ufeff in parser input",
        responding_to_event_id=evt1_id,
        selected_agent_id="worker_01",
    )

    # Verify decision lineage traversal
    lineage = await graph_repo.get_decision_lineage(mission_id)
    assert len(lineage) >= 1
    assert lineage[0]["decision_id"] == dec_id
    assert lineage[0]["causal_event"]["id"] == evt1_id
    assert lineage[0]["selected_agent"]["id"] == "worker_01"


# =========================================================================
# 5. Context retrieval across a handoff
# =========================================================================
@pytest.mark.asyncio
async def test_handoff_context_retrieval(graph_repo):
    mission_id = f"m_ho_{uuid.uuid4().hex[:6]}"
    task_id = f"{mission_id}_task_api"
    await graph_repo.save_mission(mission_id, "Handoff Mission", "Test handoff context")
    await graph_repo.save_task_dag(mission_id, [{"id": task_id, "title": "API Implementation", "order": 1}])
    await graph_repo.register_agent("worker_01", "WORKER", "nemotron")
    await graph_repo.register_agent("claude_code", "WORKER", "claude-3-7-sonnet")

    # Record handoff from worker_01 to claude_code
    ho_id = f"ho_{uuid.uuid4().hex[:8]}"
    await graph_repo.record_handoff(
        handoff_id=ho_id,
        task_id=task_id,
        source_agent="worker_01",
        target_agent="claude_code",
        trigger="STALL_THRESHOLD_EXCEEDED",
        status="COMPLETED",
        context_summary="Transferred after 3 unresolvable test loops in worker_01",
    )

    ctx = await graph_repo.get_task_graph_context(mission_id, task_id)
    assert len(ctx["handoffs"]) == 1
    assert ctx["handoffs"][0]["id"] == ho_id
    assert ctx["handoffs"][0]["source_agent"] == "worker_01"
    assert ctx["handoffs"][0]["target_agent"] == "claude_code"
    assert ctx["handoffs"][0]["trigger"] == "STALL_THRESHOLD_EXCEEDED"


# =========================================================================
# 6. Preservation of distinct execution attempts
# =========================================================================
@pytest.mark.asyncio
async def test_preservation_of_distinct_attempts(graph_repo):
    mission_id = f"m_attempts_{uuid.uuid4().hex[:6]}"
    task_id = f"{mission_id}_t1"
    await graph_repo.save_mission(mission_id, "Attempt Tracking Mission", "Verify attempt preservation")
    await graph_repo.save_task_dag(mission_id, [{"id": task_id, "title": "Multi Attempt Task", "order": 1}])
    await graph_repo.register_agent("worker_01", "WORKER", "nemotron")

    # Attempt 1: Fails
    exec1 = f"exec_{task_id}_1"
    await graph_repo.record_execution_start(exec1, task_id, mission_id, "worker_01", attempt_number=1)
    await graph_repo.record_execution_failure(exec1, "SyntaxError", "Invalid syntax")

    # Attempt 2: Fails
    exec2 = f"exec_{task_id}_2"
    await graph_repo.record_execution_start(exec2, task_id, mission_id, "worker_01", attempt_number=2)
    await graph_repo.record_execution_failure(exec2, "TypeError", "Type mismatch")

    # Attempt 3: Succeeds
    exec3 = f"exec_{task_id}_3"
    await graph_repo.record_execution_start(exec3, task_id, mission_id, "worker_01", attempt_number=3)
    await graph_repo.record_execution_success(exec3, "All unit tests pass", [{"path": "src/parser.py"}])

    # Verify that all 3 distinct attempts exist and are preserved in the graph
    ctx = await graph_repo.get_task_graph_context(mission_id, task_id)
    assert ctx["total_attempts"] == 3
    attempts = {e["attempt_number"]: e["status"] for e in ctx["prior_executions"]}
    assert attempts[1] == "FAILED"
    assert attempts[2] == "FAILED"
    assert attempts[3] == "COMPLETED"


# =========================================================================
# 7. Traceability from a verification result to its evidence
# =========================================================================
@pytest.mark.asyncio
async def test_verification_evidence_traceability(graph_repo):
    mission_id = f"m_ver_{uuid.uuid4().hex[:6]}"
    task_id = f"{mission_id}_t_verify"
    await graph_repo.save_mission(mission_id, "Verification Mission", "Test evidence traceability")
    await graph_repo.save_task_dag(mission_id, [{"id": task_id, "title": "Verified Code", "order": 1}])

    ver_id = f"ver_{uuid.uuid4().hex[:8]}"
    evidence = [
        {"id": f"ev_{uuid.uuid4().hex[:6]}", "type": "pytest_output", "description": "10 passed, 0 failed in 0.4s", "passed": True},
        {"id": f"ev_{uuid.uuid4().hex[:6]}", "type": "git_diff_check", "description": "Only src/parser.py mutated", "passed": True},
    ]

    await graph_repo.record_verification(
        verification_id=ver_id,
        task_id=task_id,
        mission_id=mission_id,
        decision="ACCEPT",
        summary="Independent tests and diff constraints verified",
        evidence_items=evidence,
    )

    trace = await graph_repo.get_verification_trace(task_id)
    assert trace["verified"] is True
    assert trace["verification_id"] == ver_id
    assert trace["decision"] == "ACCEPT"
    assert len(trace["evidence"]) == 2
    ev_types = {e["type"] for e in trace["evidence"]}
    assert "pytest_output" in ev_types
    assert "git_diff_check" in ev_types


# =========================================================================
# 8. Handling of unavailable FalkorDB without pretending success
# =========================================================================
def test_unavailable_falkordb_fails_clearly():
    # Configure an unreachable port
    unreachable_config = FalkorDBConfig(host="127.0.0.1", port=59999, timeout=1.0)
    unreachable_client = FalkorDBClient(config=unreachable_config)

    # Health check should report UNHEALTHY honestly, not fake healthy
    health = unreachable_client.check_health()
    assert health["connected"] is False
    assert health["status"] == "UNHEALTHY"
    assert health["error"] is not None

    # Graph operations must raise FalkorDBUnavailableError, never silently succeed
    with pytest.raises(FalkorDBUnavailableError) as exc_info:
        unreachable_client.query("RETURN 1")
    assert "unavailable" in str(exc_info.value).lower()


# =========================================================================
# 9. Persistence across application restart
# =========================================================================
@pytest.mark.asyncio
async def test_persistence_across_restart(graph_repo):
    mission_id = f"m_restart_{uuid.uuid4().hex[:6]}"
    task_id = f"{mission_id}_t1"
    await graph_repo.save_mission(mission_id, "Persistence Test", "Verify restart survival")
    await graph_repo.save_task_dag(mission_id, [{"id": task_id, "title": "Survivor Task", "order": 1}])
    await graph_repo.record_execution_start(f"exec_{task_id}_1", task_id, mission_id, "worker_01", attempt_number=1)
    await graph_repo.record_execution_success(f"exec_{task_id}_1", "Completed before restart")

    # Simulate full application restart by creating completely fresh client & repo instances
    new_client = FalkorDBClient(config=graph_repo.client.config)
    new_repo = FalkorDBGraphRepository(new_client)

    # Query from the fresh instance
    ctx = await new_repo.get_task_graph_context(mission_id, task_id)
    assert ctx["total_attempts"] == 1
    assert ctx["prior_executions"][0]["status"] == "COMPLETED"
    assert ctx["prior_executions"][0]["summary"] == "Completed before restart"


# =========================================================================
# 10. Enforcement of the plan-approval gate
# =========================================================================
def test_plan_approval_gate_enforced_with_graph():
    client = TestClient(app)

    # Create mission: status must be AWAITING_APPROVAL
    res = client.post("/api/missions", json={"title": "Gated Mission", "goal": "Enforce plan approval gate"})
    assert res.status_code == 200
    m_data = res.json()
    mid = m_data["id"]
    assert m_data["status"] == "AWAITING_APPROVAL"

    # Attempting to start or execute before approval must be rejected with PLAN_NOT_APPROVED
    start_res = client.post(f"/api/missions/{mid}/start")
    assert start_res.status_code == 400
    assert start_res.json()["detail"]["error"] == "PLAN_NOT_APPROVED"

    exec_res = client.post(f"/api/missions/{mid}/execute")
    assert exec_res.status_code == 400
    assert exec_res.json()["detail"]["error"] == "PLAN_NOT_APPROVED"

    # Approve plan
    appr_res = client.post(f"/api/missions/{mid}/plan/approve", json={"version": 1})
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"

    # Verify graph health endpoint
    health_res = client.get("/api/graph/health")
    assert health_res.status_code == 200
    assert health_res.json()["connected"] is True

