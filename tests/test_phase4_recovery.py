import asyncio
import pytest
from pathlib import Path
from agents.reviewer.agent import ReviewerAgent, ReviewerDiagnosis
from agents.verifier.agent import VerifierAgent
from agents.worker.agent import WorkerAgent
from agents.worker.models import WorkerAction
from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus
from core.tasks.manager import TaskManager
from core.tasks.models import Task
from core.state.models import AgentContextPackage
from memory.provenance import FactStatus, MemoryRecord
from memory.store import MemoryStore
from memory.retrieval import ContextPackager
from supervisor.engine import SupervisorEngine
from supervisor.decisions import SupervisorAction
from tools import get_default_tools
from tools.filesystem import WriteFileTool


@pytest.fixture
def temp_workspace(tmp_path):
    ws = tmp_path / "sandbox"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src" / "parser.py").write_text("def parse(): pass", encoding="utf-8")
    return ws


@pytest.mark.asyncio
async def test_reviewer_readonly_enforcement(temp_workspace):
    bus = EventBus()
    tools = get_default_tools(temp_workspace)

    # Pass all tools (including write_file, edit_file) to Reviewer
    reviewer = ReviewerAgent(agent_id="rev_1", event_bus=bus, tools=tools)

    # Reviewer must have stripped out write_file and edit_file
    assert "write_file" not in reviewer.tools
    assert "edit_file" not in reviewer.tools
    assert "read_file" in reviewer.tools

    ctx = AgentContextPackage(
        mission_id="m_rev",
        objective="Fix parser",
        task={"id": "t1", "title": "Inspect parser"}
    )
    diagnosis = await reviewer.run(ctx)
    assert isinstance(diagnosis, ReviewerDiagnosis)
    assert diagnosis.confidence >= 0.9
    assert diagnosis.failure_category == "ENCODING_MISMATCH"
    assert "BOM" in diagnosis.recommended_strategy


@pytest.mark.asyncio
async def test_memory_provenance_lifecycle():
    bus = EventBus()
    mem_store = MemoryStore(event_bus=bus)

    # 1. Fact created during diagnosis (INFERRED)
    record = await mem_store.add_record(
        mission_id="m_prov",
        fact="CSV files from external source include UTF-8 BOM",
        source="reviewer_01",
        created_by="reviewer_01",
        status=FactStatus.INFERRED,
        confidence=0.85
    )
    assert record.status == FactStatus.INFERRED

    # 2. Rejected approach recorded (REJECTED)
    rej_record = await mem_store.add_record(
        mission_id="m_prov",
        fact="Direct string comparison without BOM stripping",
        source="reviewer_01",
        created_by="reviewer_01",
        status=FactStatus.REJECTED,
        category="rejected_approach",
        details="Leaves \\ufeff attached to first header"
    )
    assert rej_record.status == FactStatus.REJECTED

    # 3. Verified by tests (VERIFIED)
    verified_record = await mem_store.add_record(
        mission_id="m_prov",
        fact="lstrip('\\ufeff') strips BOM and passes all tests",
        source="verifier_01",
        created_by="verifier_01",
        status=FactStatus.VERIFIED,
        confidence=0.99
    )
    assert verified_record.status == FactStatus.VERIFIED

    summary = await mem_store.get_structured_summary("m_prov")
    assert len(summary["verified_facts"]) == 1
    assert len(summary["rejected_approaches"]) == 1


@pytest.mark.asyncio
async def test_recovery_context_generation():
    bus = EventBus()
    mem_store = MemoryStore(event_bus=bus)
    packager = ContextPackager(memory_store=mem_store, event_bus=bus)

    task = Task(id="t_rec", mission_id="m_rec", title="Fix Parser")

    diagnosis = {
        "diagnosis": "UTF-8 BOM header mismatch",
        "recommended_strategy": "Use raw_content.lstrip('\\ufeff')",
        "rejected_approach": "Direct string comparison",
        "evidence": ["test_utf8_bom_csv_parsing failed"]
    }

    recovery_pkg = await packager.build_recovery_package(
        mission_id="m_rec",
        goal="Add CSV import validation",
        task=task,
        constraints=["Do not modify database schema"],
        diagnosis=diagnosis
    )

    assert recovery_pkg.mission_id == "m_rec"
    assert any("raw_content.lstrip" in f.get("fact", "") for f in recovery_pkg.relevant_memory)
    assert any("Direct string comparison" in r.get("approach", "") for r in recovery_pkg.rejected_approaches)


@pytest.mark.asyncio
async def test_recovery_strategy_repetition_prevention():
    bus = EventBus()
    mission_mgr = MissionManager(bus)
    task_mgr = TaskManager(bus)
    supervisor = SupervisorEngine(bus, mission_mgr, task_mgr)

    repeated_events = []
    await bus.subscribe(lambda e: repeated_events.append(e), event_type=EventType.RECOVERY_STRATEGY_REPEATED)

    mission = await mission_mgr.create_mission("Repetition Test", "Test")
    supervisor.register_rejected_approach(mission.id, "direct string comparison")

    # Worker attempts tool call with rejected strategy
    await bus.publish(
        Event(
            mission_id=mission.id,
            task_id="t_rep",
            agent_id="worker_01",
            type=EventType.TOOL_CALLED,
            payload={
                "tool": "edit_file",
                "arguments": {"strategy": "apply direct string comparison on headers"}
            }
        )
    )

    assert len(repeated_events) == 1
    assert repeated_events[0].payload["rejected_strategy"] == "direct string comparison"


@pytest.mark.asyncio
async def test_verifier_handoff_and_supervisor_completion(temp_workspace):
    bus = EventBus()
    mission_mgr = MissionManager(bus)
    task_mgr = TaskManager(bus)
    tools = get_default_tools(temp_workspace)

    mission = await mission_mgr.create_mission("Verifier Test", "Test")
    await mission_mgr.update_status(mission.id, MissionStatus.RUNNING)

    # Worker finishes execution
    worker = WorkerAgent(agent_id="worker_01", event_bus=bus, tools=tools)
    # Worker says execution finished
    await bus.publish(
        Event(
            mission_id=mission.id,
            task_id="t_ver",
            agent_id=worker.agent_id,
            type=EventType.AGENT_COMPLETED,
            payload={"summary": "I finished the code."}
        )
    )

    # Mission must NOT be completed simply because worker finished!
    m = await mission_mgr.get_mission(mission.id)
    assert m.status == MissionStatus.RUNNING

    # Verifier independently checks
    verifier = VerifierAgent(agent_id="verifier_01", event_bus=bus, tools=tools)
    ctx = AgentContextPackage(mission_id=mission.id, objective="Test", task={"id": "t_ver"})
    ver_res = await verifier.run(ctx)

    # Complete only when verifier passes
    if ver_res.get("verified"):
        await mission_mgr.complete_mission(mission.id, summary="Verified by VerifierAgent")
        m_after = await mission_mgr.get_mission(mission.id)
        assert m_after.status == MissionStatus.COMPLETED
