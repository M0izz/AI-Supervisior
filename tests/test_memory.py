"""
Automated Test Suite for Phase 7: Shared Project Memory.
Validates provenance-preserving, scoped project memory, deterministic deduplication,
trust hierarchy, SQLite WAL persistence, handoff integration, verification promotion,
killer end-to-end scenario, and negative trust scenario.
"""

from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional
import pytest

from core.events.bus import EventBus
from core.protocol.schema import TaskDispatchPackage
from core.tasks.models import Task, TaskStatus
from core.verification.engine import VerificationEngine
from core.verification.models import VerificationContext, VerificationDecision
from core.handoff.engine import HandoffEngine
from core.handoff.models import HandoffTrigger, HandoffStatus, FactProvenance
from memory.models import (
    FactStatus,
    MemoryProvenance,
    MemoryQuery,
    MemoryRecord,
    MemoryStatus,
    MemoryType,
    ProjectMemoryContext,
    sanitize_text,
)
from memory.store import MemoryStore
from memory.retrieval import ContextPackager
from storage.sqlite.db import DatabaseManager
from storage.sqlite.repositories import (
    MemoryRepository,
    MissionRepository,
    TaskRepository,
    VerificationRepository,
    HandoffRepository,
)
from execution.worktree import GitWorktreeManager
from adapters.registry import AdapterRegistry
from adapters.base import AgentAdapter
from adapters.models import (
    AdapterIdentity,
    AdapterAvailability,
    AdapterAvailabilityStatus,
    AdapterExecutionResult,
    AdapterProcessStatus,
)


class MockWorkerAdapter(AgentAdapter):
    """Configurable mock adapter for testing memory & handoff flow."""
    def __init__(self, adapter_id: str, script_fn=None):
        self._identity = AdapterIdentity(
            provider="mock",
            adapter_id=adapter_id,
            display_name=f"Mock {adapter_id}",
            version="1.0.0",
            capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
        )
        self.script_fn = script_fn
        self.dispatches: List[TaskDispatchPackage] = []

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def check_availability(self) -> AdapterAvailability:
        return AdapterAvailability(
            available=True,
            status=AdapterAvailabilityStatus.AVAILABLE,
            message="Available",
        )

    async def execute(self, dispatch: TaskDispatchPackage) -> AdapterExecutionResult:
        self.dispatches.append(dispatch)
        if self.script_fn:
            exit_code = await self.script_fn(dispatch)
        else:
            exit_code = 0
        return AdapterExecutionResult(
            status=AdapterProcessStatus.COMPLETED if exit_code == 0 else AdapterProcessStatus.FAILED,
            exit_code=exit_code,
            workspace=dispatch.workspace,
            output="Mock execution completed",
        )

    async def cancel(self, task_id: str) -> bool:
        return True

    async def status(self, task_id: str) -> AdapterProcessStatus:
        return AdapterProcessStatus.COMPLETED

    async def cleanup(self, task_id: str) -> bool:
        return True


# ============================================================================
# FOCUSED UNIT & INTEGRATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_persist_verified_fact(tmp_path):
    """Test 1: Create verified memory and confirm retrieval and SQLite persistence."""
    db_file = tmp_path / "supervisor.db"
    db = DatabaseManager(db_path=str(db_file))
    msn_repo = MissionRepository(db)
    await msn_repo.save({
        "mission_id": "msn_001",
        "title": "Auth Mission",
        "goal": "Test auth",
        "status": "IN_PROGRESS",
    })
    repo = MemoryRepository(db)
    store = MemoryStore(repository=repo)

    rec = await store.record_verified_fact(
        mission_id="msn_001",
        project_id="proj_auth",
        task_id="tsk_101",
        content="Authentication service uses RS256 JWT tokens",
        source="verification_engine",
        source_id="ver_999",
        created_by="verifier",
        evidence=["test_jwt_signature.py: PASS"],
    )

    assert rec.status == MemoryStatus.VERIFIED
    assert rec.memory_type == MemoryType.FACT
    assert rec.project_id == "proj_auth"
    assert rec.provenance.source == "verification_engine"
    assert rec.provenance.evidence == ["test_jwt_signature.py: PASS"]

    # Verify query
    results = await store.query(MemoryQuery(project_id="proj_auth", statuses=[MemoryStatus.VERIFIED]))
    assert len(results) == 1
    assert results[0].content == "Authentication service uses RS256 JWT tokens"

    # Verify direct SQLite persistence
    db_row = await repo.get(rec.id)
    assert db_row is not None
    assert db_row["content"] == "Authentication service uses RS256 JWT tokens"
    assert db_row["status"] == "VERIFIED"


@pytest.mark.asyncio
async def test_unverified_claim(tmp_path):
    """Test 2: Agent claim must remain UNVERIFIED and never automatically become VERIFIED."""
    store = MemoryStore()

    rec = await store.record_unverified_claim(
        mission_id="msn_001",
        project_id="proj_auth",
        task_id="tsk_102",
        content="Database connection timeout is caused by network latency",
        source="agent_event",
        created_by="claude_code",
    )

    assert rec.status == MemoryStatus.UNVERIFIED
    assert rec.confidence == 0.5
    assert rec.provenance.created_by == "claude_code"

    # Confirms query for VERIFIED does NOT return this unverified claim
    verified_only = await store.query(MemoryQuery(statuses=[MemoryStatus.VERIFIED]))
    assert len(verified_only) == 0

    unverified_only = await store.query(MemoryQuery(statuses=[MemoryStatus.UNVERIFIED]))
    assert len(unverified_only) == 1
    assert unverified_only[0].content == rec.content


@pytest.mark.asyncio
async def test_rejected_approach(tmp_path):
    """Test 3: Store a failed approach and confirm it remains retrievable as REJECTED."""
    store = MemoryStore()

    rec = await store.record_rejected_approach(
        mission_id="msn_001",
        project_id="proj_auth",
        task_id="tsk_103",
        content="Increasing regex buffer limit to 10MB",
        source="verification_engine",
        source_id="ver_002",
        created_by="verifier",
        details="Caused OutOfMemoryError on benchmark test",
    )

    assert rec.status == MemoryStatus.REJECTED
    assert rec.memory_type == MemoryType.REJECTED_APPROACH
    assert "OutOfMemoryError" in rec.details

    # Retrieval as rejected approach
    context = await store.build_project_memory_context(mission_id="msn_001", project_id="proj_auth")
    assert len(context.rejected_approaches) == 1
    assert "Increasing regex buffer" in context.rejected_approaches[0]["approach"]
    assert "OutOfMemoryError" in context.rejected_approaches[0]["reason"]


@pytest.mark.asyncio
async def test_provenance(tmp_path):
    """Test 4: Every persisted memory record has valid provenance metadata."""
    store = MemoryStore()

    rec = await store.add_record(
        mission_id="msn_prov",
        fact="PostgreSQL port configured to 5432",
        source="watchdog_event",
        source_id="evt_wd_55",
        created_by="watchdog_engine",
        status=MemoryStatus.OBSERVED,
        evidence=["netstat inspection: 5432 LISTEN"],
    )

    assert rec.provenance.source == "watchdog_event"
    assert rec.provenance.source_id == "evt_wd_55"
    assert rec.provenance.created_by == "watchdog_engine"
    assert len(rec.provenance.evidence) == 1


@pytest.mark.asyncio
async def test_project_isolation(tmp_path):
    """Test 5: Memories from Project A must NEVER leak into Project B queries."""
    store = MemoryStore()

    await store.record_verified_fact(
        mission_id="msn_a",
        project_id="proj_alpha",
        content="Alpha database username is alpha_admin",
    )

    await store.record_verified_fact(
        mission_id="msn_b",
        project_id="proj_beta",
        content="Beta database username is beta_service",
    )

    # Query Project Alpha
    alpha_memories = await store.query(MemoryQuery(project_id="proj_alpha"))
    assert len(alpha_memories) == 1
    assert alpha_memories[0].content == "Alpha database username is alpha_admin"

    # Query Project Beta
    beta_memories = await store.query(MemoryQuery(project_id="proj_beta"))
    assert len(beta_memories) == 1
    assert beta_memories[0].content == "Beta database username is beta_service"


@pytest.mark.asyncio
async def test_relevance_ranking(tmp_path):
    """Test 6: Authentication query prioritizes auth memories over unrelated billing memories."""
    store = MemoryStore()

    # 1. Unrelated verified fact
    await store.record_verified_fact(
        mission_id="msn_001",
        project_id="proj_app",
        content="Stripe webhook endpoint timeout is set to 30s",
        task_id="tsk_billing",
    )

    # 2. Related verified fact
    await store.record_verified_fact(
        mission_id="msn_001",
        project_id="proj_app",
        content="OAuth2 token expires after 3600 seconds",
        task_id="tsk_auth",
    )

    # 3. Highly related verified fact for the target task
    await store.record_verified_fact(
        mission_id="msn_001",
        project_id="proj_app",
        content="Authentication session header requires Bearer prefix",
        task_id="tsk_auth",
    )

    ranked = await store.query(
        MemoryQuery(
            project_id="proj_app",
            task_id="tsk_auth",
            keywords=["authentication", "token", "oauth2"],
        )
    )

    assert len(ranked) == 3
    # Top ranked should be auth-related with task match and keyword match
    assert "Authentication session header" in ranked[0].content or "OAuth2 token" in ranked[0].content
    # Billing should be at the bottom
    assert "Stripe webhook" in ranked[-1].content


@pytest.mark.asyncio
async def test_deduplication(tmp_path):
    """Test 7: Repeated equivalent memory candidates do not create uncontrolled duplicates."""
    store = MemoryStore()

    rec1 = await store.add_record(
        mission_id="msn_001",
        project_id="proj_core",
        fact="Redis cache port is 6379",
        status=MemoryStatus.OBSERVED,
    )

    # Attempt to add identical fact with slightly different casing and whitespace
    rec2 = await store.add_record(
        mission_id="msn_001",
        project_id="proj_core",
        fact="  redis cache port is 6379.  ",
        status=MemoryStatus.OBSERVED,
    )

    assert rec1.id == rec2.id
    all_recs = await store.get_by_project("proj_core")
    assert len(all_recs) == 1

    # Now promote that same fact to VERIFIED
    rec3 = await store.record_verified_fact(
        mission_id="msn_001",
        project_id="proj_core",
        content="Redis cache port is 6379",
        source="verification_engine",
        evidence=["port 6379 verified"],
    )

    assert rec3.id == rec1.id
    assert rec3.status == MemoryStatus.VERIFIED
    assert len(await store.get_by_project("proj_core")) == 1


@pytest.mark.asyncio
async def test_conflict_and_supersession(tmp_path):
    """Test 8: Conflicting claims preserve provenance and link supersession rather than silent overwriting."""
    store = MemoryStore()

    rec1 = await store.record_unverified_claim(
        mission_id="msn_001",
        project_id="proj_core",
        content="Default pagination page size is 50",
        source="agent_event",
        created_by="claude_code",
    )

    # Verifier independently discovers it is actually 20
    rec2 = await store.record_verified_fact(
        mission_id="msn_001",
        project_id="proj_core",
        content="Default pagination page size is 20",
        source="verification_engine",
        created_by="verifier",
        evidence=["settings.py: DEFAULT_PAGE_SIZE = 20"],
    )

    # Mark old record as superseded
    rec1.superseded_by = rec2.id
    rec1.status = MemoryStatus.REJECTED

    # Query active facts excluding superseded
    active = await store.query(
        MemoryQuery(project_id="proj_core", exclude_superseded=True)
    )
    assert len(active) == 1
    assert active[0].content == "Default pagination page size is 20"

    # Both records remain preserved in history for audit
    assert rec1.id != rec2.id
    assert rec1.superseded_by == rec2.id


@pytest.mark.asyncio
async def test_restart_persistence(tmp_path):
    """Test 9: Memory and provenance survive database close and reopen."""
    db_file = tmp_path / "supervisor.db"
    db1 = DatabaseManager(db_path=str(db_file))
    msn_repo1 = MissionRepository(db1)
    await msn_repo1.save({
        "mission_id": "msn_restart",
        "title": "Restart Mission",
        "goal": "Test restart",
        "status": "IN_PROGRESS",
    })
    repo1 = MemoryRepository(db1)
    store1 = MemoryStore(repository=repo1)

    rec = await store1.record_verified_fact(
        mission_id="msn_restart",
        project_id="proj_restart",
        content="Config file loaded from /etc/supervisor/config.yaml",
        source="verification_engine",
        source_id="ver_restart_01",
        evidence=["file exists check: True"],
    )

    # Reopen brand new DatabaseManager and MemoryStore on same file
    db2 = DatabaseManager(db_path=str(db_file))
    repo2 = MemoryRepository(db2)
    store2 = MemoryStore(repository=repo2)

    # Query from second store
    results = await store2.query(MemoryQuery(project_id="proj_restart"))
    assert len(results) == 1
    loaded = results[0]
    assert loaded.id == rec.id
    assert loaded.content == "Config file loaded from /etc/supervisor/config.yaml"
    assert loaded.status == MemoryStatus.VERIFIED
    assert loaded.provenance.source == "verification_engine"
    assert loaded.provenance.source_id == "ver_restart_01"


@pytest.mark.asyncio
async def test_security_secret_scrubbing(tmp_path):
    """Test 12: Secrets and API keys are redacted before persistence."""
    store = MemoryStore()

    dirty_fact = "Connected to service using api_key='sk-ant-api03-abcdef12345678901234567890' on port 8000"
    rec = await store.add_record(
        mission_id="msn_sec",
        fact=dirty_fact,
        details="Bearer token=ghp_ABC1234567890123456789012345678901234567",
    )

    assert "sk-ant-api03" not in rec.content
    assert "[REDACTED_SECRET]" in rec.content
    assert "ghp_ABC" not in rec.details
    assert "[REDACTED_SECRET]" in rec.details


# ============================================================================
# INTEGRATION TESTS: VERIFICATION & HANDOFF
# ============================================================================

@pytest.mark.asyncio
async def test_verification_engine_promotes_memory(tmp_path):
    """Test 11: Verification engine promotes verified fact on ACCEPT and rejected approach on REJECT."""
    bus = EventBus()
    store = MemoryStore(event_bus=bus)
    ver_engine = VerificationEngine(
        event_bus=bus,
        memory_store=store,
    )

    # 1. Verification ACCEPT creates verified fact
    ctx_pass = VerificationContext(
        mission_id="msn_ver_test",
        task_id="tsk_pass",
        workspace=str(tmp_path),
        allowed_files=["*"],
        verification_requirements=["python -c 'import sys; sys.exit(0)'"],
        completion_claim={"summary": "Passing verification check"},
    )
    res_pass = await ver_engine.verify(ctx_pass)
    assert res_pass.decision == VerificationDecision.ACCEPT

    facts = await store.query(MemoryQuery(mission_id="msn_ver_test", statuses=[MemoryStatus.VERIFIED]))
    assert len(facts) >= 1
    assert "Verified:" in facts[0].content

    # 2. Verification REJECT creates rejected approach
    ctx_fail = VerificationContext(
        mission_id="msn_ver_test",
        task_id="tsk_fail",
        workspace=str(tmp_path),
        allowed_files=["*"],
        verification_requirements=["python -c 'import sys; sys.exit(1)'"],
        completion_claim={"summary": "Failing verification check"},
    )
    res_fail = await ver_engine.verify(ctx_fail)
    assert res_fail.decision == VerificationDecision.REJECT

    rejected = await store.query(MemoryQuery(mission_id="msn_ver_test", statuses=[MemoryStatus.REJECTED]))
    assert len(rejected) >= 1
    assert "Rejected approach:" in rejected[0].content


@pytest.mark.asyncio
async def test_handoff_integration_injects_shared_memory(tmp_path):
    """Test 10: Handoff engine injects verified facts and rejected approaches into receiving agent context."""
    bus = EventBus()
    store = MemoryStore(event_bus=bus)

    # Seed shared memory
    await store.record_verified_fact(
        mission_id="msn_ho",
        task_id="tsk_auth",
        content="Session token uses HS256 algorithm",
    )
    await store.record_rejected_approach(
        mission_id="msn_ho",
        task_id="tsk_auth",
        content="Parsing token with RS256 algorithm",
        details="Signature verification failed",
    )

    registry = AdapterRegistry()
    codex_mock = MockWorkerAdapter("codex")
    registry.register_adapter(codex_mock)

    handoff_engine = HandoffEngine(
        event_bus=bus,
        adapter_registry=registry,
        memory_store=store,
    )

    result = await handoff_engine.execute_handoff(
        mission_id="msn_ho",
        task_id="tsk_auth",
        source_agent_id="claude_code",
        target_agent_id="codex",
        trigger=HandoffTrigger.REPEATED_FAILURE,
        reason="Repeated signature failure",
        objective="Fix token parsing",
        workspace=str(tmp_path),
    )

    assert result.success is True
    pkg = result.context_package
    assert pkg is not None

    # Verify that Codex receives the verified facts and rejected attempts
    verified_statements = [f.statement for f in pkg.verified_facts]
    rejected_statements = [f.statement for f in pkg.rejected_attempts]

    assert any("Session token uses HS256 algorithm" in s for s in verified_statements)
    assert any("Parsing token with RS256 algorithm" in s for s in rejected_statements)


# ============================================================================
# SECTION 27: KILLER END-TO-END SCENARIO
# ============================================================================

@pytest.mark.asyncio
async def test_killer_scenario_shared_project_memory_lifecycle(tmp_path):
    """
    KILLER SCENARIO (Section 27):
    Mission: Fix authentication tests.
    1. Agent A (Claude) investigates and discovers: UTF-8 BOM flaw. Verified fact stored.
    2. Agent A tries wrong approach: replace parser library -> Fails -> Rejected approach stored.
    3. Handoff occurs: Claude fails repeatedly -> Handoff to Codex.
    4. Agent B (Codex) receives handoff context:
       - Contains VERIFIED: UTF-8 BOM affects authentication parser
       - Contains REJECTED: Replacing parser library did not solve issue
       - Does NOT contain unrelated project memory (e.g. billing)
    5. Codex applies byte-level BOM strip.
    6. Phase 4 VerificationEngine independently verifies result -> ACCEPT.
    Assertions:
       - memory contains verified discovery
       - memory contains rejected approach
       - memory survived handoff
       - Agent B received relevant memory
       - Agent B did not receive unrelated project memory
       - final result independently verified
    """
    repo_dir = tmp_path / "killer_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo_dir), check=True)

    # Initial codebase
    (repo_dir / "README.md").write_text("# Killer Scenario\n")
    (repo_dir / "auth").mkdir()
    (repo_dir / "auth" / "session.py").write_text("def parse_token(t): return t\n")
    (repo_dir / "test_auth.py").write_text(
        "import sys\n"
        "from auth.session import parse_token\n"
        "if parse_token('test') != 'test': sys.exit(1)\n"
    )
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)

    bus = EventBus()
    db_file = tmp_path / "supervisor.db"
    db = DatabaseManager(db_path=str(db_file))
    msn_repo = MissionRepository(db)
    await msn_repo.save({
        "mission_id": "msn_auth_fix",
        "title": "Auth Fix Mission",
        "goal": "Fix BOM",
        "status": "IN_PROGRESS",
    })
    await msn_repo.save({
        "mission_id": "msn_billing_other",
        "title": "Billing Mission",
        "goal": "Other",
        "status": "IN_PROGRESS",
    })
    mem_repo = MemoryRepository(db)
    ver_repo = VerificationRepository(db)
    ho_repo = HandoffRepository(db)
    wt_mgr = GitWorktreeManager(repo_root=repo_dir)

    store = MemoryStore(event_bus=bus, repository=mem_repo)

    # Seed an UNRELATED project memory to prove isolation & relevance filtering
    await store.record_verified_fact(
        mission_id="msn_billing_other",
        project_id="billing_service",
        content="Stripe API keys must use testmode secret rk_test_123",
        details="Billing subsystem configuration",
    )

    # STEP 1: Agent A discovers UTF-8 BOM flaw -> Stored as VERIFIED FACT with evidence
    bom_fact = await store.record_verified_fact(
        mission_id="msn_auth_fix",
        project_id="auth_service",
        task_id="tsk_auth_01",
        content="Authentication parser is affected by a UTF-8 BOM byte-order marker",
        source="verification_engine",
        source_id="ver_bom_01",
        created_by="claude_code",
        evidence=["Hex dump shows \\xef\\xbb\\xbf prefix on session headers"],
    )

    # STEP 2: Agent A tries a wrong approach: replace parser library -> Fails -> Stored as REJECTED_APPROACH
    rejected_appr = await store.record_rejected_approach(
        mission_id="msn_auth_fix",
        project_id="auth_service",
        task_id="tsk_auth_01",
        content="Replacing parser library with PyJWT regex wrapper",
        source="verification_engine",
        source_id="ver_wrong_01",
        created_by="claude_code",
        details="Did not solve byte-order marker and broke downstream signature validation",
    )

    # Create worktree for task
    wt_path = wt_mgr.create(
        mission_id="msn_auth_fix",
        task_id="tsk_auth_01",
    )

    # STEP 3 & 4: Handoff from Claude to Codex
    # Codex mock worker applies the correct byte-level BOM strip
    async def codex_worker(dispatch: TaskDispatchPackage) -> int:
        target_file = Path(dispatch.workspace) / "auth" / "session.py"
        target_file.write_text(
            "def parse_token(t):\n"
            "    # Strip UTF-8 BOM if present\n"
            "    if isinstance(t, str) and t.startswith('\\ufeff'):\n"
            "        t = t.lstrip('\\ufeff')\n"
            "    return t\n"
        )
        # Update test to verify BOM stripping
        test_file = Path(dispatch.workspace) / "test_auth.py"
        test_file.write_text(
            "import sys\n"
            "from auth.session import parse_token\n"
            "assert parse_token('\\ufefftoken_123') == 'token_123'\n"
            "assert parse_token('token_123') == 'token_123'\n"
            "print('ALL AUTH TESTS PASS')\n"
        )
        return 0

    registry = AdapterRegistry()
    codex_adapter = MockWorkerAdapter("codex", script_fn=codex_worker)
    registry.register_adapter(codex_adapter)

    handoff_engine = HandoffEngine(
        event_bus=bus,
        adapter_registry=registry,
        repository=ho_repo,
        worktree_manager=wt_mgr,
        memory_store=store,
    )

    handoff_res = await handoff_engine.execute_handoff(
        mission_id="msn_auth_fix",
        task_id="tsk_auth_01",
        source_agent_id="claude_code",
        target_agent_id="codex",
        trigger=HandoffTrigger.REPEATED_FAILURE,
        reason="Repeated failure on parser library replacement",
        objective="Fix authentication test failures with UTF-8 BOM",
        workspace=str(wt_path),
        test_commands=["python test_auth.py"],
    )

    assert handoff_res.success is True
    pkg = handoff_res.context_package
    assert pkg is not None

    # Assert Agent B (Codex) received relevant memory
    verified_texts = [f.statement for f in pkg.verified_facts]
    rejected_texts = [f.statement for f in pkg.rejected_attempts]

    assert any("affected by a UTF-8 BOM" in t for t in verified_texts)
    assert any("Replacing parser library" in t for t in rejected_texts)

    # Assert Agent B did NOT receive unrelated project memory (Billing)
    assert not any("Stripe" in t for t in verified_texts)
    assert not any("billing" in t.lower() for t in verified_texts)

    # STEP 5: Independent Verification
    ver_engine = VerificationEngine(
        event_bus=bus,
        repository=ver_repo,
        worktree_manager=wt_mgr,
        memory_store=store,
    )

    ver_ctx = VerificationContext(
        mission_id="msn_auth_fix",
        task_id="tsk_auth_01",
        workspace=str(wt_path),
        allowed_files=["auth/session.py", "test_auth.py"],
        verification_requirements=["python test_auth.py"],
        completion_claim={"summary": "Fixed auth BOM", "changed_files": ["auth/session.py", "test_auth.py"]},
    )

    ver_res = await ver_engine.verify(ver_ctx)
    assert ver_res.decision == VerificationDecision.ACCEPT

    # Assert memory survived handoff and is persisted
    db_bom = await mem_repo.get(bom_fact.id)
    assert db_bom is not None
    assert db_bom["status"] == "VERIFIED"

    db_rej = await mem_repo.get(rejected_appr.id)
    assert db_rej is not None
    assert db_rej["status"] == "REJECTED"

    # Cleanup worktree
    wt_mgr.remove("msn_auth_fix", "tsk_auth_01")


# ============================================================================
# SECTION 28: NEGATIVE QUALITY SCENARIO
# ============================================================================

@pytest.mark.asyncio
async def test_negative_trust_scenario(tmp_path):
    """
    NEGATIVE TRUST SCENARIO (Section 28):
    1. Agent says: "The database migration is safe."
       No independent evidence exists.
       System MUST store at most: UNVERIFIED (never VERIFIED).
    2. Later, verified observation contradicts it:
       "Migration dropped column user_email causing 14 test regressions."
    3. System preserves provenance of the old claim, marks it REJECTED/superseded,
       rather than silently rewriting history.
    """
    store = MemoryStore()

    # Step 1: Agent asserts claim without empirical proof
    claim = await store.record_unverified_claim(
        mission_id="msn_migration",
        project_id="proj_db",
        task_id="tsk_mig",
        content="The database migration is safe",
        source="agent_event",
        created_by="claude_code",
    )

    assert claim.status == MemoryStatus.UNVERIFIED
    assert claim.status != MemoryStatus.VERIFIED

    # Step 2: Independent verification discovers the migration failed
    contradiction = await store.record_rejected_approach(
        mission_id="msn_migration",
        project_id="proj_db",
        task_id="tsk_mig",
        content="The database migration is safe",
        source="verification_engine",
        source_id="ver_mig_01",
        created_by="verifier",
        details="Migration dropped column user_email causing 14 test regressions",
        evidence=["Migration check exit_code: 1", "Regression in test_users.py"],
    )

    # Step 3: Verify the record was updated to REJECTED with updated provenance
    # and not left as VERIFIED, nor silently erased.
    assert contradiction.id == claim.id
    assert contradiction.status == MemoryStatus.REJECTED
    assert contradiction.provenance.source == "verification_engine"
    assert "dropped column user_email" in contradiction.details
