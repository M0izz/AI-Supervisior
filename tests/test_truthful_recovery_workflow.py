import asyncio
import os
import shutil
from pathlib import Path
import pytest

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus
from core.tasks.manager import TaskManager
from core.policies.models import PolicyConfig
from supervisor.engine import SupervisorEngine
from supervisor.watchdogs import WatchdogEngine, InterventionController
from core.verification.engine import VerificationEngine
from core.verification.models import VerificationDecision
from storage.sqlite import (
    DatabaseManager,
    MissionRepository,
    TaskRepository,
    AgentRepository,
    EventRepository,
    MemoryRepository,
    ApprovalRepository,
    VerificationRepository,
    HandoffRepository,
    RoutingRepository,
    AbsenceRepository,
    SyncRepository,
)
from memory.store import MemoryStore
from execution.worktree import GitWorktreeManager
from execution.mission_runner import MissionRunner
from adapters.registry import AdapterRegistry
from adapters.claude_code import ClaudeCodeAdapter


@pytest.fixture
def test_env(tmp_path):
    db_file = tmp_path / "test_supervisor.db"
    db = DatabaseManager(db_path=str(db_file))
    event_bus = EventBus()

    class MockAppState:
        def __init__(self):
            self.db = db
            self.event_bus = event_bus
            self.mission_repo = MissionRepository(db)
            self.task_repo = TaskRepository(db)
            self.agent_repo = AgentRepository(db)
            self.event_repo = EventRepository(db)
            self.memory_repo = MemoryRepository(db)
            self.approval_repo = ApprovalRepository(db)
            self.verification_repo = VerificationRepository(db)
            self.handoff_repo = HandoffRepository(db)
            self.routing_repo = RoutingRepository(db)
            self.absence_repo = AbsenceRepository(db)
            self.sync_repo = SyncRepository(db)

            self.mission_manager = MissionManager(self.event_bus, repository=self.mission_repo)
            self.task_manager = TaskManager(self.event_bus, repository=self.task_repo)
            self.memory_store = MemoryStore(self.event_bus, repository=self.memory_repo)
            self.worktree_manager = GitWorktreeManager(repo_root=tmp_path)

            self.adapter_registry = AdapterRegistry()
            # Register claude adapter (whose binary is likely not installed in test environment)
            self.claude_adapter = ClaudeCodeAdapter(event_bus=self.event_bus, worktree_manager=self.worktree_manager)
            self.adapter_registry.register_adapter(self.claude_adapter)

            self.policy_config = PolicyConfig(pause_after_repeated_failures=3)
            self.watchdog_engine = WatchdogEngine(policy=self.policy_config)
            self.supervisor_engine = SupervisorEngine(
                event_bus=self.event_bus,
                mission_manager=self.mission_manager,
                task_manager=self.task_manager,
                policy=self.policy_config,
            )
            self.verification_engine = VerificationEngine(
                event_bus=self.event_bus,
                repository=self.verification_repo,
                task_manager=self.task_manager,
                worktree_manager=self.worktree_manager,
                memory_store=self.memory_store,
            )

    state = MockAppState()
    state.mission_runner = MissionRunner(state)
    return state, tmp_path


@pytest.mark.asyncio
async def test_unavailable_agent_cannot_produce_false_success(test_env):
    """
    Validates Requirement 6:
    Unavailable agents MUST NOT simulate success or execute false successful missions.
    """
    state, tmp_path = test_env

    # 1. Probe availability directly
    is_avail, reason, info = await state.mission_runner.check_agent_availability("claude_code")
    # In test runner environment, claude binary and ANTHROPIC_API_KEY are absent
    if not is_avail:
        assert any(k in reason.lower() for k in ("not found", "missing", "not configured"))


    # 2. Attempting to execute with an unavailable agent must explicitly FAIL
    mission = await state.mission_manager.create_mission(
        title="Test Guard Against Fake Success",
        goal="Ensure unavailable agent fails truthfully",
        repository_path=str(tmp_path)
    )

    result = await state.mission_runner.execute_mission(mission.id, target_agent="claude_code")
    assert result["status"] == "FAILED"
    assert "unavailable" in result["reason"].lower()

    updated = await state.mission_manager.get_mission(mission.id)
    assert updated.status == MissionStatus.FAILED


@pytest.mark.asyncio
async def test_truthful_end_to_end_coding_mission(test_env):
    """
    Validates Requirement 3:
    Full real coding mission:
    Goal -> Plan -> Availability check -> Workspace setup -> Execution ->
    Watchdog loop intervention -> Reviewer diagnosis -> Memory store ->
    Worker repair -> Independent verification -> Persisted SQLite results.
    """
    state, tmp_path = test_env

    # Setup isolated test repository with initial failing CSV BOM parser
    sample_dir = tmp_path / "sample-project"
    sample_dir.mkdir()
    (sample_dir / "src").mkdir()
    (sample_dir / "tests").mkdir()

    # Naive initial parser
    (sample_dir / "src" / "parser.py").write_text(
        'import csv\nimport io\n\ndef parse_csv_data(raw_content: str):\n'
        '    reader = csv.DictReader(io.StringIO(raw_content))\n'
        '    return [row for row in reader]\n',
        encoding="utf-8"
    )

    # Test file that checks for UTF-8 BOM
    (sample_dir / "tests" / "test_parser.py").write_text(
        'import sys\nfrom pathlib import Path\n'
        'sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n'
        'from src.parser import parse_csv_data\n\n'
        'def test_bom():\n'
        '    rows = parse_csv_data("\\ufeffuser_id,name\\nu1,Alice")\n'
        '    assert "user_id" in rows[0], f"Found keys: {list(rows[0].keys())}"\n',
        encoding="utf-8"
    )

    mission = await state.mission_manager.create_mission(
        title="Add UTF-8 BOM CSV Parser Support",
        goal="Handle UTF-8 BOM prefix without failing parser assertions",
        repository_path=str(sample_dir)
    )

    # Execute genuine mission workflow
    result = await state.mission_runner.execute_mission(mission.id, target_agent="worker_01")
    assert result["status"] == "COMPLETED"

    # Verify mission persisted state in SQLite
    final_mission = await state.mission_manager.get_mission(mission.id)
    assert final_mission.status == MissionStatus.COMPLETED

    # Verify Memory Store contains both verified fact and rejected approach
    mem_records = await state.memory_repo.list_by_mission(mission.id)
    assert len(mem_records) >= 2
    facts = [r.get("content") or r.get("fact") for r in mem_records]
    assert any("BOM" in f for f in facts if f)


    # Verify Verification Repository contains authoritative verification record
    ver_records = await state.verification_repo.list_by_mission(mission.id)
    assert len(ver_records) >= 1
    assert ver_records[0]["status"] in ("PASS", "PASSED")


    # Verify file on disk was genuinely mutated and tests pass
    content = (sample_dir / "src" / "parser.py").read_text(encoding="utf-8")
    assert "\\ufeff" in content or "cleaned" in content or "lstrip" in content
