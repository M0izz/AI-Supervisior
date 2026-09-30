import asyncio
import os
import shutil
import pytest
from pathlib import Path
from agents.planner.agent import PlannerAgent
from agents.worker.agent import WorkerAgent
from agents.worker.models import WorkerAction, WorkerState
from agents.reviewer.agent import ReviewerAgent
from agents.verifier.agent import VerifierAgent
from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus
from core.tasks.manager import TaskManager
from core.tasks.models import Task, TaskStatus
from core.policies.models import PolicyConfig
from core.state.models import AgentContextPackage
from supervisor.engine import SupervisorEngine
from supervisor.decisions import SupervisorAction
from supervisor.state_machine import SupervisorState
from supervisor.reasoning import SupervisoryReasoner
from integrations.nebius.provider import MockReasoningProvider
from memory.store import MemoryStore
from memory.provenance import FactStatus
from memory.retrieval import ContextPackager
from tools import get_default_tools


@pytest.fixture
def sandbox_repo(tmp_path):
    repo = tmp_path / "sample-project"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "tests").mkdir()

    # Initial naive parser that fails on BOM
    (repo / "src" / "parser.py").write_text(
        'import csv\nimport io\n\ndef parse_csv_data(raw_content: str):\n'
        '    reader = csv.DictReader(io.StringIO(raw_content))\n'
        '    return [row for row in reader]\n',
        encoding="utf-8"
    )
    (repo / "src" / "validator.py").write_text(
        'def validate_user_row(row):\n'
        '    return "user_id" in row, []\n',
        encoding="utf-8"
    )
    (repo / "tests" / "test_parser.py").write_text(
        'import sys\nfrom pathlib import Path\n'
        'sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n'
        'from src.parser import parse_csv_data\n'
        'from src.validator import validate_user_row\n\n'
        'def test_standard():\n'
        '    assert len(parse_csv_data("user_id,name\\nu1,Alice")) == 1\n\n'
        'def test_bom():\n'
        '    rows = parse_csv_data("\\ufeffuser_id,name\\nu2,Bob")\n'
        '    assert "user_id" in rows[0], f"Found keys: {list(rows[0].keys())}"\n',
        encoding="utf-8"
    )
    return repo


@pytest.mark.asyncio
async def test_live_worker_supervisor_recovery(sandbox_repo):
    """
    Genuine end-to-end integration test:
    Worker fails on real tests -> Supervisor detects loop -> Worker pauses ->
    Reviewer diagnoses -> Memory records -> Worker resumes with recovery context ->
    Worker fixes real file -> Tests pass -> Verifier confirms -> Mission completes.
    """
    event_bus = EventBus()
    mission_mgr = MissionManager(event_bus)
    task_mgr = TaskManager(event_bus)
    mem_store = MemoryStore(event_bus)
    packager = ContextPackager(mem_store, event_bus)
    policy = PolicyConfig(pause_after_repeated_failures=3)

    supervisor = SupervisorEngine(
        event_bus=event_bus,
        mission_manager=mission_mgr,
        task_manager=task_mgr,
        policy=policy,
        reasoner=SupervisoryReasoner(provider=MockReasoningProvider())
    )

    tools = get_default_tools(sandbox_repo)
    worker = WorkerAgent(agent_id="worker_01", event_bus=event_bus, tools=tools)
    supervisor.register_worker(worker)

    # 1. Mission Creation
    mission = await mission_mgr.create_mission(
        title="Add CSV Import Validation",
        goal="Parse and validate CSV files with UTF-8 support without altering DB schema",
        repository_path=str(sandbox_repo)
    )
    await mission_mgr.update_status(mission.id, MissionStatus.RUNNING)

    # 2. Planner Creates Tasks
    planner = PlannerAgent(agent_id="planner_01", event_bus=event_bus)
    plan = await planner.run(
        AgentContextPackage(mission_id=mission.id, objective=mission.goal, task={"title": "Plan"})
    )
    graph = await task_mgr.initialize_mission_tasks(mission.id, plan["tasks"])

    task_3 = graph.get_task("TASK-003")
    await task_mgr.start_task(mission.id, task_3.id, worker.agent_id)

    # 3. Worker fails on real tests
    # First attempt: run tests on naive parser
    t_res1 = await worker.call_tool("run_tests", {"test_command": "python -m pytest tests/test_parser.py -v"}, mission_id=mission.id, task_id=task_3.id)
    assert t_res1.success is False
    assert t_res1.metadata.get("failed") == 1
    await task_mgr.fail_task(mission.id, task_3.id, error_signature=t_res1.metadata.get("error_signature"))

    # Second attempt
    t_res2 = await worker.call_tool("run_tests", {"test_command": "python -m pytest tests/test_parser.py -v"}, mission_id=mission.id, task_id=task_3.id)
    await task_mgr.fail_task(mission.id, task_3.id, error_signature=t_res2.metadata.get("error_signature"))

    # Third attempt -> triggers LOOP_DETECTED in Supervisor
    t_res3 = await worker.call_tool("run_tests", {"test_command": "python -m pytest tests/test_parser.py -v"}, mission_id=mission.id, task_id=task_3.id)
    await task_mgr.fail_task(mission.id, task_3.id, error_signature=t_res3.metadata.get("error_signature"))

    # 4. Supervisor Detects Loop and Pauses Worker
    assert worker.state == WorkerState.PAUSED
    assert supervisor.state_machine.current_state == SupervisorState.INVESTIGATING

    # 5. Reviewer Diagnoses
    reviewer = ReviewerAgent(agent_id="reviewer_01", event_bus=event_bus, tools=tools)
    diagnosis = await reviewer.run(
        AgentContextPackage(
            mission_id=mission.id,
            objective=mission.goal,
            task=task_3.model_dump(),
            recent_events=[{"error_signature": t_res3.metadata.get("error_signature")}]
        )
    )
    assert "BOM" in diagnosis.recommended_strategy

    # 6. Memory Records Diagnosis with Provenance
    fact_rec = await mem_store.add_record(
        mission_id=mission.id,
        fact=diagnosis.recommended_strategy,
        source="reviewer_01",
        created_by="reviewer_01",
        status=FactStatus.VERIFIED,
        confidence=diagnosis.confidence
    )
    rej_rec = await mem_store.add_record(
        mission_id=mission.id,
        fact=diagnosis.rejected_approach or "Direct comparison",
        source="reviewer_01",
        created_by="reviewer_01",
        status=FactStatus.REJECTED,
        category="rejected_approach"
    )
    supervisor.register_rejected_approach(mission.id, rej_rec.fact)

    # 7. Recovery Context Created & Worker Resumed
    recovery_pkg = await packager.build_recovery_package(
        mission_id=mission.id,
        goal=mission.goal,
        task=task_3,
        constraints=["Do not modify database schema"],
        diagnosis=diagnosis.model_dump()
    )
    worker.resume(recovery_context=recovery_pkg)
    assert worker.state == WorkerState.RECOVERING

    # 8. Worker Fixes Real File via edit_file tool
    edit_res = await worker.call_tool(
        "edit_file",
        {
            "path": "src/parser.py",
            "target_content": "    reader = csv.DictReader(io.StringIO(raw_content))",
            "replacement_content": '    cleaned = raw_content.lstrip("\\ufeff")\n    reader = csv.DictReader(io.StringIO(cleaned))'
        },
        mission_id=mission.id,
        task_id=task_3.id
    )
    assert edit_res.success is True

    # 9. Real tests now pass
    t_pass = await worker.call_tool("run_tests", {"test_command": "python -m pytest tests/test_parser.py -v"}, mission_id=mission.id, task_id=task_3.id)
    assert t_pass.success is True
    assert t_pass.metadata.get("failed") == 0
    assert t_pass.metadata.get("passed") == 2

    # Worker reports execution complete (does NOT claim verified)
    await task_mgr.complete_task(mission.id, task_3.id, summary="Parser updated with UTF-8 BOM stripping.")

    # 10. Independent Verifier Validates
    verifier = VerifierAgent(agent_id="verifier_01", event_bus=event_bus, tools=tools)
    ver_res = await verifier.run(recovery_pkg)
    assert ver_res["verified"] is True
    assert ver_res["tests_failed"] == 0

    # 11. Supervisor Verifies & Completes Mission
    await mission_mgr.complete_mission(mission.id, summary="Verified 100% tests passed by Verifier.")
    final_mission = await mission_mgr.get_mission(mission.id)
    assert final_mission.status == MissionStatus.COMPLETED
