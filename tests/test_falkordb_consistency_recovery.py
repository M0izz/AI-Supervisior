"""
Tests verifying FalkorDB Consistency, Disconnection, Replay Idempotency, and Recovery:
1. Mid-mission FalkorDB disconnection handling (fail-fast with FalkorDBUnavailableError, no silent fallback).
2. Event & DAG replay idempotency (Cypher MERGE guarantees zero duplication of nodes/edges).
3. State recovery across application restarts (in-flight state survives process death).
4. Actual application-level consistency guarantees and boundaries.
"""

import pytest
import uuid
from storage.graph.client import FalkorDBClient, FalkorDBConfig
from storage.graph.repository import FalkorDBGraphRepository
from storage.graph import FalkorDBUnavailableError


@pytest.fixture
def graph_repo():
    config = FalkorDBConfig.from_env()
    config.graph_name = f"test_cons_{uuid.uuid4().hex[:8]}"
    client = FalkorDBClient(config=config)
    if not client.is_available():
        pytest.skip("FalkorDB is not running or accessible")
    repo = FalkorDBGraphRepository(client)
    repo.initialize_schema()
    yield repo
    try:
        client.get_graph().delete()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_replay_idempotency_does_not_duplicate_nodes_or_edges(graph_repo):
    """
    Priority 2:
    Verify that replaying events or re-saving the task DAG does not duplicate
    nodes or relationships in FalkorDB.
    """
    mission_id = f"test_idemp_{uuid.uuid4().hex[:8]}"
    task_id = f"task_{uuid.uuid4().hex[:6]}"
    exec_id = f"exec_{task_id}_1"

    # Step 1: Initial writes
    await graph_repo.save_mission(
        mission_id=mission_id,
        title="Idempotency Test Mission",
        goal="Ensure repeated operations are idempotent",
        requirements=["Requirement A"]
    )
    await graph_repo.save_task_dag(mission_id, [
        {"id": task_id, "title": "Database Schema Setup", "dependencies": []}
    ])
    await graph_repo.record_execution_start(exec_id, task_id, "claude-code", 1)
    await graph_repo.record_execution_event(
        event_id=f"evt_{exec_id}_1",
        execution_id=exec_id,
        event_type="CODE_EDITED",
        severity="INFO",
        payload={"file": "schema.sql"}
    )
    await graph_repo.record_execution_success(
        exec_id,
        summary="Schema created",
        artifacts=[{"id": f"art_{exec_id}_1", "path": "schema.sql", "type": "file"}]
    )

    subgraph_first = await graph_repo.get_mission_subgraph(mission_id)
    initial_node_count = subgraph_first["nodes_count"]
    initial_edge_count = subgraph_first["edges_count"]

    # Step 2: Replay the EXACT SAME events, mission, task DAG, and execution
    await graph_repo.save_mission(
        mission_id=mission_id,
        title="Idempotency Test Mission",
        goal="Ensure repeated operations are idempotent",
        requirements=["Requirement A"]
    )
    await graph_repo.save_task_dag(mission_id, [
        {"id": task_id, "title": "Database Schema Setup", "dependencies": []}
    ])
    await graph_repo.record_execution_start(exec_id, task_id, "claude-code", 1)
    await graph_repo.record_execution_event(
        event_id=f"evt_{exec_id}_1",
        execution_id=exec_id,
        event_type="CODE_EDITED",
        severity="INFO",
        payload={"file": "schema.sql"}
    )
    await graph_repo.record_execution_success(
        exec_id,
        summary="Schema created",
        artifacts=[{"id": f"art_{exec_id}_1", "path": "schema.sql", "type": "file"}]
    )

    subgraph_second = await graph_repo.get_mission_subgraph(mission_id)
    
    # Assert zero duplication
    assert subgraph_second["nodes_count"] == initial_node_count, (
        f"Replay created duplicate nodes! Before: {initial_node_count}, After: {subgraph_second['nodes_count']}"
    )
    assert subgraph_second["edges_count"] == initial_edge_count, (
        f"Replay created duplicate edges! Before: {initial_edge_count}, After: {subgraph_second['edges_count']}"
    )


@pytest.mark.asyncio
async def test_mid_mission_disconnection_raises_falkordb_unavailable_error(graph_repo):
    """
    Priority 2:
    Verify behavior when FalkorDB disconnects mid-mission.
    AI Supervisor explicitly raises FalkorDBUnavailableError so the operator
    is immediately informed, preventing uncoordinated split-brain execution.
    """
    mission_id = f"test_disc_{uuid.uuid4().hex[:8]}"
    
    # Successfully save mission
    await graph_repo.save_mission(
        mission_id=mission_id,
        title="Disconnection Resilience Mission",
        goal="Test system behavior when graph socket breaks",
        requirements=["Reliable failure reporting"]
    )

    # Simulate network disconnect or broker crash by targeting an unreachable port
    broken_config = FalkorDBConfig(host="localhost", port=59999, timeout=0.5)
    broken_client = FalkorDBClient(config=broken_config)
    broken_repo = FalkorDBGraphRepository(broken_client)

    # 1. Health check reports unavailable cleanly
    health = broken_client.check_health()
    assert health["connected"] is False
    assert health["status"] in ("UNHEALTHY", "UNAVAILABLE")

    # 2. Graph write fails fast with FalkorDBUnavailableError
    with pytest.raises(FalkorDBUnavailableError) as exc_info:
        await broken_repo.save_task_dag(mission_id, [{"id": "task_fail", "title": "Fail Task", "dependencies": []}])
    
    assert "FalkorDB" in str(exc_info.value)

    # 3. Graph query also fails fast with FalkorDBUnavailableError
    with pytest.raises(FalkorDBUnavailableError):
        await broken_repo.get_task_graph_context(mission_id, "task_fail")


@pytest.mark.asyncio
async def test_state_recovery_across_application_restart():
    """
    Priority 2:
    Simulate an application crash during recovery:
    1. Process 1 records task, execution 1 failure, and a supervisory decision.
    2. Process terminates (both client and repo are deleted).
    3. Process 2 starts up fresh with a new client connection.
    4. Process 2 queries FalkorDB and immediately recovers full mission memory,
       the failed attempt, the error signature, and the supervisor decision.
    """
    mission_id = f"test_restart_{uuid.uuid4().hex[:8]}"
    task_id = f"task_recover_{uuid.uuid4().hex[:6]}"
    exec_1_id = f"exec_{task_id}_1"
    dec_id = f"dec_{uuid.uuid4().hex[:8]}"

    test_graph_name = f"test_restart_{uuid.uuid4().hex[:8]}"
    config_p1 = FalkorDBConfig.from_env()
    config_p1.graph_name = test_graph_name
    client_p1 = FalkorDBClient(config=config_p1)
    if not client_p1.is_available():
        pytest.skip("FalkorDB not available")
    repo_p1 = FalkorDBGraphRepository(client_p1)
    repo_p1.initialize_schema()

    try:
        await repo_p1.save_mission(
            mission_id=mission_id,
            title="App Crash Recovery Mission",
            goal="Verify graph preserves state across total process restart",
            requirements=["Requirement: Zero context loss across restarts"]
        )
        await repo_p1.save_task_dag(mission_id, [{"id": task_id, "title": "Build Neural Cache", "dependencies": []}])
        await repo_p1.record_execution_start(exec_1_id, task_id, "claude-code", 1)
        await repo_p1.record_execution_failure(
            execution_id=exec_1_id,
            error_signature="CUDA_OUT_OF_MEMORY",
            reason="Allocated 16GB VRAM on batch size 64",
            event_id=f"evt_oom_{uuid.uuid4().hex[:6]}"
        )
        await repo_p1.record_decision(
            decision_id=dec_id,
            mission_id=mission_id,
            task_id=task_id,
            decision_type="REDUCE_BATCH_SIZE",
            action="DECREASE_BATCH_SIZE_TO_16",
            reason="Recover from CUDA OOM by lowering batch allocation"
        )

        # Simulate total crash of Process 1: Discard instances
        del repo_p1
        del client_p1

        # Process 2: Fresh cold start with same persistent graph
        config_p2 = FalkorDBConfig.from_env()
        config_p2.graph_name = test_graph_name
        client_p2 = FalkorDBClient(config=config_p2)
        repo_p2 = FalkorDBGraphRepository(client_p2)

        # Query context from FalkorDB on cold start
        recovered_context = await repo_p2.get_task_graph_context(mission_id, task_id)
        assert len(recovered_context["prior_attempts"]) == 1
        attempt = recovered_context["prior_attempts"][0]
        assert attempt["execution_id"] == exec_1_id
        assert attempt["status"] == "FAILED"
        assert attempt["error_signature"] == "CUDA_OUT_OF_MEMORY"

        assert len(recovered_context["decisions"]) == 1
        decision = recovered_context["decisions"][0]
        assert decision["decision_id"] == dec_id
        assert decision["action"] == "DECREASE_BATCH_SIZE_TO_16"

        # Process 2 resumes with Execution attempt 2 informed by recovered context
        exec_2_id = f"exec_{task_id}_2"
        await repo_p2.record_execution_start(exec_2_id, task_id, "claude-code", 2)
        await repo_p2.record_execution_success(exec_2_id, summary="Batch size 16 trained cleanly with no OOM")

        subgraph = await repo_p2.get_mission_subgraph(mission_id)
        # Both execution 1 and execution 2 are linked in the graph
        execution_nodes = [n for n in subgraph["nodes"] if n["label"] == "Execution"]
        assert len(execution_nodes) == 2
        assert any(n["id"] == exec_1_id for n in execution_nodes)
        assert any(n["id"] == exec_2_id for n in execution_nodes)
    finally:
        try:
            client_cleanup = FalkorDBClient(config=config_p1)
            client_cleanup.get_graph().delete()
        except Exception:
            pass
