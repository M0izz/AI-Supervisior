import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import pytest

from core.events.bus import EventBus
from core.events.schema import Event, EventType
from core.protocol.schema import TaskDispatchPackage
from core.protocol.validators import ProtocolValidationError
from execution.worktree import GitWorktreeManager
from storage.sqlite import DatabaseManager, MissionRepository, attach_sqlite_persistence
from agents.registry import AgentRegistry
from adapters.models import (
    AdapterIdentity,
    AdapterCapability,
    AdapterAvailabilityStatus,
    AdapterProcessStatus,
)
from adapters.base import AgentAdapter
from adapters.registry import AdapterRegistry
from adapters.claude_code import ClaudeCodeAdapter


# ============================================================================
# HELPER FIXTURES: FAKE CLAUDE PROCESS
# ============================================================================

def _create_mock_claude_script(tmp_path: Path, script_content: str) -> str:
    """Creates a deterministic Python script to act as a fake Claude executable."""
    script_file = tmp_path / "fake_claude.py"
    script_file.write_text(script_content, encoding="utf-8")
    return str(script_file.resolve())


def _init_dummy_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(path), check=True)
    (path / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(path), check=True)


# ============================================================================
# 1. ADAPTER CONTRACT & IDENTITY TESTS
# ============================================================================

def test_claude_adapter_identity():
    adapter = ClaudeCodeAdapter()
    identity = adapter.identity
    assert identity.provider == "anthropic"
    assert identity.adapter_id == "claude_code"
    assert identity.display_name == "Claude Code"
    assert identity.version == "1.0.0"

    expected_caps = [
        "code_execution",
        "filesystem_read",
        "filesystem_write",
        "terminal_execution",
        "git",
        "test_execution",
    ]
    for cap in expected_caps:
        assert cap in adapter.capabilities


@pytest.mark.asyncio
async def test_claude_adapter_availability_uninstalled(monkeypatch):
    # Simulate claude CLI not being installed
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("CLAUDE_CODE_EXECUTABLE", raising=False)
    adapter = ClaudeCodeAdapter(executable_override="nonexistent_claude_binary_12345")
    avail = await adapter.check_availability()
    assert avail.available is False
    assert avail.status == AdapterAvailabilityStatus.NOT_INSTALLED


@pytest.mark.asyncio
async def test_claude_adapter_availability_installed_mock(tmp_path):
    mock_bin = tmp_path / "mock_claude.exe"
    mock_bin.write_text("binary", encoding="utf-8")
    adapter = ClaudeCodeAdapter(executable_override=str(mock_bin))
    avail = await adapter.check_availability()
    assert avail.available is True
    assert avail.status == AdapterAvailabilityStatus.AVAILABLE
    assert avail.executable_path == str(mock_bin.resolve())


# ============================================================================
# 2. WORKSPACE ISOLATION ENFORCEMENT
# ============================================================================

@pytest.mark.asyncio
async def test_claude_adapter_rejects_main_repo_workspace(tmp_path):
    repo_dir = tmp_path / "primary_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    adapter = ClaudeCodeAdapter(worktree_manager=wt_mgr)

    # Attempting to execute in the primary repo root must be explicitly rejected
    dispatch = TaskDispatchPackage(
        task_id="tsk_danger",
        mission_id="msn_001",
        objective="Modify main repo",
        workspace=str(repo_dir),
    )

    result = await adapter.execute(dispatch)
    assert result.status == AdapterProcessStatus.FAILED
    assert "matches primary repository root" in result.failure_reason


@pytest.mark.asyncio
async def test_claude_adapter_rejects_workspace_outside_worktrees(tmp_path):
    repo_dir = tmp_path / "primary_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    arbitrary_dir = tmp_path / "arbitrary_dir"
    arbitrary_dir.mkdir()

    wt_mgr = GitWorktreeManager(repo_dir)
    adapter = ClaudeCodeAdapter(worktree_manager=wt_mgr)

    dispatch = TaskDispatchPackage(
        task_id="tsk_outside",
        mission_id="msn_001",
        objective="Escape containment",
        workspace=str(arbitrary_dir),
    )

    result = await adapter.execute(dispatch)
    assert result.status == AdapterProcessStatus.FAILED
    assert "outside supervisor worktree directory" in result.failure_reason


@pytest.mark.asyncio
async def test_claude_adapter_rejects_nonexistent_workspace(tmp_path):
    repo_dir = tmp_path / "primary_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    adapter = ClaudeCodeAdapter(worktree_manager=wt_mgr)

    dispatch = TaskDispatchPackage(
        task_id="tsk_ghost",
        mission_id="msn_001",
        objective="Run in ghost dir",
        workspace=str(repo_dir / ".supervisor" / "worktrees" / "ghost_dir"),
    )

    result = await adapter.execute(dispatch)
    assert result.status == AdapterProcessStatus.FAILED
    assert "does not exist" in result.failure_reason


# ============================================================================
# 3. DETERMINISTIC PROCESS LIFECYCLE TESTS (MOCK CLAUDE)
# ============================================================================

@pytest.mark.asyncio
async def test_claude_process_successful_execution(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    wt_path = wt_mgr.create("msn_succ", "tsk_succ")

    # Fake Claude script that simulates writing a file and completing
    mock_script = _create_mock_claude_script(
        tmp_path,
        """import sys, time
print('Starting Claude Code execution...')
print('Analyzing requirements')
print('Writing solution.py')
with open('solution.py', 'w') as f:
    f.write('print("solved")\\n')
print('Done!')
sys.exit(0)
"""
    )

    bus = EventBus()
    emitted_events = []

    async def _on_event(e):
        emitted_events.append(e)

    await bus.subscribe(_on_event)

    adapter = ClaudeCodeAdapter(
        event_bus=bus,
        worktree_manager=wt_mgr,
        executable_override=mock_script,
    )

    dispatch = TaskDispatchPackage(
        task_id="tsk_succ",
        mission_id="msn_succ",
        objective="Create solution.py",
        workspace=str(wt_path),
        allowed_files=["solution.py"],
    )

    result = await adapter.execute(dispatch)

    assert result.status == AdapterProcessStatus.COMPLETED
    assert result.exit_code == 0
    assert (wt_path / "solution.py").exists()
    assert not (repo_dir / "solution.py").exists()  # Isolated!
    assert "solution.py" in result.affected_files

    # Verify event normalization
    types = [e.payload.get("event_type") for e in emitted_events]
    assert "agent.started" in types
    assert "command.started" in types
    assert "file.changed" in types
    assert "task.completed" in types


@pytest.mark.asyncio
async def test_claude_process_failure_exit(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    wt_path = wt_mgr.create("msn_fail", "tsk_fail")

    mock_script = _create_mock_claude_script(
        tmp_path,
        """import sys
sys.stderr.write('Fatal syntax error in generated code\\n')
sys.exit(2)
"""
    )

    adapter = ClaudeCodeAdapter(
        worktree_manager=wt_mgr,
        executable_override=mock_script,
    )

    dispatch = TaskDispatchPackage(
        task_id="tsk_fail",
        mission_id="msn_fail",
        objective="Trigger failure",
        workspace=str(wt_path),
    )

    result = await adapter.execute(dispatch)
    assert result.status == AdapterProcessStatus.FAILED
    assert result.exit_code == 2
    assert "Fatal syntax error" in result.stderr_excerpt


@pytest.mark.asyncio
async def test_claude_process_timeout(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    wt_path = wt_mgr.create("msn_to", "tsk_to")

    # Script that sleeps longer than timeout
    mock_script = _create_mock_claude_script(
        tmp_path,
        """import time
time.sleep(10.0)
"""
    )

    adapter = ClaudeCodeAdapter(
        worktree_manager=wt_mgr,
        executable_override=mock_script,
    )

    dispatch = TaskDispatchPackage(
        task_id="tsk_to",
        mission_id="msn_to",
        objective="Run slow task",
        workspace=str(wt_path),
        timeout=1.0,  # 1 second timeout
    )

    result = await adapter.execute(dispatch)
    assert result.status == AdapterProcessStatus.TIMED_OUT
    assert "timed out" in result.summary.lower()


@pytest.mark.asyncio
async def test_claude_process_cancellation(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    wt_path = wt_mgr.create("msn_canc", "tsk_canc")

    mock_script = _create_mock_claude_script(
        tmp_path,
        """import time
time.sleep(10.0)
"""
    )

    adapter = ClaudeCodeAdapter(
        worktree_manager=wt_mgr,
        executable_override=mock_script,
    )

    dispatch = TaskDispatchPackage(
        task_id="tsk_canc",
        mission_id="msn_canc",
        objective="Cancel me",
        workspace=str(wt_path),
        timeout=15.0,
    )

    # Launch task in background coroutine and cancel after 0.5s
    task_fut = asyncio.create_task(adapter.execute(dispatch))
    await asyncio.sleep(0.5)

    cancelled = await adapter.cancel("tsk_canc")
    assert cancelled is True

    result = await task_fut
    assert result.status == AdapterProcessStatus.CANCELLED
    assert "cancelled" in result.summary.lower()


# ============================================================================
# 4. REGISTRY DISCOVERY TESTS
# ============================================================================

def test_adapter_registry_discovery():
    registry = AdapterRegistry()
    claude = ClaudeCodeAdapter()
    registry.register_adapter(claude)

    assert registry.get_adapter("claude_code") is not None
    assert len(registry.list_adapters()) == 1

    # Capability lookup
    matched = registry.find_by_capability("code_execution")
    assert len(matched) == 1
    assert matched[0].identity.adapter_id == "claude_code"

    unmatched = registry.find_by_capability("nonexistent_superpower")
    assert len(unmatched) == 0


def test_agent_registry_integration():
    """Verify that existing AgentRegistry exposes external adapter discovery."""
    registry = AgentRegistry()
    claude = ClaudeCodeAdapter()
    registry.register_adapter(claude)

    found = registry.get_adapter("claude_code")
    assert found is not None
    assert found.identity.display_name == "Claude Code"
    assert len(registry.list_adapters()) == 1


# ============================================================================
# 5. END-TO-END INTEGRATION TEST
# ============================================================================

@pytest.mark.asyncio
async def test_e2e_fake_claude_worktree_persistence(tmp_path):
    """
    End-to-End Test:
    Mission -> Task -> GitWorktreeManager -> TaskDispatchPackage ->
    ClaudeCodeAdapter -> Fake Claude process -> EventBus -> SQLite -> Completion.
    """
    # 1. Setup Git repo and worktree manager
    repo_dir = tmp_path / "e2e_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    mission_id = "msn_e2e_99"
    task_id = "tsk_e2e_99"

    wt_path = wt_mgr.create(mission_id, task_id)
    assert wt_path.exists()

    # 2. Setup SQLite persistence & EventBus
    db_file = tmp_path / "e2e.db"
    db = DatabaseManager(str(db_file))
    await db.init_db()

    m_repo = MissionRepository(db)
    await m_repo.save({"id": mission_id, "title": "E2E Adapter Test", "goal": "Verify adapter kernel"})

    bus = EventBus()
    event_repo = await attach_sqlite_persistence(bus, db)

    # 3. Setup mock Claude process
    mock_script = _create_mock_claude_script(
        tmp_path,
        """import sys
print('Writing feature.py')
with open('feature.py', 'w') as f:
    f.write('def feature(): return 42\\n')
sys.exit(0)
"""
    )

    # 4. Instantiate ClaudeCodeAdapter
    adapter = ClaudeCodeAdapter(
        event_bus=bus,
        worktree_manager=wt_mgr,
        executable_override=mock_script,
    )

    # 5. Build TaskDispatchPackage
    dispatch = TaskDispatchPackage(
        task_id=task_id,
        mission_id=mission_id,
        objective="Implement feature function",
        workspace=str(wt_path),
        allowed_files=["feature.py"],
        timeout=10.0,
    )

    # 6. Execute task
    result = await adapter.execute(dispatch)

    assert result.status == AdapterProcessStatus.COMPLETED
    assert result.exit_code == 0
    assert (wt_path / "feature.py").exists()
    assert not (repo_dir / "feature.py").exists()  # Main repo protected!

    # 7. Verify events persisted in SQLite
    await asyncio.sleep(0.1)
    persisted = await event_repo.list_by_mission(mission_id)
    assert len(persisted) >= 3
    event_types = [e["event_type"] for e in persisted]
    assert "agent.started" in event_types
    assert "task.completed" in event_types


# ============================================================================
# 6. OPTIONAL REAL CLAUDE SMOKE TEST
# ============================================================================

@pytest.mark.skipif(
    not shutil.which("claude") or not os.getenv("ANTHROPIC_API_KEY"),
    reason="Real Claude Code executable or ANTHROPIC_API_KEY not configured in environment.",
)
@pytest.mark.asyncio
async def test_real_claude_smoke_test(tmp_path):
    """
    Optional live smoke test against installed Claude Code CLI.
    Runs a minimal harmless task in an isolated temporary worktree.
    """
    repo_dir = tmp_path / "live_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    wt_path = wt_mgr.create("msn_live", "tsk_live")

    adapter = ClaudeCodeAdapter(worktree_manager=wt_mgr)
    avail = await adapter.check_availability()
    assert avail.available is True

    dispatch = TaskDispatchPackage(
        task_id="tsk_live",
        mission_id="msn_live",
        objective="Create a hello.txt file containing 'Hello from AI Supervisor'",
        workspace=str(wt_path),
        timeout=60.0,
    )

    result = await adapter.execute(dispatch)
    assert result.status == AdapterProcessStatus.COMPLETED
    assert (wt_path / "hello.txt").exists()
