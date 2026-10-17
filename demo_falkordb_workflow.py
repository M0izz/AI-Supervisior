"""
FalkorDB Graph Hacks - End-to-End Real Mission Demonstration.

Demonstrates:
1. Mission submission and plan approval.
2. Graph-guided task dispatch with FalkorDB context retrieval.
3. Execution attempt 1 recording controlled failure (UTF-8 BOM AssertionError).
4. Cypher traversal of prior failure history from FalkorDB.
5. Supervisory recovery decision informed by graph context.
6. Execution attempt 2 with repair, test pass, and independent verification.
7. Application restart simulation.
8. Post-restart FalkorDB verification showing intact mission memory, execution attempts,
   decision provenance, and verification evidence relationships.
"""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from storage.graph.client import FalkorDBClient, FalkorDBConfig
from storage.graph.repository import FalkorDBGraphRepository
from core.events.bus import EventBus
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus
from core.tasks.manager import TaskManager
from core.verification.engine import VerificationEngine
from core.verification.models import VerificationContext, VerificationDecision
from execution.mission_runner import MissionRunner
from memory.store import MemoryStore
from execution.worktree import GitWorktreeManager
from adapters.registry import AdapterRegistry
from storage.sqlite import (
    DatabaseManager,
    MissionRepository,
    TaskRepository,
    VerificationRepository,
    MemoryRepository,
)


async def run_demo():
    print("=" * 80)
    print("AI SUPERVISOR x FALKORDB: GRAPH MEMORY & COORDINATION LAYER DEMO")
    print("=" * 80)

    # Isolated demo workspace and DB
    demo_dir = Path(tempfile.mkdtemp(prefix="falkordb_demo_"))
    db_file = demo_dir / "demo_supervisor.db"
    db = DatabaseManager(db_path=str(db_file))
    event_bus = EventBus()

    # Configure dedicated FalkorDB Graph for demo
    demo_graph_name = f"demo_falkor_{uuid.uuid4().hex[:6]}"
    falkor_cfg = FalkorDBConfig.from_env()
    falkor_cfg.graph_name = demo_graph_name

    falkor_client = FalkorDBClient(config=falkor_cfg)
    graph_repo = FalkorDBGraphRepository(falkor_client)
    graph_repo.initialize_schema()

    print(f"\n[PHASE 3] FalkorDB Connected to Graph: '{demo_graph_name}'")
    health = falkor_client.check_health()
    print(f"Health: {health['status']} | Latency: {health['latency_ms']}ms | Connected: {health['connected']}")

    # Setup repositories and managers with graph_repository wired
    mission_repo = MissionRepository(db)
    task_repo = TaskRepository(db)
    ver_repo = VerificationRepository(db)
    mem_repo = MemoryRepository(db)

    mission_manager = MissionManager(event_bus, repository=mission_repo, graph_repository=graph_repo)
    task_manager = TaskManager(event_bus, repository=task_repo, graph_repository=graph_repo)
    mem_store = MemoryStore(event_bus, repository=mem_repo)
    worktree_mgr = GitWorktreeManager(repo_root=demo_dir)
    ver_engine = VerificationEngine(
        event_bus=event_bus,
        repository=ver_repo,
        task_manager=task_manager,
        worktree_manager=worktree_mgr,
        memory_store=mem_store,
        graph_repository=graph_repo,
    )

    # Setup sample code repository
    src_dir = demo_dir / "src"
    tests_dir = demo_dir / "tests"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    # Initial naive parser failing on BOM byte
    (src_dir / "parser.py").write_text(
        "import csv\nimport io\n\ndef parse_csv_data(raw_content: str):\n"
        "    reader = csv.DictReader(io.StringIO(raw_content))\n"
        "    return [row for row in reader]\n",
        encoding="utf-8"
    )

    # Regression test verifying UTF-8 BOM handling
    (tests_dir / "test_parser.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n"
        "from src.parser import parse_csv_data\n\n"
        "def test_bom():\n"
        '    rows = parse_csv_data("\\ufeffuser_id,name\\nu1,Alice")\n'
        '    assert "user_id" in rows[0], f"Found keys: {list(rows[0].keys())}"\n',
        encoding="utf-8"
    )

    # --- STEP 1: Submit Mission & Approve Plan ---
    print("\n[STEP 1] Submitting Mission & Recording Structured Plan in FalkorDB...")
    mission = await mission_manager.create_mission(
        title="UTF-8 BOM CSV Parser Hardening",
        goal="Handle UTF-8 BOM prefix without failing parser assertions",
        repository_path=str(demo_dir),
        status=MissionStatus.AWAITING_APPROVAL
    )
    print(f"Mission Created: id={mission.id}, status={mission.status.value}")

    # Plan approval gate enforcement
    print("Enforcing plan approval gate: Mission is AWAITING_APPROVAL...")
    await mission_manager.update_status(mission.id, MissionStatus.RUNNING, reason="Plan approved by operator")
    print("Plan approved -> Mission status: RUNNING")

    # Initialize Task DAG in FalkorDB
    task_id = f"{mission.id}_task_01"
    tasks = [
        {
            "id": task_id,
            "title": "Fix UTF-8 BOM CSV parsing",
            "order": 1,
            "status": "PENDING",
            "dependencies": [],
            "expected_files": ["src/parser.py"]
        }
    ]
    await graph_repo.save_task_dag(mission.id, tasks)
    await graph_repo.register_agent("worker_01", "WORKER", "nemotron", "Autonomous Worker")
    print(f"Task DAG stored in FalkorDB: Task {task_id} CONTAINS_TASK Mission {mission.id}")

    # --- STEP 2: Query FalkorDB Task Context Before Dispatch ---
    print("\n[STEP 2] Querying FalkorDB Context Before Task Dispatch...")
    ctx_before = await graph_repo.get_task_graph_context(mission.id, task_id)
    print(f"Graph Dispatch Package: prior_attempts={ctx_before['total_attempts']}, dependencies_met={ctx_before['dependencies_met']}")

    # --- STEP 3: Execution Attempt 1 - Controlled Failure ---
    print("\n[STEP 3] Dispatching Execution Attempt 1 (Testing naive codebase)...")
    exec1_id = f"exec_{task_id}_1"
    await graph_repo.record_execution_start(exec1_id, task_id, mission.id, "worker_01", attempt_number=1)

    # Simulate test run failure
    evt1_id = f"evt_{uuid.uuid4().hex[:8]}"
    err_sig = "AssertionError: Found keys: ['\\ufeffuser_id', 'name']"
    await graph_repo.record_execution_event(
        exec1_id,
        evt1_id,
        event_type="TEST_EXECUTION_FAILED",
        severity="WARNING",
        payload={"command": "pytest tests/test_parser.py", "error": err_sig}
    )
    await graph_repo.record_execution_failure(exec1_id, error_signature="AssertionError: UTF-8 BOM", reason=err_sig, event_id=evt1_id)
    print(f"Execution Attempt 1 FAILED -> Linked in FalkorDB: ({exec1_id})-[:FAILS_WITH]->({evt1_id})")

    # --- STEP 4: Cypher Traversal of Prior Failures ---
    print("\n[STEP 4] Traversing FalkorDB Graph for Prior Failure History...")
    fail_history = await graph_repo.get_prior_failure_history(mission.id, task_id=task_id)
    print(f"Retrieved {len(fail_history)} causal failure record(s) from FalkorDB:")
    for f in fail_history:
        print(f"  Attempt {f['attempt_number']}: signature='{f['error_signature']}', event={f['event_id']}")

    # --- STEP 5: Supervisory Recovery Decision Informed by Graph ---
    print("\n[STEP 5] Recording Supervisory Decision in FalkorDB Property Graph...")
    dec_id = f"dec_{task_id}_1"
    dec_action = "INTERVENE_AND_PATCH"
    dec_reason = "Strip UTF-8 BOM byte prefix (\\ufeff) before passing buffer to csv.DictReader"
    await graph_repo.record_decision(
        decision_id=dec_id,
        mission_id=mission.id,
        task_id=task_id,
        decision_type="SUPERVISORY_RECOVERY",
        action=dec_action,
        reason=dec_reason,
        responding_to_event_id=evt1_id,
        selected_agent_id="worker_01",
    )
    print(f"Decision recorded: ({dec_id})-[:RESPONDS_TO]->({evt1_id}), ({dec_id})-[:SELECTS]->(worker_01)")

    # --- STEP 6: Execution Attempt 2 - Repair, Test Pass, & Verification ---
    print("\n[STEP 6] Executing Attempt 2 (Applying patch informed by decision)...")
    exec2_id = f"exec_{task_id}_2"
    await graph_repo.record_execution_start(exec2_id, task_id, mission.id, "worker_01", attempt_number=2)

    # Apply repair to parser.py
    repaired_code = (
        "import csv\nimport io\n\ndef parse_csv_data(raw_content: str):\n"
        '    cleaned = raw_content.lstrip("\\ufeff")\n'
        "    reader = csv.DictReader(io.StringIO(cleaned))\n"
        "    return [row for row in reader]\n"
    )
    (src_dir / "parser.py").write_text(repaired_code, encoding="utf-8")
    print("Repaired parser.py with BOM strip logic.")

    # Record execution success
    await graph_repo.record_execution_success(exec2_id, summary="Parser fixed and test suite passing", artifacts=[{"path": "src/parser.py"}])
    print(f"Execution Attempt 2 SUCCEEDED -> ({exec2_id})-[:PRODUCES]->(Artifact)")

    # Independent Verification
    print("Running Independent Verification Engine...")
    v_context = VerificationContext(
        mission_id=mission.id,
        task_id=task_id,
        agent_id="worker_01",
        workspace=str(demo_dir),
        allowed_files=["src/parser.py", "tests/test_parser.py"],
        expected_files=["src/parser.py"],
        verification_requirements=["python -m pytest tests/test_parser.py -v"],
        completion_claim={"summary": "BOM handled cleanly"}
    )
    v_result = await ver_engine.verify(v_context)
    print(f"Independent Verification Decision: {v_result.decision.value}")
    assert v_result.decision == VerificationDecision.ACCEPT

    await mission_manager.complete_mission(mission.id, summary="Mission completed with independent verification.")

    # --- STEP 7: Simulate Application Restart ---
    print("\n[STEP 7] Simulating Application Restart (Tearing down in-memory state)...")
    del mission_manager
    del task_manager
    del ver_engine
    del graph_repo
    del falkor_client

    # --- STEP 8: Post-Restart Verification against FalkorDB ---
    print("\n[STEP 8] Querying FalkorDB Property Graph After Application Restart...")
    restart_client = FalkorDBClient(config=falkor_cfg)
    restart_repo = FalkorDBGraphRepository(restart_client)

    # 8.1 Verify Task Context & Distinct Attempts
    post_ctx = await restart_repo.get_task_graph_context(mission.id, task_id)
    print(f"Post-Restart Task Context: Total Attempts={post_ctx['total_attempts']}")
    assert post_ctx["total_attempts"] == 2
    attempts_map = {e["attempt_number"]: e["status"] for e in post_ctx["prior_executions"]}
    print(f"  Attempt 1: {attempts_map.get(1)} (Failed attempt preserved)")
    print(f"  Attempt 2: {attempts_map.get(2)} (Successful retry preserved)")
    assert attempts_map.get(1) == "FAILED"
    assert attempts_map.get(2) == "COMPLETED"

    # 8.2 Verify Decision Lineage
    lineage = await restart_repo.get_decision_lineage(mission.id)
    print(f"\nDecision Lineage Path:")
    for d in lineage:
        print(f"  Decision '{d['decision_id']}': action='{d['action']}'")
        if d['causal_event']:
            print(f"    --> RESPONDS_TO Event '{d['causal_event']['id']}' ({d['causal_event']['event_type']})")
        if d['selected_agent']:
            print(f"    --> SELECTS Agent '{d['selected_agent']['id']}'")
    assert len(lineage) >= 1

    # 8.3 Verify Verification Traceability to Evidence
    trace = await restart_repo.get_verification_trace(task_id)
    print(f"\nVerification Evidence Trace:")
    print(f"  Verification ID: {trace['verification_id']} | Decision: {trace['decision']}")
    for ev in trace.get("evidence", []):
        print(f"    --> SUPPORTED_BY Evidence ({ev.get('type')}): {ev.get('description')} (passed={ev.get('passed')})")
    assert trace["verified"] is True
    assert trace["decision"] == "ACCEPT"

    # 8.4 Verify Mission Subgraph
    subgraph = await restart_repo.get_mission_subgraph(mission.id)
    print(f"\nFull Mission Subgraph Summary: {subgraph['nodes_count']} nodes, {subgraph['edges_count']} relationships")

    # Cleanup demo graph and temp directory
    try:
        restart_client.get_graph().delete()
        shutil.rmtree(demo_dir, ignore_errors=True)
    except Exception:
        pass

    print("\n" + "=" * 80)
    print("END-TO-END DEMO SUCCEEDED WITH 100% PERSISTENCE AND GRAPH TRACEABILITY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_demo())
