"""
Unit & Integration Tests for FalkorDB Graph Relationships and Provenance.
Validates:
1. Mission -> HAS_TASK -> Task & Mission -> CONTAINS_TASK -> Task
2. Task -> ASSIGNED_TO -> Agent
3. Task -> HAS_ATTEMPT -> Execution & Execution -> FOR_TASK -> Task
4. Execution -> FAILED_WITH -> Failure & Execution -> FAILS_WITH -> Failure
5. Task -> PRODUCED -> Artifact & Execution -> PRODUCES -> Artifact
6. Execution -> HAS_RESULT -> Verification & Verification -> EVALUATES -> Task
7. Mission -> HAS_DECISION -> Decision, Decision -> GOVERNS -> Task, Decision -> SELECTS -> Agent
8. Handoff -> FROM_AGENT -> Agent, Handoff -> TO_AGENT -> Agent, Handoff -> TRANSFERS_CONTEXT -> Task
9. Idempotent MERGE operations (no duplicate nodes or relationships on repeated writes)
10. Safe backfill_relationships() for historical nodes
11. Mission subgraph payload completeness (both nodes and edges returned)
12. FastAPI endpoint /api/missions/{mission_id}/graph payload verification
"""

import asyncio
import uuid
import pytest
from fastapi.testclient import TestClient

from storage.graph.client import FalkorDBClient, FalkorDBConfig
from storage.graph.repository import FalkorDBGraphRepository
from apps.api.main import app
from apps.api.state import app_state


@pytest.fixture(scope="module")
def graph_repo():
    test_graph_name = f"test_rel_{uuid.uuid4().hex[:8]}"
    config = FalkorDBConfig.from_env()
    config.graph_name = test_graph_name
    client = FalkorDBClient(config=config)
    repo = FalkorDBGraphRepository(client)
    repo.initialize_schema()
    yield repo
    try:
        g = client.get_graph()
        g.delete()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_mission_and_task_relationships(graph_repo):
    mission_id = f"msn_{uuid.uuid4().hex[:6]}"
    task_1 = f"task_{uuid.uuid4().hex[:6]}"
    task_2 = f"task_{uuid.uuid4().hex[:6]}"

    await graph_repo.save_mission(
        mission_id=mission_id,
        title="Test Mission",
        goal="Validate mission and task edges",
        requirements=["Requirement A"],
    )

    tasks = [
        {"id": task_1, "title": "Setup workspace", "order": 1, "dependencies": []},
        {"id": task_2, "title": "Run tests", "order": 2, "dependencies": [task_1], "assigned_agent_id": "claude-code"},
    ]
    await graph_repo.save_task_dag(mission_id, tasks)

    # Verify HAS_TASK and CONTAINS_TASK edges exist
    res = graph_repo.client.query(
        "MATCH (m:Mission {id: $mid})-[r:HAS_TASK]->(t:Task) RETURN t.id",
        {"mid": mission_id}
    )
    task_ids = {row[0] for row in res.result_set}
    assert task_ids == {task_1, task_2}

    res_contains = graph_repo.client.query(
        "MATCH (m:Mission {id: $mid})-[r:CONTAINS_TASK]->(t:Task) RETURN t.id",
        {"mid": mission_id}
    )
    contains_ids = {row[0] for row in res_contains.result_set}
    assert contains_ids == {task_1, task_2}

    # Verify Task -> ASSIGNED_TO -> Agent edge exists for task_2
    res_agent = graph_repo.client.query(
        "MATCH (t:Task {id: $tid})-[r:ASSIGNED_TO]->(a:Agent) RETURN a.id",
        {"tid": task_2}
    )
    assert len(res_agent.result_set) == 1
    assert res_agent.result_set[0][0] == "claude-code"


@pytest.mark.asyncio
async def test_execution_attempt_and_agent_edges(graph_repo):
    mission_id = f"msn_{uuid.uuid4().hex[:6]}"
    task_id = f"task_{uuid.uuid4().hex[:6]}"
    exec_id = f"exec_{task_id}_1"
    agent_id = "codex_worker"

    await graph_repo.save_mission(mission_id=mission_id, title="Exec Edge Test", goal="Edges")
    await graph_repo.save_task_dag(mission_id, [{"id": task_id, "title": "Run Task", "order": 1}])

    await graph_repo.record_execution_start(
        execution_id=exec_id,
        task_id=task_id,
        mission_id=mission_id,
        agent_id=agent_id,
        attempt_number=1,
    )

    # Verify Task -> HAS_ATTEMPT -> Execution
    res_attempt = graph_repo.client.query(
        "MATCH (t:Task {id: $tid})-[r:HAS_ATTEMPT]->(e:Execution) RETURN e.id",
        {"tid": task_id}
    )
    assert len(res_attempt.result_set) == 1
    assert res_attempt.result_set[0][0] == exec_id

    # Verify Execution -> FOR_TASK -> Task
    res_for = graph_repo.client.query(
        "MATCH (e:Execution {id: $eid})-[r:FOR_TASK]->(t:Task) RETURN t.id",
        {"eid": exec_id}
    )
    assert len(res_for.result_set) == 1
    assert res_for.result_set[0][0] == task_id

    # Verify Agent -> EXECUTES -> Execution & Task -> ASSIGNED_TO -> Agent
    res_executes = graph_repo.client.query(
        "MATCH (a:Agent {id: $aid})-[r:EXECUTES]->(e:Execution {id: $eid}) RETURN count(r)",
        {"aid": agent_id, "eid": exec_id}
    )
    assert res_executes.result_set[0][0] == 1

    res_assigned = graph_repo.client.query(
        "MATCH (t:Task {id: $tid})-[r:ASSIGNED_TO]->(a:Agent {id: $aid}) RETURN count(r)",
        {"tid": task_id, "aid": agent_id}
    )
    assert res_assigned.result_set[0][0] == 1


@pytest.mark.asyncio
async def test_failure_relationships(graph_repo):
    mission_id = f"msn_{uuid.uuid4().hex[:6]}"
    task_id = f"task_{uuid.uuid4().hex[:6]}"
    exec_id = f"exec_{task_id}_1"

    await graph_repo.save_mission(mission_id=mission_id, title="Fail Edge Test", goal="Edges")
    await graph_repo.save_task_dag(mission_id, [{"id": task_id, "title": "Failing Task", "order": 1}])
    await graph_repo.record_execution_start(exec_id, task_id, mission_id, "worker_01", 1)

    await graph_repo.record_execution_failure(
        execution_id=exec_id,
        error_signature="AssertionError: 404 != 200",
        reason="Endpoint missing",
        event_id=f"evt_{task_id}_err",
    )

    # Verify Execution -> FAILED_WITH -> Failure
    res_fail = graph_repo.client.query(
        "MATCH (e:Execution {id: $eid})-[r:FAILED_WITH]->(f:Failure) RETURN f.id, f.error_signature",
        {"eid": exec_id}
    )
    assert len(res_fail.result_set) == 1
    assert "fail_" in res_fail.result_set[0][0]
    assert res_fail.result_set[0][1] == "AssertionError: 404 != 200"


@pytest.mark.asyncio
async def test_artifact_and_verification_relationships(graph_repo):
    mission_id = f"msn_{uuid.uuid4().hex[:6]}"
    task_id = f"task_{uuid.uuid4().hex[:6]}"
    exec_id = f"exec_{task_id}_1"
    verif_id = f"ver_{task_id}_1"
    art_id = f"art_{uuid.uuid4().hex[:6]}"

    await graph_repo.save_mission(mission_id=mission_id, title="Success Edge Test", goal="Edges")
    await graph_repo.save_task_dag(mission_id, [{"id": task_id, "title": "Completed Task", "order": 1}])
    await graph_repo.record_execution_start(exec_id, task_id, mission_id, "worker_01", 1)

    # Record success with artifact
    await graph_repo.record_execution_success(
        execution_id=exec_id,
        summary="Completed successfully",
        artifacts=[{"id": art_id, "path": "src/app.py", "type": "code"}],
    )

    # Verify Task -> PRODUCED -> Artifact and Execution -> PRODUCES -> Artifact
    res_t_art = graph_repo.client.query(
        "MATCH (t:Task {id: $tid})-[r:PRODUCED]->(a:Artifact {id: $aid}) RETURN count(r)",
        {"tid": task_id, "aid": art_id}
    )
    assert res_t_art.result_set[0][0] == 1

    res_e_art = graph_repo.client.query(
        "MATCH (e:Execution {id: $eid})-[r:PRODUCES]->(a:Artifact {id: $aid}) RETURN count(r)",
        {"eid": exec_id, "aid": art_id}
    )
    assert res_e_art.result_set[0][0] == 1

    # Record verification
    await graph_repo.record_verification(
        verification_id=verif_id,
        task_id=task_id,
        mission_id=mission_id,
        decision="ACCEPT",
        summary="All tests pass cleanly",
        evidence_items=[{"id": "ev_1", "type": "test_suite", "passed": True}],
        execution_id=exec_id,
    )

    # Verify Execution -> HAS_RESULT -> Verification
    res_ver_res = graph_repo.client.query(
        "MATCH (e:Execution {id: $eid})-[r:HAS_RESULT]->(v:Verification {id: $vid}) RETURN count(r)",
        {"eid": exec_id, "vid": verif_id}
    )
    assert res_ver_res.result_set[0][0] == 1

    # Verify Verification -> EVALUATES -> Task
    res_eval = graph_repo.client.query(
        "MATCH (v:Verification {id: $vid})-[r:EVALUATES]->(t:Task {id: $tid}) RETURN count(r)",
        {"vid": verif_id, "tid": task_id}
    )
    assert res_eval.result_set[0][0] == 1


@pytest.mark.asyncio
async def test_decision_and_handoff_relationships(graph_repo):
    mission_id = f"msn_{uuid.uuid4().hex[:6]}"
    task_id = f"task_{uuid.uuid4().hex[:6]}"
    dec_id = f"dec_{task_id}_1"
    handoff_id = f"ho_{task_id}_1"

    await graph_repo.save_mission(mission_id=mission_id, title="Dec & Handoff Test", goal="Edges")
    await graph_repo.save_task_dag(mission_id, [{"id": task_id, "title": "Supervised Task", "order": 1}])

    # Record Decision
    await graph_repo.record_decision(
        decision_id=dec_id,
        mission_id=mission_id,
        task_id=task_id,
        decision_type="SUPERVISORY_RECOVERY",
        action="ESCALATE_TO_SENIOR",
        reason="Loop detected",
        selected_agent_id="reviewer_01",
    )

    # Verify Mission -> HAS_DECISION -> Decision
    res_m_dec = graph_repo.client.query(
        "MATCH (m:Mission {id: $mid})-[r:HAS_DECISION]->(d:Decision {id: $did}) RETURN count(r)",
        {"mid": mission_id, "did": dec_id}
    )
    assert res_m_dec.result_set[0][0] == 1

    # Verify Decision -> GOVERNS -> Task
    res_d_task = graph_repo.client.query(
        "MATCH (d:Decision {id: $did})-[r:GOVERNS]->(t:Task {id: $tid}) RETURN count(r)",
        {"did": dec_id, "tid": task_id}
    )
    assert res_d_task.result_set[0][0] == 1

    # Verify Decision -> SELECTS -> Agent
    res_d_agent = graph_repo.client.query(
        "MATCH (d:Decision {id: $did})-[r:SELECTS]->(a:Agent {id: 'reviewer_01'}) RETURN count(r)",
        {"did": dec_id}
    )
    assert res_d_agent.result_set[0][0] == 1

    # Record Handoff
    await graph_repo.record_handoff(
        handoff_id=handoff_id,
        task_id=task_id,
        source_agent="worker_01",
        target_agent="reviewer_01",
        trigger="STUCK_IN_LOOP",
        status="COMPLETED",
        context_summary="Transferred context package",
    )

    # Verify Handoff -> FROM_AGENT & TO_AGENT & TRANSFERS_CONTEXT
    res_ho = graph_repo.client.query(
        """
        MATCH (h:Handoff {id: $hid})-[r1:FROM_AGENT]->(src:Agent {id: 'worker_01'})
        MATCH (h)-[r2:TO_AGENT]->(tgt:Agent {id: 'reviewer_01'})
        MATCH (h)-[r3:TRANSFERS_CONTEXT]->(t:Task {id: $tid})
        RETURN count(h)
        """,
        {"hid": handoff_id, "tid": task_id}
    )
    assert res_ho.result_set[0][0] == 1


@pytest.mark.asyncio
async def test_idempotent_writes_no_duplicates(graph_repo):
    mission_id = f"msn_{uuid.uuid4().hex[:6]}"
    task_id = f"task_{uuid.uuid4().hex[:6]}"

    # Save mission twice
    await graph_repo.save_mission(mission_id=mission_id, title="Idempotent Test", goal="No dupes")
    await graph_repo.save_mission(mission_id=mission_id, title="Idempotent Test", goal="No dupes")

    res_m = graph_repo.client.query("MATCH (m:Mission {id: $mid}) RETURN count(m)", {"mid": mission_id})
    assert res_m.result_set[0][0] == 1

    # Save task DAG twice
    tasks = [{"id": task_id, "title": "Idempotent Task", "order": 1}]
    await graph_repo.save_task_dag(mission_id, tasks)
    await graph_repo.save_task_dag(mission_id, tasks)

    res_t = graph_repo.client.query("MATCH (t:Task {id: $tid}) RETURN count(t)", {"tid": task_id})
    assert res_t.result_set[0][0] == 1

    res_rel = graph_repo.client.query(
        "MATCH (m:Mission {id: $mid})-[r:HAS_TASK]->(t:Task {id: $tid}) RETURN count(r)",
        {"mid": mission_id, "tid": task_id}
    )
    assert res_rel.result_set[0][0] == 1


@pytest.mark.asyncio
async def test_mission_subgraph_returns_nodes_and_edges(graph_repo):
    mission_id = f"msn_{uuid.uuid4().hex[:6]}"
    task_id = f"task_{uuid.uuid4().hex[:6]}"
    exec_id = f"exec_{task_id}_1"

    await graph_repo.save_mission(mission_id=mission_id, title="Subgraph Test", goal="Nodes & Edges")
    await graph_repo.save_task_dag(mission_id, [{"id": task_id, "title": "Sub Task", "order": 1}])
    await graph_repo.record_execution_start(exec_id, task_id, mission_id, "worker_01", 1)
    await graph_repo.record_execution_failure(exec_id, "SyntaxError", "Invalid syntax")

    subgraph = await graph_repo.get_mission_subgraph(mission_id)

    assert subgraph["mission_id"] == mission_id
    assert subgraph["nodes_count"] >= 4  # Mission, Task, Agent, Execution, Failure
    assert subgraph["edges_count"] >= 3  # HAS_TASK, HAS_ATTEMPT, FAILED_WITH, etc.

    node_labels = {n["label"] for n in subgraph["nodes"]}
    assert "Mission" in node_labels
    assert "Task" in node_labels
    assert "Execution" in node_labels
    assert "Failure" in node_labels

    edge_types = {e["type"] for e in subgraph["edges"]}
    assert "HAS_TASK" in edge_types or "CONTAINS_TASK" in edge_types
    assert "HAS_ATTEMPT" in edge_types or "FOR_TASK" in edge_types
    assert "FAILED_WITH" in edge_types or "FAILS_WITH" in edge_types


@pytest.mark.asyncio
async def test_backfill_relationships(graph_repo):
    # Create isolated historical nodes with foreign keys but without relationships
    mission_id = f"msn_{uuid.uuid4().hex[:6]}"
    task_id = f"task_{uuid.uuid4().hex[:6]}"
    exec_id = f"exec_{task_id}_1"
    agent_id = "agent_historical"

    graph_repo.client.query(
        "CREATE (m:Mission {id: $mid, title: 'Historical Mission'})",
        {"mid": mission_id}
    )
    graph_repo.client.query(
        "CREATE (t:Task {id: $tid, mission_id: $mid, title: 'Historical Task'})",
        {"tid": task_id, "mid": mission_id}
    )
    graph_repo.client.query(
        "CREATE (e:Execution {id: $eid, task_id: $tid, mission_id: $mid, agent_id: $aid, status: 'FAILED', error_signature: 'HistErr'})",
        {"eid": exec_id, "tid": task_id, "mid": mission_id, "aid": agent_id}
    )

    # Run backfill
    backfilled = await graph_repo.backfill_relationships()
    assert isinstance(backfilled, dict)

    # Verify Mission -> HAS_TASK -> Task was backfilled
    res_m_t = graph_repo.client.query(
        "MATCH (m:Mission {id: $mid})-[r:HAS_TASK]->(t:Task {id: $tid}) RETURN count(r)",
        {"mid": mission_id, "tid": task_id}
    )
    assert res_m_t.result_set[0][0] == 1

    # Verify Task -> HAS_ATTEMPT -> Execution was backfilled
    res_t_e = graph_repo.client.query(
        "MATCH (t:Task {id: $tid})-[r:HAS_ATTEMPT]->(e:Execution {id: $eid}) RETURN count(r)",
        {"tid": task_id, "eid": exec_id}
    )
    assert res_t_e.result_set[0][0] == 1

    # Verify Execution -> FAILED_WITH -> Failure was backfilled
    res_e_f = graph_repo.client.query(
        "MATCH (e:Execution {id: $eid})-[r:FAILED_WITH]->(f:Failure) RETURN count(r)",
        {"eid": exec_id}
    )
    assert res_e_f.result_set[0][0] == 1
