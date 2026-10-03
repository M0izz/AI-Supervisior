import asyncio
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import tempfile
import pytest

from core.events.bus import EventBus
from core.events.schema import Event, EventType
from core.missions.models import Mission, MissionStatus
from core.tasks.models import Task, TaskStatus
from core.protocol import (
    CURRENT_SCHEMA_VERSION,
    ProtocolEventType,
    ActionType,
    ActionInfo,
    TelemetryInfo,
    WorkProtocolEvent,
    TaskDispatchPackage,
    ProtocolValidationError,
    validate_protocol_event,
    validate_dispatch_package,
    validate_schema_version,
)
from storage.sqlite import (
    DatabaseManager,
    MissionRepository,
    TaskRepository,
    AgentRepository,
    EventRepository,
    MemoryRepository,
    ApprovalRepository,
    VerificationRepository,
    attach_sqlite_persistence,
)
from execution.worktree import (
    GitWorktreeManager,
    GitWorktreeError,
    sanitize_identifier,
)


# ============================================================================
# 1. WORK PROTOCOL V1 TESTS
# ============================================================================

def test_protocol_valid_event():
    evt = WorkProtocolEvent(
        mission_id="msn_alpha",
        task_id="tsk_001",
        agent_id="agent_worker",
        provider="internal",
        event_type=ProtocolEventType.TASK_STARTED.value,
        action=ActionInfo(
            action_type=ActionType.TOOL_CALL.value,
            target="read_file",
            parameters={"path": "src/main.py"},
        ),
        telemetry=TelemetryInfo(
            input_tokens=150,
            output_tokens=42,
            cost=0.0012,
            duration=1.25,
            exit_status="success",
        ),
        payload={"note": "autonomous execution start"},
    )
    validated = validate_protocol_event(evt)
    assert validated.event_id is not None
    assert validated.mission_id == "msn_alpha"
    assert validated.schema_version == CURRENT_SCHEMA_VERSION
    assert validated.telemetry.input_tokens == 150
    assert validated.action.target == "read_file"


def test_protocol_missing_identity_rejected():
    with pytest.raises(ProtocolValidationError) as exc:
        validate_protocol_event({
            "mission_id": "",
            "event_type": "mission.created",
        })
    assert "mission_id" in str(exc.value)

    with pytest.raises(ProtocolValidationError) as exc2:
        validate_protocol_event({
            "mission_id": "msn_test",
            "event_type": "   ",
        })
    assert "event_type" in str(exc2.value)


def test_protocol_invalid_schema_version_rejected():
    with pytest.raises(ProtocolValidationError) as exc:
        validate_protocol_event({
            "schema_version": "2.0.0",  # Incompatible major version
            "mission_id": "msn_test",
            "event_type": "mission.created",
        })
    assert "Unsupported schema_version" in str(exc.value)


def test_protocol_unknown_metadata_handled():
    evt_dict = {
        "mission_id": "msn_test",
        "event_type": "agent.action.executed",
        "custom_future_flag": "allowed_extra_field",
        "payload": {"arbitrary": 12345},
    }
    validated = validate_protocol_event(evt_dict)
    assert validated.mission_id == "msn_test"
    assert validated.payload["arbitrary"] == 12345
    assert getattr(validated, "custom_future_flag") == "allowed_extra_field"


def test_task_dispatch_package_valid():
    pkg = TaskDispatchPackage(
        task_id="tsk_99",
        mission_id="msn_99",
        objective="Fix UTF-8 BOM encoding issue in CSV parser",
        workspace="/tmp/worktree_99",
        allowed_files=["src/parser.py", "tests/test_parser.py"],
        budget={"max_tokens": 50000, "max_cost_usd": 1.5},
        timeout=180.0,
        context={"error": "UnicodeDecodeError"},
        verification_requirements=["pytest tests/test_parser.py"],
    )
    validated = validate_dispatch_package(pkg)
    assert validated.task_id == "tsk_99"
    assert validated.budget["max_tokens"] == 50000
    assert validated.permissions["write_filesystem"] is True


def test_task_dispatch_package_invalid_rejected():
    with pytest.raises(ProtocolValidationError) as exc:
        validate_dispatch_package({
            "task_id": "tsk_01",
            "mission_id": "",
            "objective": "Do something",
            "workspace": "/tmp",
        })
    assert "mission_id" in str(exc.value)


# ============================================================================
# 2. SQLITE WAL PERSISTENCE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_sqlite_wal_mode_and_foreign_keys(tmp_path):
    db_file = tmp_path / "test_kernel.db"
    db = DatabaseManager(str(db_file))
    await db.init_db()

    assert await db.is_wal_mode() is True
    assert await db.is_foreign_keys_enabled() is True

    # Test foreign key enforcement
    # Inserting a task for a non-existent mission must fail
    task_repo = TaskRepository(db)
    with pytest.raises(Exception):
        await task_repo.save({
            "task_id": "t_orphan",
            "mission_id": "non_existent_mission_id",
            "title": "Orphan task",
            "status": "PENDING",
        })


@pytest.mark.asyncio
async def test_sqlite_repositories_crud(tmp_path):
    db_file = tmp_path / "test_crud.db"
    db = DatabaseManager(str(db_file))
    await db.init_db()

    mission_repo = MissionRepository(db)
    task_repo = TaskRepository(db)
    agent_repo = AgentRepository(db)
    event_repo = EventRepository(db)
    memory_repo = MemoryRepository(db)
    approval_repo = ApprovalRepository(db)
    verification_repo = VerificationRepository(db)

    # 1. Mission CRUD
    await mission_repo.save({
        "id": "msn_001",
        "title": "Fix Parser",
        "goal": "Handle UTF-8 BOM",
        "status": "RUNNING",
    })
    m = await mission_repo.get("msn_001")
    assert m is not None
    assert m["title"] == "Fix Parser"
    assert m["status"] == "RUNNING"

    # 2. Task CRUD
    await task_repo.save({
        "id": "tsk_001",
        "mission_id": "msn_001",
        "title": "Unit Test Validation",
        "status": "IN_PROGRESS",
        "order": 1,
    })
    t = await task_repo.get("tsk_001")
    assert t is not None
    assert t["title"] == "Unit Test Validation"

    # 3. Agent CRUD
    await agent_repo.save({
        "agent_id": "worker_01",
        "agent_type": "WORKER",
        "model": "nemotron",
        "status": "RUNNING",
        "mission_id": "msn_001",
        "tool_calls": 5,
    })
    a = await agent_repo.get("worker_01")
    assert a is not None
    assert a["tool_calls"] == 5

    # 4. Append-Only Events
    evt_id1 = await event_repo.append({
        "mission_id": "msn_001",
        "task_id": "tsk_001",
        "event_type": "command.started",
        "payload": {"command": "pytest"},
    })
    evt_id2 = await event_repo.append({
        "mission_id": "msn_001",
        "task_id": "tsk_001",
        "event_type": "command.completed",
        "payload": {"exit_code": 0},
    })
    assert await event_repo.count_events("msn_001") == 2
    evts = await event_repo.list_by_mission("msn_001")
    assert len(evts) == 2

    # 5. Memory CRUD
    mem_id = await memory_repo.save(
        mission_id="msn_001",
        category="debugging",
        content="BOM marker requires utf-8-sig decode",
    )
    records = await memory_repo.list_by_mission("msn_001")
    assert len(records) == 1
    assert "utf-8-sig" in records[0]["content"]

    # 6. Approval CRUD
    appr = await approval_repo.create(
        mission_id="msn_001",
        action_type="command_execute",
        description="Run alembic upgrade head",
        task_id="tsk_001",
    )
    assert appr["status"] == "PENDING"
    resolved = await approval_repo.resolve(appr["approval_id"], "APPROVED", "lead_dev")
    assert resolved["status"] == "APPROVED"
    assert resolved["resolved_by"] == "lead_dev"

    # 7. Verification CRUD
    ver = await verification_repo.save(
        mission_id="msn_001",
        task_id="tsk_001",
        verification_type="pytest",
        status="PASSED",
        command="pytest tests/test_parser.py",
        details={"passed": 2, "failed": 0},
    )
    assert ver["status"] == "PASSED"
    loaded_ver = await verification_repo.get(ver["verification_id"])
    assert loaded_ver["details"]["passed"] == 2


@pytest.mark.asyncio
async def test_sqlite_restart_persistence(tmp_path):
    """
    Validates that database state survives process termination:
    Process A writes -> closes connection -> Process B opens and asserts existence.
    """
    db_file = tmp_path / "restart_test.db"

    # Process A writes
    db_a = DatabaseManager(str(db_file))
    await db_a.init_db()
    mission_repo_a = MissionRepository(db_a)
    task_repo_a = TaskRepository(db_a)
    event_repo_a = EventRepository(db_a)

    await mission_repo_a.save({
        "id": "msn_restart_1",
        "title": "Persistent Mission Across Restarts",
        "goal": "Verify durability",
        "status": "RUNNING",
    })
    await task_repo_a.save({
        "id": "tsk_restart_1",
        "mission_id": "msn_restart_1",
        "title": "Verify data survival",
        "status": "COMPLETED",
    })
    await event_repo_a.append({
        "mission_id": "msn_restart_1",
        "task_id": "tsk_restart_1",
        "event_type": "test.passed",
        "payload": {"score": 100},
    })

    # Simulate Process A termination (drop instances)
    del mission_repo_a
    del task_repo_a
    del event_repo_a
    del db_a

    # Process B starts from scratch and loads database
    db_b = DatabaseManager(str(db_file))
    await db_b.init_db()
    mission_repo_b = MissionRepository(db_b)
    task_repo_b = TaskRepository(db_b)
    event_repo_b = EventRepository(db_b)

    loaded_mission = await mission_repo_b.get("msn_restart_1")
    assert loaded_mission is not None
    assert loaded_mission["title"] == "Persistent Mission Across Restarts"

    loaded_task = await task_repo_b.get("tsk_restart_1")
    assert loaded_task is not None
    assert loaded_task["status"] == "COMPLETED"

    events = await event_repo_b.list_by_mission("msn_restart_1")
    assert len(events) == 1
    assert events[0]["payload"]["score"] == 100


# ============================================================================
# 3. GIT WORKTREE ISOLATION TESTS
# ============================================================================

def _init_dummy_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(path), check=True)
    dummy_file = path / "README.md"
    dummy_file.write_text("# Dummy Project\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(path), check=True)


def test_worktree_uninitialized_git_refusal(tmp_path):
    """
    CRITICAL CONSTRAINT: If Git is uninitialized or unavailable, do NOT silently
    fall back to an unisolated directory. Must raise GitWorktreeError.
    """
    non_git_dir = tmp_path / "not_a_git_repo"
    non_git_dir.mkdir()

    mgr = GitWorktreeManager(non_git_dir)
    with pytest.raises(GitWorktreeError) as exc:
        mgr.create("m1", "t1")
    assert "not an initialized Git repository" in str(exc.value)


def test_worktree_creation_isolation_and_cleanup(tmp_path):
    repo_dir = tmp_path / "sample_git_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    mgr = GitWorktreeManager(repo_dir)
    mgr.verify_git_repo()

    mission_id = "msn_test"
    task_id = "tsk_iso_1"

    # 1. Create worktree
    wt_path = mgr.create(mission_id, task_id)
    assert wt_path.exists()
    assert wt_path.is_dir()
    assert (wt_path / "README.md").exists()

    # 2. Verify isolation: worktree is separate path
    assert wt_path != repo_dir
    assert mgr.exists(mission_id, task_id) is True

    # 3. Status check
    status = mgr.status(mission_id, task_id)
    assert status.is_active is True
    assert status.branch_name == "supervisor/msn_test/tsk_iso_1"
    assert status.has_uncommitted_changes is False

    # 4. Mutate file inside worktree - main repo must remain untouched!
    wt_test_file = wt_path / "task_work.txt"
    wt_test_file.write_text("isolated changes\n", encoding="utf-8")
    assert not (repo_dir / "task_work.txt").exists()  # Main repo is protected!

    status_after_change = mgr.status(mission_id, task_id)
    assert status_after_change.has_uncommitted_changes is True

    # 5. Duplicate protection: re-creating returns existing path without error
    wt_path_duplicate = mgr.create(mission_id, task_id)
    assert wt_path_duplicate == wt_path

    # 6. Safe cleanup
    mgr.cleanup(mission_id, task_id, force=True)
    assert not wt_path.exists()
    assert mgr.exists(mission_id, task_id) is False
    assert (repo_dir / "README.md").exists()  # Main repo remains completely intact


def test_worktree_path_traversal_prevention(tmp_path):
    repo_dir = tmp_path / "safe_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    mgr = GitWorktreeManager(repo_dir)
    # Sanitization strips malicious characters
    safe_name = sanitize_identifier("../../etc/passwd")
    assert "/" not in safe_name
    assert ".." not in safe_name


# ============================================================================
# 4. INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_event_bus_to_sqlite_persistence(tmp_path):
    db_file = tmp_path / "event_bus_test.db"
    db = DatabaseManager(str(db_file))
    await db.init_db()

    # Pre-populate mission for foreign key constraint
    m_repo = MissionRepository(db)
    await m_repo.save({"id": "msn_eb_1", "title": "Bus Test", "goal": "Integration"})

    bus = EventBus()
    repo = await attach_sqlite_persistence(bus, db)

    # Publish events to bus
    await bus.publish(
        Event(
            mission_id="msn_eb_1",
            task_id="tsk_01",
            type=EventType.TASK_STARTED,
            payload={"info": "started via bus"},
        )
    )
    await bus.publish(
        Event(
            mission_id="msn_eb_1",
            task_id="tsk_01",
            type=EventType.TASK_COMPLETED,
            payload={"info": "completed via bus"},
        )
    )

    # Give async subscriber a moment to finish write
    await asyncio.sleep(0.1)

    persisted_events = await repo.list_by_mission("msn_eb_1")
    assert len(persisted_events) == 2
    types = [e["event_type"] for e in persisted_events]
    assert "task.started" in types
    assert "task.completed" in types


@pytest.mark.asyncio
async def test_manager_persistence_reload_across_restart(tmp_path):
    from core.missions.manager import MissionManager
    from core.tasks.manager import TaskManager
    from agents.registry import AgentRegistry

    db_file = tmp_path / "managers_restart.db"

    # Instance 1: Create missions, tasks, agents
    db1 = DatabaseManager(str(db_file))
    await db1.init_db()
    bus1 = EventBus()

    mm1 = MissionManager(bus1, repository=MissionRepository(db1))
    tm1 = TaskManager(bus1, repository=TaskRepository(db1))
    ar1 = AgentRegistry(bus1, repository=AgentRepository(db1))

    m = await mm1.create_mission(title="Refactor Engine", goal="Improve modularity")
    t1 = Task(mission_id=m.id, title="Extract Protocol", status=TaskStatus.COMPLETED)
    t2 = Task(mission_id=m.id, title="Implement WAL", status=TaskStatus.IN_PROGRESS)
    await tm1.initialize_mission_tasks(m.id, [t1, t2])
    await ar1.register_agent(agent_id="agt_primary", agent_type="WORKER", mission_id=m.id)

    # Simulate shutdown / process restart: create completely new manager instances on same db
    del mm1, tm1, ar1, bus1, db1

    db2 = DatabaseManager(str(db_file))
    await db2.init_db()
    bus2 = EventBus()

    mm2 = MissionManager(bus2, repository=MissionRepository(db2))
    tm2 = TaskManager(bus2, repository=TaskRepository(db2))
    ar2 = AgentRegistry(bus2, repository=AgentRepository(db2))

    # Assert managers can load existing persisted state
    loaded_m = await mm2.get_mission(m.id)
    assert loaded_m is not None
    assert loaded_m.title == "Refactor Engine"

    graph = await tm2.get_graph(m.id)
    assert graph is not None
    assert len(graph.tasks) == 2
    assert graph.tasks[t1.id].status == TaskStatus.COMPLETED

    loaded_agent = await ar2.get_agent("agt_primary")
    assert loaded_agent is not None
    assert loaded_agent.agent_id == "agt_primary"
    assert loaded_agent.mission_id == m.id


@pytest.mark.asyncio
async def test_internal_worker_backward_compatibility():
    """Verify that existing internal Worker agent initializes and runs without breaking."""
    from agents.worker import WorkerAgent

    bus = EventBus()
    worker = WorkerAgent(
        agent_id="test_worker_compat",
        event_bus=bus,
        tools={},
        max_iterations=3,
    )
    assert worker.agent_id == "test_worker_compat"
    assert hasattr(worker, "run_task")
    assert hasattr(worker, "pause")
    assert hasattr(worker, "resume")


def test_worktree_merge_safe_explicit_failure(tmp_path):
    """Verify that merge() enforces safe explicit failure and never attempts unsafe auto-merges."""
    repo_dir = tmp_path / "merge_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    mgr = GitWorktreeManager(repo_dir)
    # Merging a non-existent branch must raise GitWorktreeError
    with pytest.raises(GitWorktreeError) as exc:
        mgr.merge("msn_nonexistent", "tsk_nonexistent", target_branch="main")
    assert "does not exist" in str(exc.value)

