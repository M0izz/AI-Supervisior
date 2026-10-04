import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple
import pytest

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.tasks.models import Task, TaskStatus
from core.protocol.schema import TaskDispatchPackage
from core.protocol.events import ProtocolEventType
from execution.worktree import GitWorktreeManager
from adapters.models import (
    AdapterIdentity,
    AdapterAvailabilityStatus,
    AdapterProcessStatus,
)
from adapters.registry import AdapterRegistry
from adapters.claude_code import ClaudeCodeAdapter
from adapters.codex import CodexAdapter
from core.handoff.models import (
    HandoffStatus,
    HandoffTrigger,
    FactProvenance,
    ContextFact,
    HandoffContextPackage,
    HandoffRecord,
    HandoffResult,
)
from core.handoff.context import HandoffContextBuilder
from core.handoff.engine import HandoffEngine
from core.verification.models import (
    VerificationDecision,
    VerificationCheckStatus,
    VerificationCheckType,
    VerificationContext,
    VerificationResult,
)
from core.verification.engine import VerificationEngine
from storage.sqlite import (
    DatabaseManager,
    MissionRepository,
    TaskRepository,
    VerificationRepository,
    HandoffRepository,
)


# ============================================================================
# HELPER FIXTURES
# ============================================================================

def _init_dummy_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(path), check=True)
    (path / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(path), check=True)


def _create_mock_script(tmp_path: Path, filename: str, script_content: str) -> str:
    script_file = tmp_path / filename
    script_file.write_text(script_content, encoding="utf-8")
    return str(script_file.resolve())


# ============================================================================
# 1. CODEX ADAPTER CONTRACT & IDENTITY TESTS
# ============================================================================

def test_codex_adapter_identity():
    adapter = CodexAdapter()
    identity = adapter.identity
    assert identity.provider == "openai"
    assert identity.adapter_id == "codex"
    assert identity.display_name == "OpenAI Codex"
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
async def test_codex_adapter_availability_uninstalled(monkeypatch):
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("CODEX_EXECUTABLE", raising=False)
    adapter = CodexAdapter(executable_override="nonexistent_codex_cli_99999")
    avail = await adapter.check_availability()
    assert avail.available is False
    assert avail.status == AdapterAvailabilityStatus.NOT_INSTALLED


@pytest.mark.asyncio
async def test_codex_adapter_availability_installed_mock(tmp_path):
    mock_bin = tmp_path / "mock_codex.exe"
    mock_bin.write_text("binary", encoding="utf-8")
    adapter = CodexAdapter(executable_override=str(mock_bin))
    avail = await adapter.check_availability()
    assert avail.available is True
    assert avail.status == AdapterAvailabilityStatus.AVAILABLE
    assert avail.executable_path == str(mock_bin.resolve())


@pytest.mark.asyncio
async def test_codex_adapter_rejects_main_repo_workspace(tmp_path):
    repo_dir = tmp_path / "primary_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    adapter = CodexAdapter(worktree_manager=wt_mgr)

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
async def test_codex_adapter_mock_execution_success(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    wt_path = wt_mgr.create("msn_codex", "tsk_codex")

    mock_script = _create_mock_script(
        tmp_path,
        "fake_codex.py",
        """import sys
print('Codex CLI starting...')
with open('codex_output.txt', 'w') as f:
    f.write('Generated by Codex\\n')
print('Codex CLI finished successfully.')
sys.exit(0)
""",
    )

    bus = EventBus()
    emitted_events = []

    async def _on_event(e):
        emitted_events.append(e)

    await bus.subscribe(_on_event)

    adapter = CodexAdapter(
        event_bus=bus,
        worktree_manager=wt_mgr,
        executable_override=mock_script,
    )

    dispatch = TaskDispatchPackage(
        task_id="tsk_codex",
        mission_id="msn_codex",
        objective="Generate codex output",
        workspace=str(wt_path),
        allowed_files=["codex_output.txt"],
    )

    result = await adapter.execute(dispatch)
    assert result.status == AdapterProcessStatus.COMPLETED
    assert result.exit_code == 0
    assert (wt_path / "codex_output.txt").exists()
    assert (wt_path / "codex_output.txt").read_text(encoding="utf-8").strip() == "Generated by Codex"
    # Main repo remained untouched
    assert not (repo_dir / "codex_output.txt").exists()


# ============================================================================
# 2. HANDOFF CONTEXT BUILDER & PROVENANCE TESTS
# ============================================================================

def test_handoff_context_builder_provenance(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    wt_path = wt_mgr.create("msn_ctx", "tsk_ctx")

    # Add a modified file in the worktree
    mod_file = wt_path / "auth.py"
    mod_file.write_text("def authenticate(): return False\n", encoding="utf-8")

    pkg = HandoffContextBuilder.build(
        mission_id="msn_ctx",
        task_id="tsk_ctx",
        objective="Fix auth logic",
        workspace=str(wt_path),
        source_agent_id="claude_code",
        target_agent_id="codex",
        trigger=HandoffTrigger.REPEATED_FAILURE,
        reason="Claude stuck in retry loop",
        failure_signature="TypeError: unsupported operand",
        consecutive_failures=3,
        watchdog_evidence={"anomaly": "REPEATED_FAILURE_LOOP", "attempts": 3},
        verification_evidence={"tests_passed": 0, "tests_failed": 2},
        source_claim={"claim": "Claude claimed it solved the bug", "verified": False},
        executed_commands=["pytest tests/test_auth.py", "python auth.py"],
    )

    assert pkg.task_id == "tsk_ctx"
    assert pkg.source_agent_id == "claude_code"
    assert pkg.target_agent_id == "codex"
    assert pkg.trigger == HandoffTrigger.REPEATED_FAILURE
    assert "auth.py" in pkg.changed_files

    # Check verified vs unverified vs rejected provenance separation
    verified_statements = [f.statement for f in pkg.verified_facts]
    unverified_statements = [f.statement for f in pkg.unverified_claims]
    rejected_statements = [f.statement for f in pkg.rejected_attempts]

    assert any("TypeError: unsupported operand" in s for s in rejected_statements)
    assert any("Claude claimed it solved the bug" in s for s in unverified_statements)
    assert any("Changed files" in s for s in verified_statements)

    # Provenance tags must match
    for f in pkg.verified_facts:
        assert f.provenance == FactProvenance.VERIFIED
    for f in pkg.unverified_claims:
        assert f.provenance == FactProvenance.UNVERIFIED
    for f in pkg.rejected_attempts:
        assert f.provenance == FactProvenance.REJECTED


# ============================================================================
# 3. HANDOFF PERSISTENCE & RESTAURABILITY (SQLITE WAL)
# ============================================================================

@pytest.mark.asyncio
async def test_handoff_persistence_sqlite_and_restart(tmp_path):
    db_file = tmp_path / "supervisor_test.db"
    db = DatabaseManager(db_path=str(db_file))
    mission_repo = MissionRepository(db)
    task_repo = TaskRepository(db)
    handoff_repo = HandoffRepository(db)

    # Seed parent mission and task
    await mission_repo.save({
        "mission_id": "msn_persist",
        "title": "Persistence Test Mission",
        "goal": "Verify SQLite durability",
        "status": "IN_PROGRESS",
    })
    await task_repo.save({
        "task_id": "tsk_persist",
        "mission_id": "msn_persist",
        "title": "Persist Handoff Task",
        "status": "IN_PROGRESS",
    })

    # Save handoff record
    rec_dict = await handoff_repo.save(
        mission_id="msn_persist",
        task_id="tsk_persist",
        source_agent_id="claude_code",
        target_agent_id="codex",
        trigger=HandoffTrigger.AGENT_FAILURE.value,
        status=HandoffStatus.TRANSFERRED.value,
        reason="Agent process terminated unexpectedly",
        context_package={"objective": "Recover from crash", "remaining_work": "Finish task"},
        result=None,
    )
    rec_id = rec_dict["handoff_id"]
    assert rec_id is not None

    # Retrieve record
    saved_rec = await handoff_repo.get(rec_id)
    assert saved_rec is not None
    assert saved_rec["source_agent_id"] == "claude_code"
    assert saved_rec["target_agent_id"] == "codex"
    assert saved_rec["status"] == HandoffStatus.TRANSFERRED.value

    # Simulate restart by instantiating new DatabaseManager on same DB file
    db_reopened = DatabaseManager(db_path=str(db_file))
    reopened_repo = HandoffRepository(db_reopened)

    retrieved = await reopened_repo.get(rec_id)
    assert retrieved is not None
    assert retrieved["handoff_id"] == rec_id
    assert retrieved["trigger"] == HandoffTrigger.AGENT_FAILURE.value
    assert retrieved["context_package"]["objective"] == "Recover from crash"

    task_handoffs = await reopened_repo.list_by_task("tsk_persist")
    assert len(task_handoffs) == 1
    assert task_handoffs[0]["handoff_id"] == rec_id


# ============================================================================
# 4. WORKTREE CONTINUITY & SOURCE CANCELLATION
# ============================================================================

@pytest.mark.asyncio
async def test_handoff_worktree_continuity_and_cancellation(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    wt_path = wt_mgr.create("msn_cont", "tsk_cont")

    # Claude partially edited a file
    (wt_path / "partial.py").write_text("# Claude work\ndef step1(): pass\n", encoding="utf-8")

    # Mock Claude script that sleeps (to test cancellation)
    mock_claude_script = _create_mock_script(
        tmp_path,
        "claude_hang.py",
        """import time
print('Claude starting and hanging...')
while True:
    time.sleep(1)
""",
    )

    # Mock Codex script that completes work in the same worktree
    mock_codex_script = _create_mock_script(
        tmp_path,
        "codex_finish.py",
        """import os, sys
print('Codex picking up task in worktree...')
# Assert that partial work from Claude is present
if not os.path.exists('partial.py'):
    sys.exit(1)
with open('partial.py', 'a') as f:
    f.write('def step2(): return True\\n')
sys.exit(0)
""",
    )

    bus = EventBus()
    emitted_events = []

    async def _on_event(e):
        emitted_events.append(e)

    await bus.subscribe(_on_event)

    adapter_registry = AdapterRegistry()
    claude_adapter = ClaudeCodeAdapter(
        event_bus=bus,
        worktree_manager=wt_mgr,
        executable_override=mock_claude_script,
    )
    codex_adapter = CodexAdapter(
        event_bus=bus,
        worktree_manager=wt_mgr,
        executable_override=mock_codex_script,
    )
    adapter_registry.register_adapter(claude_adapter)
    adapter_registry.register_adapter(codex_adapter)

    engine = HandoffEngine(
        event_bus=bus,
        adapter_registry=adapter_registry,
        worktree_manager=wt_mgr,
        max_handoffs_per_task=3,
    )

    # Execute handoff
    result = await engine.execute_handoff(
        mission_id="msn_cont",
        task_id="tsk_cont",
        source_agent_id="claude_code",
        target_agent_id="codex",
        trigger=HandoffTrigger.REPEATED_FAILURE,
        reason="Claude stalled",
        objective="Complete step2 in partial.py",
        workspace=str(wt_path),
        allowed_scope=["partial.py"],
    )

    assert result.success is True
    assert result.status == HandoffStatus.COMPLETED

    # Verify worktree continuity: step 1 and step 2 exist in same file
    content = (wt_path / "partial.py").read_text(encoding="utf-8")
    assert "def step1(): pass" in content
    assert "def step2(): return True" in content

    # Verify emitted events
    event_types = [e.payload.get("event_type") for e in emitted_events if isinstance(e.payload, dict)]
    assert "handoff.requested" in event_types
    assert "handoff.prepared" in event_types
    assert "handoff.started" in event_types
    assert "handoff.completed" in event_types


# ============================================================================
# 5. KILLER SCENARIO 1: DETERMINISTIC END-TO-END RECOVERY + INDEPENDENT VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_killer_scenario_auth_fix_handoff_and_verification(tmp_path):
    """
    KILLER SCENARIO 1:
    1. Mission: Fix authentication tests.
    2. Claude attempts a flawed fix 3 times -> Watchdog repeatedly detects failure.
    3. Supervisor halts Claude, creates Context Package with provenance.
    4. Task handed off to Codex in the SAME isolated worktree.
    5. Codex applies the correct fix to auth/session.py and claims completion.
    6. Phase 4 Independent Verification Engine runs tests independently.
    7. Verification engine returns ACCEPT. Task is independently verified!
    """
    repo_dir = tmp_path / "auth_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    # Initialize auth/session.py with broken parser and a test file
    auth_dir = repo_dir / "auth"
    auth_dir.mkdir()
    (auth_dir / "session.py").write_text(
        """def parse_token(token: str) -> dict:
    # BUG: fails on bearer token
    return {"token": token}
""",
        encoding="utf-8",
    )

    test_file = repo_dir / "test_auth.py"
    test_file.write_text(
        """import sys
from auth.session import parse_token

def test_bearer():
    res = parse_token("Bearer xyz123")
    if res.get("token") != "xyz123":
        print("FAIL: Expected 'xyz123', got:", res.get("token"))
        sys.exit(1)
    print("PASS")
    sys.exit(0)

if __name__ == '__main__':
    test_bearer()
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Add auth and tests"], cwd=str(repo_dir), check=True)

    wt_mgr = GitWorktreeManager(repo_dir)
    wt_path = wt_mgr.create("msn_auth", "tsk_auth")

    # Mock Claude script: repeatedly writes wrong fix
    mock_claude_script = _create_mock_script(
        tmp_path,
        "claude_auth_broken.py",
        """import sys
# Flawed attempt: sets token to 'Bearer'
with open('auth/session.py', 'w') as f:
    f.write('def parse_token(token: str) -> dict:\\n    return {"token": "Bearer"}\\n')
print('Claude finished attempt (wrong fix)')
sys.exit(0)
""",
    )

    # Mock Codex script: reads handoff context and applies correct fix
    mock_codex_script = _create_mock_script(
        tmp_path,
        "codex_auth_fix.py",
        """import sys
# Correct fix: strips 'Bearer ' prefix
with open('auth/session.py', 'w') as f:
    f.write('''def parse_token(token: str) -> dict:
    if token.startswith("Bearer "):
        token = token[7:]
    return {"token": token}
''')
print('Codex successfully applied correct fix.')
sys.exit(0)
""",
    )

    bus = EventBus()
    db_file = tmp_path / "supervisor.db"
    db = DatabaseManager(db_path=str(db_file))
    mission_repo = MissionRepository(db)
    task_repo = TaskRepository(db)
    ver_repo = VerificationRepository(db)
    handoff_repo = HandoffRepository(db)

    # Seed parent mission and task
    await mission_repo.save({
        "mission_id": "msn_auth",
        "title": "Fix authentication tests",
        "goal": "Fix parse_token to strip Bearer",
        "repository_path": str(repo_dir),
        "status": "IN_PROGRESS",
    })
    await task_repo.save({
        "task_id": "tsk_auth",
        "mission_id": "msn_auth",
        "title": "Fix token parsing",
        "status": "IN_PROGRESS",
        "assigned_agent": "claude_code",
    })

    adapter_registry = AdapterRegistry()
    claude_adapter = ClaudeCodeAdapter(
        event_bus=bus,
        worktree_manager=wt_mgr,
        executable_override=mock_claude_script,
    )
    codex_adapter = CodexAdapter(
        event_bus=bus,
        worktree_manager=wt_mgr,
        executable_override=mock_codex_script,
    )
    adapter_registry.register_adapter(claude_adapter)
    adapter_registry.register_adapter(codex_adapter)

    ver_engine = VerificationEngine(
        event_bus=bus,
        repository=ver_repo,
        worktree_manager=wt_mgr,
    )

    handoff_engine = HandoffEngine(
        event_bus=bus,
        adapter_registry=adapter_registry,
        repository=handoff_repo,
        worktree_manager=wt_mgr,
        verification_engine=ver_engine,
        max_handoffs_per_task=3,
    )

    # 1. Claude runs and applies flawed attempt
    dispatch_claude = TaskDispatchPackage(
        task_id="tsk_auth",
        mission_id="msn_auth",
        objective="Fix token parsing",
        workspace=str(wt_path),
        allowed_files=["auth/session.py"],
    )
    claude_result = await claude_adapter.execute(dispatch_claude)
    assert claude_result.status == AdapterProcessStatus.COMPLETED

    # Verifier check on Claude's attempt: REJECT
    v_ctx_claude = VerificationContext(
        task_id="tsk_auth",
        mission_id="msn_auth",
        workspace=str(wt_path),
        agent_id="claude_code",
        verification_requirements=["python test_auth.py"],
        allowed_files=["auth/session.py"],
        completion_claim={"summary": "Claude claimed fix completed"},
    )
    claude_ver_res = await ver_engine.verify(v_ctx_claude)
    assert claude_ver_res.decision == VerificationDecision.REJECT

    # 2. Supervisor initiates Handoff to Codex due to VERIFICATION_FAILURE
    handoff_res = await handoff_engine.execute_handoff(
        mission_id="msn_auth",
        task_id="tsk_auth",
        source_agent_id="claude_code",
        target_agent_id="codex",
        trigger=HandoffTrigger.VERIFICATION_FAILURE,
        reason="Independent verifier rejected Claude's fix: test_auth.py failed",
        objective="Fix token parsing to pass test_auth.py",
        workspace=str(wt_path),
        allowed_scope=["auth/session.py"],
        failure_signature="test_auth.py exit code 1",
        consecutive_failures=1,
        verification_evidence=claude_ver_res.model_dump(mode="json"),
        verify_after=True,
        test_commands=["python test_auth.py"],
    )

    # 3. Assert handoff succeeded and independent verification PASSED
    assert handoff_res.success is True
    assert handoff_res.status == HandoffStatus.COMPLETED
    assert handoff_res.context_package is not None
    assert handoff_res.context_package.target_agent_id == "codex"

    # 4. Verify Phase 4 verification engine independently accepted the result
    assert handoff_res.verification_result is not None
    assert handoff_res.verification_result.decision == VerificationDecision.ACCEPT, (
        f"Verification failed with checks: {[(c.check_id, c.status, c.message) for c in handoff_res.verification_result.checks]}"
    )
    assert "Independent verification ACCEPTED" in handoff_res.verification_result.summary

    # 5. Primary repository remained clean
    primary_session = (repo_dir / "auth" / "session.py").read_text(encoding="utf-8")
    assert "startswith" not in primary_session  # Isolation preserved!


# ============================================================================
# 6. KILLER SCENARIO 2: HANDOFF LOOP PROTECTION & BUDGET ENFORCEMENT
# ============================================================================

@pytest.mark.asyncio
async def test_killer_scenario_handoff_loop_prevention(tmp_path):
    """
    KILLER SCENARIO 2:
    Simulates repeated failures between agents:
    Claude -> fails -> Handoff 1 to Codex -> fails -> Handoff 2 to Claude -> fails -> Handoff 3.
    Once ceiling is exceeded, Supervisor rejects handoff, emits SUPERVISOR_HUMAN_REQUIRED,
    and prevents an infinite handoff ping-pong loop.
    """
    repo_dir = tmp_path / "loop_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    wt_mgr = GitWorktreeManager(repo_dir)
    wt_path = wt_mgr.create("msn_loop", "tsk_loop")

    mock_fail_script = _create_mock_script(
        tmp_path,
        "fail_agent.py",
        """import sys
print('Agent failed to complete task')
sys.exit(1)
""",
    )

    bus = EventBus()
    emitted_events = []

    async def _on_event(e):
        emitted_events.append(e)

    await bus.subscribe(_on_event)

    adapter_registry = AdapterRegistry()
    claude_adapter = ClaudeCodeAdapter(
        event_bus=bus,
        worktree_manager=wt_mgr,
        executable_override=mock_fail_script,
    )
    codex_adapter = CodexAdapter(
        event_bus=bus,
        worktree_manager=wt_mgr,
        executable_override=mock_fail_script,
    )
    adapter_registry.register_adapter(claude_adapter)
    adapter_registry.register_adapter(codex_adapter)

    # Configure conservative ceiling: max 2 handoffs per task
    engine = HandoffEngine(
        event_bus=bus,
        adapter_registry=adapter_registry,
        worktree_manager=wt_mgr,
        max_handoffs_per_task=2,
    )

    # Handoff 1: Claude -> Codex (allowed)
    res1 = await engine.execute_handoff(
        mission_id="msn_loop",
        task_id="tsk_loop",
        source_agent_id="claude_code",
        target_agent_id="codex",
        trigger=HandoffTrigger.REPEATED_FAILURE,
        reason="First failure",
        objective="Solve intractable problem",
        workspace=str(wt_path),
    )
    assert engine.get_task_handoff_count("tsk_loop") == 1

    # Handoff 2: Codex -> Claude (allowed)
    res2 = await engine.execute_handoff(
        mission_id="msn_loop",
        task_id="tsk_loop",
        source_agent_id="codex",
        target_agent_id="claude_code",
        trigger=HandoffTrigger.REPEATED_FAILURE,
        reason="Second failure",
        objective="Solve intractable problem",
        workspace=str(wt_path),
    )
    assert engine.get_task_handoff_count("tsk_loop") == 2

    # Handoff 3: Attempting another handoff must be REJECTED by loop protection
    res3 = await engine.execute_handoff(
        mission_id="msn_loop",
        task_id="tsk_loop",
        source_agent_id="claude_code",
        target_agent_id="codex",
        trigger=HandoffTrigger.REPEATED_FAILURE,
        reason="Third failure",
        objective="Solve intractable problem",
        workspace=str(wt_path),
    )

    assert res3.success is False
    assert res3.status == HandoffStatus.REJECTED
    assert "HANDOFF_LIMIT_REACHED" in (res3.error or "")

    # Assert Supervisor emitted SUPERVISOR_HUMAN_REQUIRED event
    critical_events = [
        e for e in emitted_events
        if e.type == EventType.SUPERVISOR_HUMAN_REQUIRED
    ]
    assert len(critical_events) == 1
    assert "HANDOFF_LIMIT_REACHED" in critical_events[0].payload["reason"]
