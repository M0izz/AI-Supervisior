import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List, Optional
import pytest

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.tasks.manager import TaskManager
from core.tasks.models import Task, TaskStatus
from core.protocol.schema import TaskDispatchPackage
from core.protocol.events import ProtocolEventType
from core.verification.models import (
    VerificationDecision,
    VerificationCheckStatus,
    VerificationCheckType,
    VerificationCheck,
    VerificationContext,
    VerificationResult,
)
from core.verification.engine import VerificationEngine
from storage.sqlite import (
    DatabaseManager,
    MissionRepository,
    TaskRepository,
    VerificationRepository,
)


# ============================================================================
# TEST HELPERS
# ============================================================================

async def _seed_mission_and_task(
    db: DatabaseManager,
    mission_id: str,
    task_id: str,
    repo_path: str,
    allowed_files: Optional[List[str]] = None,
    expected_files: Optional[List[str]] = None,
) -> Tuple[MissionRepository, TaskRepository]:
    mission_repo = MissionRepository(db)
    task_repo = TaskRepository(db)

    await mission_repo.save({
        "mission_id": mission_id,
        "title": "Auth Verification Mission",
        "goal": "Verify authentication services",
        "repository_path": repo_path,
        "status": "IN_PROGRESS",
    })

    await task_repo.save({
        "task_id": task_id,
        "mission_id": mission_id,
        "title": "Repair authentication test failures",
        "status": "IN_PROGRESS",
        "assigned_agent": "claude_code",
        "expected_files": expected_files or [],
    })

    return mission_repo, task_repo


# ============================================================================
# TEST 1: SUCCESSFUL VERIFICATION (ACCEPT)
# ============================================================================

@pytest.mark.asyncio
async def test_verification_successful_accept():
    """
    When all tests pass, scope is respected, and worktree is valid,
    the verifier must produce ACCEPT and mark task VERIFIED.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        # Create passing test script
        test_file = ws / "test_auth.py"
        test_file.write_text("def test_ok(): assert 1 == 1\n", encoding="utf-8")

        db = DatabaseManager(db_path=os.path.join(tmp_dir, "test.db"))
        mission_repo, task_repo = await _seed_mission_and_task(db, "m-1", "t-1", tmp_dir)
        ver_repo = VerificationRepository(db)
        bus = EventBus()
        task_mgr = TaskManager(event_bus=bus, repository=task_repo)
        task = Task(id="t-1", mission_id="m-1", title="Auth fix")
        await task_mgr.initialize_mission_tasks("m-1", [task])

        engine = VerificationEngine(
            event_bus=bus,
            repository=ver_repo,
            task_manager=task_mgr,
        )

        context = VerificationContext(
            mission_id="m-1",
            task_id="t-1",
            agent_id="claude_code",
            workspace=tmp_dir,
            allowed_files=["test_auth.py"],
            verification_requirements=[f"python -m pytest {test_file.name}"],
            completion_claim={"summary": "Fixed authentication tests", "changed_files": ["test_auth.py"]},
        )

        result = await engine.verify(context)

        assert result.decision == VerificationDecision.ACCEPT
        assert result.status == "PASSED"
        assert len(result.failed_checks) == 0

        # Verify task is now VERIFIED
        verified_task = await task_mgr.get_task("m-1", "t-1")
        assert verified_task is not None
        assert verified_task.status == TaskStatus.VERIFIED


# ============================================================================
# TEST 2: AGENT LIES ABOUT TESTS (REJECT)
# ============================================================================

@pytest.mark.asyncio
async def test_verification_agent_lies_about_tests():
    """
    Agent claims 'All tests pass', but the independent test execution fails.
    Verifier must produce REJECT and reopen/fail the task.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        # Create failing test script
        test_file = ws / "test_auth.py"
        test_file.write_text("def test_fail(): assert 1 == 2, 'Token expired'\n", encoding="utf-8")

        db = DatabaseManager(db_path=os.path.join(tmp_dir, "test.db"))
        mission_repo, task_repo = await _seed_mission_and_task(db, "m-2", "t-2", tmp_dir)
        ver_repo = VerificationRepository(db)
        bus = EventBus()
        task_mgr = TaskManager(event_bus=bus, repository=task_repo)
        task = Task(id="t-2", mission_id="m-2", title="Auth fix")
        await task_mgr.initialize_mission_tasks("m-2", [task])

        engine = VerificationEngine(
            event_bus=bus,
            repository=ver_repo,
            task_manager=task_mgr,
        )

        context = VerificationContext(
            mission_id="m-2",
            task_id="t-2",
            agent_id="claude_code",
            workspace=tmp_dir,
            allowed_files=["test_auth.py"],
            verification_requirements=[f"python -m pytest {test_file.name}"],
            completion_claim={"summary": "Agent claimed all tests pass 100%"},
        )

        result = await engine.verify(context)

        assert result.decision == VerificationDecision.REJECT
        assert result.status == "FAILED"
        assert "check_tests" in result.failed_checks

        # Task must NOT be VERIFIED
        t = await task_mgr.get_task("m-2", "t-2")
        assert t is not None
        assert t.status != TaskStatus.VERIFIED


# ============================================================================
# TEST 3: OUT-OF-SCOPE CHANGE (REJECT)
# ============================================================================

@pytest.mark.asyncio
async def test_verification_out_of_scope_change():
    """
    Agent modifies an allowed file and an unauthorized out-of-scope file.
    Verifier must produce REJECT due to scope check failure.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        # Create files
        (ws / "auth.py").write_text("ok", encoding="utf-8")
        (ws / "forbidden_billing.py").write_text("pwned", encoding="utf-8")

        db = DatabaseManager(db_path=os.path.join(tmp_dir, "test.db"))
        mission_repo, task_repo = await _seed_mission_and_task(db, "m-3", "t-3", tmp_dir)
        ver_repo = VerificationRepository(db)
        bus = EventBus()

        engine = VerificationEngine(event_bus=bus, repository=ver_repo)

        context = VerificationContext(
            mission_id="m-3",
            task_id="t-3",
            workspace=tmp_dir,
            allowed_files=["auth.py"],
            completion_claim={"changed_files": ["auth.py", "forbidden_billing.py"]},
        )

        result = await engine.verify(context)

        assert result.decision == VerificationDecision.REJECT
        assert "check_scope" in result.failed_checks
        assert "forbidden_billing.py" in str(result.evidence)


# ============================================================================
# TEST 4: INSUFFICIENT ACCEPTANCE CRITERIA (REQUIRE_REVIEW)
# ============================================================================

@pytest.mark.asyncio
async def test_verification_insufficient_criteria_requires_review():
    """
    When a task has no test requirements, no expected files, and no allowed files,
    it cannot be mechanically certified. Verifier must produce REQUIRE_REVIEW.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db = DatabaseManager(db_path=os.path.join(tmp_dir, "test.db"))
        mission_repo, task_repo = await _seed_mission_and_task(db, "m-4", "t-4", tmp_dir)
        ver_repo = VerificationRepository(db)
        bus = EventBus()

        engine = VerificationEngine(event_bus=bus, repository=ver_repo)

        context = VerificationContext(
            mission_id="m-4",
            task_id="t-4",
            workspace=tmp_dir,
            allowed_files=[],
            expected_files=[],
            verification_requirements=[],
            completion_claim={"summary": "I improved code readability."},
        )

        result = await engine.verify(context)

        assert result.decision == VerificationDecision.REQUIRE_REVIEW
        assert result.status == "REVIEW_REQUIRED"
        assert len(result.warnings) > 0


# ============================================================================
# TEST 5: PERSISTENCE SURVIVES RESTART
# ============================================================================

@pytest.mark.asyncio
async def test_verification_survives_process_restart():
    """
    Verification records must be durably stored in SQLite WAL tables and
    remain retrievable after database reload.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "durable.db")

        # Session 1: Run verification and persist
        db1 = DatabaseManager(db_path=db_path)
        mission_repo1, _ = await _seed_mission_and_task(db1, "m-persist", "t-persist", tmp_dir)
        ver_repo1 = VerificationRepository(db1)

        engine1 = VerificationEngine(repository=ver_repo1)
        context = VerificationContext(
            mission_id="m-persist",
            task_id="t-persist",
            workspace=tmp_dir,
            allowed_files=["*"],
            completion_claim={"summary": "Done"},
        )
        res1 = await engine1.verify(context)
        vid = res1.verification_id

        # Session 2: Fresh database instance simulating process restart
        db2 = DatabaseManager(db_path=db_path)
        ver_repo2 = VerificationRepository(db2)

        loaded = await ver_repo2.get(vid)
        assert loaded is not None
        assert loaded["verification_id"] == vid
        assert loaded["mission_id"] == "m-persist"
        assert loaded["task_id"] == "t-persist"
        assert loaded["details"]["decision"] == res1.decision.value

        by_task = await ver_repo2.list_by_task("t-persist")
        assert len(by_task) == 1
        assert by_task[0]["verification_id"] == vid


# ============================================================================
# TEST 6: MALFORMED CONTEXT HANDLED SAFELY
# ============================================================================

@pytest.mark.asyncio
async def test_verification_malformed_context_handled_safely():
    """
    Non-existent workspace or invalid context must degrade safely to REJECT
    without unhandled crashes.
    """
    engine = VerificationEngine()
    context = VerificationContext(
        mission_id="m-bad",
        task_id="t-bad",
        workspace="/path/that/does/not/exist/anywhere",
        verification_requirements=["pytest"],
    )

    result = await engine.verify(context)
    assert result.decision == VerificationDecision.REJECT
    assert "check_git_workspace" in result.failed_checks


# ============================================================================
# TEST 7: TEST TIMEOUT ENFORCEMENT
# ============================================================================

@pytest.mark.asyncio
async def test_verification_test_timeout_triggers_reject():
    """
    When verification test commands exceed the allocated timeout,
    verifier must fail the check and REJECT the claim (never ACCEPT).
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        # Create hanging test
        hang_script = ws / "hang.py"
        hang_script.write_text("import time; time.sleep(10)\n", encoding="utf-8")

        engine = VerificationEngine()
        context = VerificationContext(
            mission_id="m-timeout",
            task_id="t-timeout",
            workspace=tmp_dir,
            allowed_files=["hang.py"],
            verification_requirements=[f"python {hang_script.name}"],
            timeout=0.1,  # 100ms timeout
        )

        result = await engine.verify(context)

        assert result.decision == VerificationDecision.REJECT
        assert "check_tests" in result.failed_checks
        assert "timed out" in str(result.evidence)


# ============================================================================
# TEST 8: REGRESSION DETECTION
# ============================================================================

@pytest.mark.asyncio
async def test_verification_regression_detection():
    """
    When baseline shows a test was previously passing, but it now fails,
    verifier must report regression failure and produce REJECT.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        test_file = ws / "test_reg.py"
        test_file.write_text("def test_login(): assert False, 'regressed'\n", encoding="utf-8")

        engine = VerificationEngine()
        context = VerificationContext(
            mission_id="m-reg",
            task_id="t-reg",
            workspace=tmp_dir,
            allowed_files=["test_reg.py"],
            verification_requirements=[f"python -m pytest {test_file.name}"],
            baseline_test_results={
                "passed_tests": ["test_login"],
                "failed_tests": [],
            },
        )

        result = await engine.verify(context)

        assert result.decision == VerificationDecision.REJECT
        assert "check_tests" in result.failed_checks


# ============================================================================
# TEST 9: MISSING EXPECTED FILES
# ============================================================================

@pytest.mark.asyncio
async def test_verification_missing_expected_files():
    """
    If task specifies expected output files that were not created,
    verifier must produce REJECT.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = VerificationEngine()
        context = VerificationContext(
            mission_id="m-exp",
            task_id="t-exp",
            workspace=tmp_dir,
            allowed_files=["*"],
            expected_files=["dist/bundle.js"],
        )

        result = await engine.verify(context)

        assert result.decision == VerificationDecision.REJECT
        assert "check_scope" in result.failed_checks
        assert "missing" in str(result.evidence)


# ============================================================================
# TEST 10: PATH TRAVERSAL VIOLATION
# ============================================================================

@pytest.mark.asyncio
async def test_verification_path_traversal_violation():
    """
    Attempting to modify files via path traversal ('../') must be flagged as a scope violation.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = VerificationEngine()
        context = VerificationContext(
            mission_id="m-trav",
            task_id="t-trav",
            workspace=tmp_dir,
            allowed_files=["*"],
            completion_claim={"changed_files": ["../../etc/shadow"]},
        )

        result = await engine.verify(context)

        assert result.decision == VerificationDecision.REJECT
        assert "check_scope" in result.failed_checks
        assert "traversal" in str(result.evidence).lower()


# ============================================================================
# TEST 11: PROTECTED FILE VIOLATION
# ============================================================================

@pytest.mark.asyncio
async def test_verification_protected_file_violation():
    """
    Modifying protected system/secret files (.env, .git) must be rejected.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = VerificationEngine()
        context = VerificationContext(
            mission_id="m-prot",
            task_id="t-prot",
            workspace=tmp_dir,
            allowed_files=["*"],
            completion_claim={"changed_files": [".env"]},
        )

        result = await engine.verify(context)

        assert result.decision == VerificationDecision.REJECT
        assert "check_scope" in result.failed_checks
        assert "protected" in str(result.evidence).lower()


# ============================================================================
# TEST 12: KILLER END-TO-END SCENARIO
# ============================================================================

@pytest.mark.asyncio
async def test_killer_scenario_agent_claims_fix_but_verification_proves_failure():
    """
    KILLER SCENARIO:
    Mission: Fix authentication tests
    Task: Repair authentication test failures
    Agent: Claude Code (deterministic fake)

    Agent performs an edit and emits 'task.completed'.
    Agent claims: "Authentication tests are fixed."
    However, the test suite still has a failing test!

    The Supervisor:
    1. Receives completion claim.
    2. Runs independent VerificationEngine.
    3. Executes tests in isolated worktree.
    4. Observes test failure.
    5. Produces REJECT decision.
    6. Persists verification report to SQLite.
    7. Emits verification.failed event.
    8. Enforces that task is NOT marked VERIFIED.

    Killer assertion:
    agent_claimed_success == True
    verified_success == False
    verification.decision == REJECT
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)

        # 1. Setup repository with failing authentication test
        auth_src = ws / "auth.py"
        auth_src.write_text(
            "def authenticate(token):\n"
            "    # Agent made an incomplete fix\n"
            "    if token == 'valid_token':\n"
            "        return {'status': 200, 'user': 'alice'}\n"
            "    return {'status': 401}\n",
            encoding="utf-8",
        )

        auth_test = ws / "test_auth.py"
        auth_test.write_text(
            "from auth import authenticate\n\n"
            "def test_valid_token():\n"
            "    res = authenticate('valid_token')\n"
            "    assert res['status'] == 200\n\n"
            "def test_token_expiry():\n"
            "    # This test still fails!\n"
            "    res = authenticate('expired_token')\n"
            "    assert res['status'] == 403, 'Expected 403 Forbidden for expired token'\n",
            encoding="utf-8",
        )

        # 2. Database and Task infrastructure
        db = DatabaseManager(db_path=os.path.join(tmp_dir, "scenario.db"))
        mission_id = "mission-auth-killer"
        task_id = "task-auth-killer"
        mission_repo, task_repo = await _seed_mission_and_task(db, mission_id, task_id, tmp_dir)
        ver_repo = VerificationRepository(db)

        bus = EventBus()
        events_emitted: List[Event] = []
        bus.subscribe_sync(events_emitted.append)

        task_mgr = TaskManager(event_bus=bus, repository=task_repo)
        task = Task(
            id=task_id,
            mission_id=mission_id,
            title="Repair authentication test failures",
            expected_files=["auth.py"],
        )
        await task_mgr.initialize_mission_tasks(mission_id, [task])
        await task_mgr.start_task(mission_id, task_id, agent_id="claude_code")

        # 3. Agent claims task is completed
        agent_claimed_success = True
        claim_summary = "Authentication tests are fixed and passing."
        await task_mgr.complete_task(mission_id, task_id, summary=claim_summary)

        # Task is currently in COMPLETED status (claimed by worker)
        task_pre_ver = await task_mgr.get_task(mission_id, task_id)
        assert task_pre_ver is not None
        assert task_pre_ver.status == TaskStatus.COMPLETED

        # 4. Supervisor Independent Verification Engine triggers
        engine = VerificationEngine(
            event_bus=bus,
            repository=ver_repo,
            task_manager=task_mgr,
        )

        dispatch = TaskDispatchPackage(
            task_id=task_id,
            mission_id=mission_id,
            objective="Fix authentication test failures",
            workspace=tmp_dir,
            allowed_files=["auth.py", "test_auth.py"],
            verification_requirements=[f"python -m pytest {auth_test.name}"],
        )

        result = await engine.verify_dispatch(
            dispatch=dispatch,
            completion_claim={
                "summary": claim_summary,
                "claimed_success": True,
                "changed_files": ["auth.py"],
            },
        )

        # 5. Core Invariant Validation:
        # Agent claimed success, but independent verification proved failure!
        verified_success = (result.decision == VerificationDecision.ACCEPT)

        assert agent_claimed_success is True
        assert verified_success is False
        assert result.decision == VerificationDecision.REJECT
        assert result.status == "FAILED"
        assert "check_tests" in result.failed_checks

        # 6. Task State Integration:
        # The task must NOT be marked VERIFIED. It was reopened due to empirical rejection!
        task_post_ver = await task_mgr.get_task(mission_id, task_id)
        assert task_post_ver is not None
        assert task_post_ver.status != TaskStatus.VERIFIED
        assert task_post_ver.status == TaskStatus.IN_PROGRESS  # Reopened by TaskManager

        # 7. Persistence Validation:
        stored_verifications = await ver_repo.list_by_task(task_id)
        assert len(stored_verifications) == 1
        assert stored_verifications[0]["status"] == "FAILED"
        assert stored_verifications[0]["details"]["decision"] == "REJECT"

        # 8. Event Stream Validation:
        event_types = [e.type for e in events_emitted]
        assert EventType.VERIFICATION_STARTED in event_types
        assert EventType.VERIFICATION_FAILED in event_types
        assert EventType.TASK_REOPENED in event_types
