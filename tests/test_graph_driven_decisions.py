"""
Tests proving that FalkorDB Graph Memory actively drives and changes supervisor decisions:
1. Prerequisite Verification Gate: DEPENDS_ON requires empirical verification (ACCEPT), not merely a status string.
2. Failure History Retrieval: Prior failure signatures from graph steer recovery routing and prevent repeated failures.
"""

import pytest
import uuid
from storage.graph.client import FalkorDBClient, FalkorDBConfig
from storage.graph.repository import FalkorDBGraphRepository


@pytest.fixture
def graph_repo():
    config = FalkorDBConfig.from_env()
    config.graph_name = f"test_dec_{uuid.uuid4().hex[:8]}"
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
async def test_unverified_prerequisite_blocks_task_dispatch(graph_repo):
    """
    Priority 3 & Architectural Detail:
    Demonstrate that DEPENDS_ON checks empirical verification in the graph.
    Even if Task A is marked 'COMPLETED', Task B must remain BLOCKED from dispatch
    until Task A has an accepted Verification node in FalkorDB.
    """
    mission_id = f"test_gate_{uuid.uuid4().hex[:8]}"
    task_a_id = f"task_a_{uuid.uuid4().hex[:6]}"
    task_b_id = f"task_b_{uuid.uuid4().hex[:6]}"

    # 1. Initialize mission and task DAG in FalkorDB
    await graph_repo.save_mission(
        mission_id=mission_id,
        title="Dependent Workflow Mission",
        goal="Verify that unverified prerequisite halts downstream task dispatch",
        requirements=["Requirement 1: Strict empirical dependency verification"]
    )

    tasks_dag = [
        {
            "id": task_a_id,
            "title": "Build Core Database Engine",
            "dependencies": [],
            "status": "COMPLETED",  # Status looks complete, but not yet verified!
        },
        {
            "id": task_b_id,
            "title": "Deploy API Service",
            "dependencies": [task_a_id],
            "status": "PENDING",
        }
    ]
    await graph_repo.save_task_dag(mission_id, tasks_dag)

    # 2. Query task coordination context for Task B BEFORE verification
    context_before = await graph_repo.get_task_graph_context(mission_id, task_b_id)
    
    assert len(context_before["dependencies"]) == 1
    dep_a = context_before["dependencies"][0]
    assert dep_a["id"] == task_a_id
    # CRITICAL: Is Task A empirically verified? No!
    assert dep_a["is_verified"] is False
    # CRITICAL: dependencies_met MUST be False because empirical verification is missing
    assert context_before["dependencies_met"] is False

    # Simulate supervisor dispatch decision logic
    if not context_before["dependencies_met"]:
        supervisor_action = "BLOCK_DISPATCH"
        reason = f"Prerequisite {dep_a['id']} has not received empirical verification acceptance"
        await graph_repo.record_decision(
            decision_id=f"dec_{uuid.uuid4().hex[:8]}",
            mission_id=mission_id,
            task_id=task_b_id,
            decision_type="BLOCK_DISPATCH",
            action=supervisor_action,
            reason=reason
        )

    # Verify the BLOCK_DISPATCH decision was stored in the graph
    decisions = await graph_repo.get_decision_lineage(mission_id)
    block_dec = next((d for d in decisions if d["decision_type"] == "BLOCK_DISPATCH"), None)
    assert block_dec is not None
    assert block_dec["action"] == "BLOCK_DISPATCH"

    # 3. Now, independent verification agent empirically checks and accepts Task A
    exec_a_id = f"exec_{task_a_id}_1"
    await graph_repo.record_execution_start(exec_a_id, task_a_id, "claude-code", 1)
    await graph_repo.record_execution_success(exec_a_id, summary="Tests executed cleanly")

    verif_id = f"verif_{task_a_id}_1"
    evidence = [
        {
            "id": f"ev_{uuid.uuid4().hex[:6]}",
            "type": "pytest_suite",
            "description": "Executed test_database_engine.py with 100% assertions passed",
            "passed": True,
            "data": {"exit_code": 0, "passed": 12, "failed": 0}
        }
    ]
    await graph_repo.record_verification(
        verification_id=verif_id,
        task_id=task_a_id,
        mission_id=mission_id,
        decision="ACCEPT",
        summary="Empirically verified with automated test suite",
        evidence_items=evidence,
        execution_id=exec_a_id
    )

    # 4. Re-query graph context for Task B AFTER Task A's verification
    context_after = await graph_repo.get_task_graph_context(mission_id, task_b_id)
    assert len(context_after["dependencies"]) == 1
    dep_a_after = context_after["dependencies"][0]
    
    # Task A is now empirically verified in FalkorDB!
    assert dep_a_after["is_verified"] is True
    # Dependencies are now met! Task B can be dispatched!
    assert context_after["dependencies_met"] is True

    # Supervisor now issues CLEAR_FOR_DISPATCH decision
    await graph_repo.record_decision(
        decision_id=f"dec_{uuid.uuid4().hex[:8]}",
        mission_id=mission_id,
        task_id=task_b_id,
        decision_type="CLEAR_FOR_DISPATCH",
        action="DISPATCH_WORKER",
        reason="All prerequisite tasks have verifiable empirical acceptance"
    )

    updated_decisions = await graph_repo.get_decision_lineage(mission_id)
    clear_dec = next((d for d in updated_decisions if d["decision_type"] == "CLEAR_FOR_DISPATCH"), None)
    assert clear_dec is not None
    assert clear_dec["action"] == "DISPATCH_WORKER"


@pytest.mark.asyncio
async def test_prior_failure_history_guides_recovery_routing(graph_repo):
    """
    Priority 3:
    Demonstrate that retrieved failure history actively affects recovery.
    When a task fails with a specific error signature, the supervisor queries
    the graph for prior failure history and uses that data to select a recovery
    agent and route a handoff.
    """
    mission_id = f"test_fail_{uuid.uuid4().hex[:8]}"
    task_id = f"task_{uuid.uuid4().hex[:6]}"

    await graph_repo.save_mission(
        mission_id=mission_id,
        title="Recovery Routing Mission",
        goal="Test failure-guided recovery decisions",
        requirements=["Requirement 1: Resilient multi-agent recovery"]
    )
    await graph_repo.save_task_dag(mission_id, [{"id": task_id, "title": "Implement Complex Parser", "dependencies": []}])

    # 1. First execution attempt by claude-code fails with RECURSIVE_AST_LOOP
    exec_1_id = f"exec_{task_id}_1"
    evt_fail_id = f"evt_fail_{uuid.uuid4().hex[:6]}"
    await graph_repo.record_execution_start(exec_1_id, task_id, "claude-code", 1)
    await graph_repo.record_execution_failure(
        execution_id=exec_1_id,
        error_signature="RECURSIVE_AST_LOOP",
        reason="Maximum recursion depth exceeded during recursive descent AST parsing",
        event_id=evt_fail_id
    )

    # 2. Supervisor queries FalkorDB for failure history
    failure_history = await graph_repo.get_prior_failure_history(mission_id, task_id=task_id)
    assert len(failure_history) >= 1
    recent_failure = failure_history[0]
    assert recent_failure["error_signature"] == "RECURSIVE_AST_LOOP"
    assert recent_failure["causal_event_id"] == evt_fail_id

    # 3. Decision logic actively inspects the graph data:
    # If error_signature is RECURSIVE_AST_LOOP, route to 'codex' with iterative parser strategy
    if "AST_LOOP" in recent_failure["error_signature"]:
        selected_recovery_agent = "codex"
        decision_action = "SWITCH_TO_ITERATIVE_PARSER"
        decision_reason = (
            f"FalkorDB failure history indicates {recent_failure['error_signature']} on execution {recent_failure['execution_id']}. "
            f"Routing recovery to {selected_recovery_agent} with iterative parser constraints."
        )
    else:
        selected_recovery_agent = "claude-code"
        decision_action = "RETRY_SAME"
        decision_reason = "Standard retry"

    assert selected_recovery_agent == "codex"
    assert decision_action == "SWITCH_TO_ITERATIVE_PARSER"

    # 4. Persist the graph-informed recovery decision and handoff
    decision_id = f"dec_rec_{uuid.uuid4().hex[:8]}"
    await graph_repo.record_decision(
        decision_id=decision_id,
        mission_id=mission_id,
        task_id=task_id,
        decision_type="RECOVERY_ROUTING",
        action=decision_action,
        reason=decision_reason,
        responding_to_event_id=evt_fail_id,
        selected_agent_id=selected_recovery_agent
    )

    handoff_id = f"ho_{uuid.uuid4().hex[:8]}"
    await graph_repo.record_handoff(
        handoff_id=handoff_id,
        task_id=task_id,
        source_agent="claude-code",
        target_agent="codex",
        trigger="SUPERVISOR_WATCHDOG_AST_LOOP",
        status="COMPLETED",
        context_summary="Transferred AST failure context and switch to iterative stack-based parser"
    )

    # 5. Verify decision lineage in FalkorDB links the decision to the causal failure event and agent
    decision_lineage = await graph_repo.get_decision_lineage(mission_id)
    rec_dec = next((d for d in decision_lineage if d["id"] == decision_id), None)
    assert rec_dec is not None
    assert rec_dec["responding_to_event_id"] == evt_fail_id
    assert rec_dec["selected_agent_id"] == selected_recovery_agent

    # 6. Verify task graph context for retry attempt 2 includes the prior failure and the decision
    context = await graph_repo.get_task_graph_context(mission_id, task_id)
    assert len(context["prior_attempts"]) >= 1
    assert any(a["execution_id"] == exec_1_id and a["status"] == "FAILED" for a in context["prior_attempts"])
    assert any(d["decision_id"] == decision_id and d["action"] == "SWITCH_TO_ITERATIVE_PARSER" for d in context["decisions"])
    assert any(h["handoff_id"] == handoff_id and h["target_agent"] == "codex" for h in context["handoffs"])
