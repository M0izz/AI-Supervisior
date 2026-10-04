import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional
import pytest

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.tasks.manager import TaskManager
from core.tasks.models import Task, TaskStatus
from core.protocol.schema import TaskDispatchPackage
from adapters.models import (
    AdapterIdentity,
    AdapterCapability,
    AdapterAvailability,
    AdapterAvailabilityStatus,
    AdapterProcessStatus,
)
from adapters.base import AgentAdapter
from adapters.registry import AdapterRegistry
from adapters.claude_code import ClaudeCodeAdapter
from adapters.codex import CodexAdapter
from execution.worktree import GitWorktreeManager
from core.routing.models import (
    RoutingDecisionType,
    TaskRequirements,
    RoutingCandidate,
    RoutingRequest,
    RoutingDecision,
)
from core.routing.scorer import RoutingScorer
from core.routing.engine import RoutingEngine
from core.handoff.engine import HandoffEngine
from core.handoff.models import HandoffTrigger, HandoffStatus
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
    RoutingRepository,
)


# ============================================================================
# HELPER TEST ADAPTER
# ============================================================================

class MockConfigurableAdapter(AgentAdapter):
    """Configurable mock adapter for deterministic testing of routing scenarios."""
    def __init__(
        self,
        adapter_id: str,
        capabilities: List[str],
        available: bool = True,
        availability_status: AdapterAvailabilityStatus = AdapterAvailabilityStatus.AVAILABLE,
    ):
        raw_caps = [c.value if isinstance(c, AdapterCapability) else str(c) for c in capabilities]
        self._identity = AdapterIdentity(
            provider="mock",
            adapter_id=adapter_id,
            display_name=f"Mock {adapter_id}",
            version="1.0.0",
            capabilities=raw_caps,
        )
        self._available = available
        self._availability_status = availability_status

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def check_availability(self) -> AdapterAvailability:
        return AdapterAvailability(
            available=self._available,
            status=self._availability_status,
            message="Mock availability status",
        )

    async def prepare(self, dispatch: TaskDispatchPackage) -> bool:
        return True

    async def execute(self, dispatch: TaskDispatchPackage) -> Any:
        pass

    async def cancel(self, task_id: str) -> bool:
        return True

    async def status(self, task_id: str) -> AdapterProcessStatus:
        return AdapterProcessStatus.IDLE

    async def cleanup(self, task_id: str) -> None:
        pass


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
# 1. EXACT CAPABILITY MATCH & MISSING REQUIRED CAPABILITY
# ============================================================================

@pytest.mark.asyncio
async def test_exact_capability_match():
    """Agent satisfying all required capabilities is ROUTE; agent missing some is INELIGIBLE."""
    registry = AdapterRegistry()
    adapter_full = MockConfigurableAdapter(
        adapter_id="full_agent",
        capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
    )
    adapter_partial = MockConfigurableAdapter(
        adapter_id="partial_agent",
        capabilities=["code_execution", "filesystem_write"],  # missing git, test_execution
    )
    registry.register_adapter(adapter_full)
    registry.register_adapter(adapter_partial)

    engine = RoutingEngine(adapter_registry=registry)
    req = RoutingRequest(
        mission_id="msn_cap",
        task_id="tsk_cap",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "filesystem_write", "git", "test_execution"]
        ),
    )

    decision = await engine.route(req)
    assert decision.decision == RoutingDecisionType.ROUTE
    assert decision.selected_agent_id == "full_agent"

    # Verify candidate breakdowns
    cand_partial = next(c for c in decision.candidates if c.agent_id == "partial_agent")
    assert cand_partial.is_eligible is False
    assert any("Missing required capabilities" in r for r in cand_partial.ineligibility_reasons)


@pytest.mark.asyncio
async def test_missing_required_capability_ineligible_despite_high_history():
    """Candidate lacking one required capability is INELIGIBLE even with stellar historical performance."""
    registry = AdapterRegistry()
    adapter_no_git = MockConfigurableAdapter(
        adapter_id="experienced_but_missing_git",
        capabilities=["code_execution", "filesystem_write", "test_execution"],
    )
    registry.register_adapter(adapter_no_git)

    engine = RoutingEngine(adapter_registry=registry)
    req = RoutingRequest(
        mission_id="msn_gate",
        task_id="tsk_gate",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "filesystem_write", "git"]
        ),
        context={
            "historical_metrics": {
                "experienced_but_missing_git": {
                    "verified_successes": 50,
                    "verification_failures": 0,
                }
            }
        },
    )

    decision = await engine.route(req)
    assert decision.decision == RoutingDecisionType.NO_ELIGIBLE_AGENT
    assert decision.selected_agent_id is None
    cand = decision.candidates[0]
    assert cand.is_eligible is False
    assert cand.score == 0.0


# ============================================================================
# 2. PREFERRED CAPABILITY SCORING
# ============================================================================

@pytest.mark.asyncio
async def test_preferred_capability_scoring():
    """When both satisfy required capabilities, the one with preferred capabilities wins."""
    registry = AdapterRegistry()
    claude = MockConfigurableAdapter(
        adapter_id="claude_code",
        capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
    )
    codex = MockConfigurableAdapter(
        adapter_id="codex",
        capabilities=["code_execution", "filesystem_write", "git", "test_execution", "terminal_execution"],
    )
    registry.register_adapter(claude)
    registry.register_adapter(codex)

    engine = RoutingEngine(adapter_registry=registry)
    req = RoutingRequest(
        mission_id="msn_pref",
        task_id="tsk_pref",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
            preferred_capabilities=["terminal_execution"],
        ),
    )

    decision = await engine.route(req)
    assert decision.decision == RoutingDecisionType.ROUTE
    assert decision.selected_agent_id == "codex"
    cand_codex = next(c for c in decision.candidates if c.agent_id == "codex")
    cand_claude = next(c for c in decision.candidates if c.agent_id == "claude_code")
    assert cand_codex.score > cand_claude.score
    assert cand_codex.score_breakdown["preferred_capability_match"] == 2.0
    assert cand_claude.score_breakdown["preferred_capability_match"] == 0.0


# ============================================================================
# 3. UNAVAILABILITY & COLD START
# ============================================================================

@pytest.mark.asyncio
async def test_unavailable_agent_not_selected():
    """Agent with matching capabilities is not selected if check_availability returns False."""
    registry = AdapterRegistry()
    unavail_expert = MockConfigurableAdapter(
        adapter_id="expert_offline",
        capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
        available=False,
        availability_status=AdapterAvailabilityStatus.NOT_INSTALLED,
    )
    avail_fallback = MockConfigurableAdapter(
        adapter_id="fallback_online",
        capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
        available=True,
    )
    registry.register_adapter(unavail_expert)
    registry.register_adapter(avail_fallback)

    engine = RoutingEngine(adapter_registry=registry)
    req = RoutingRequest(
        mission_id="msn_unavail",
        task_id="tsk_unavail",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "filesystem_write"]
        ),
    )

    decision = await engine.route(req)
    assert decision.decision == RoutingDecisionType.ROUTE
    assert decision.selected_agent_id == "fallback_online"
    cand_offline = next(c for c in decision.candidates if c.agent_id == "expert_offline")
    assert cand_offline.is_eligible is False
    assert any("unavailable" in r.lower() for r in cand_offline.ineligibility_reasons)


@pytest.mark.asyncio
async def test_cold_start_agent_routable():
    """Agent with 0 historical tasks receives neutral (0.0) reliability and is fully routable."""
    registry = AdapterRegistry()
    new_agent = MockConfigurableAdapter(
        adapter_id="new_agent_cold_start",
        capabilities=["code_execution", "filesystem_write"],
        available=True,
    )
    registry.register_adapter(new_agent)

    engine = RoutingEngine(adapter_registry=registry)
    req = RoutingRequest(
        mission_id="msn_cold",
        task_id="tsk_cold",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "filesystem_write"]
        ),
    )

    decision = await engine.route(req)
    assert decision.decision == RoutingDecisionType.ROUTE
    assert decision.selected_agent_id == "new_agent_cold_start"
    cand = decision.candidates[0]
    assert cand.is_eligible is True
    assert cand.score_breakdown["reliability"] == 0.0  # Cold start neutral


# ============================================================================
# 4. HISTORICAL RELIABILITY & DETERMINISTIC TIES
# ============================================================================

@pytest.mark.asyncio
async def test_historical_reliability_scoring():
    """Two equivalent agents: the one with better empirical verification history is chosen."""
    registry = AdapterRegistry()
    claude = MockConfigurableAdapter(
        adapter_id="claude_code",
        capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
    )
    codex = MockConfigurableAdapter(
        adapter_id="codex",
        capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
    )
    registry.register_adapter(claude)
    registry.register_adapter(codex)

    engine = RoutingEngine(adapter_registry=registry)
    req = RoutingRequest(
        mission_id="msn_hist",
        task_id="tsk_hist",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "filesystem_write", "git", "test_execution"]
        ),
        context={
            "historical_metrics": {
                "claude_code": {"verified_successes": 2, "verification_failures": 3, "handoffs": 1},
                "codex": {"verified_successes": 8, "verification_failures": 1, "handoffs": 0},
            }
        },
    )

    decision = await engine.route(req)
    assert decision.decision == RoutingDecisionType.ROUTE
    assert decision.selected_agent_id == "codex"
    cand_codex = next(c for c in decision.candidates if c.agent_id == "codex")
    cand_claude = next(c for c in decision.candidates if c.agent_id == "claude_code")
    assert cand_codex.score > cand_claude.score
    assert cand_codex.score_breakdown["reliability"] > cand_claude.score_breakdown["reliability"]


@pytest.mark.asyncio
async def test_deterministic_tie_breaker():
    """Identical candidates produce the exact same selected agent deterministically across runs."""
    registry = AdapterRegistry()
    agent_a = MockConfigurableAdapter(
        adapter_id="agent_alpha",
        capabilities=["code_execution", "filesystem_write"],
    )
    agent_b = MockConfigurableAdapter(
        adapter_id="agent_beta",
        capabilities=["code_execution", "filesystem_write"],
    )
    registry.register_adapter(agent_a)
    registry.register_adapter(agent_b)

    engine = RoutingEngine(adapter_registry=registry)
    req = RoutingRequest(
        mission_id="msn_tie",
        task_id="tsk_tie",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "filesystem_write"]
        ),
    )

    results = []
    for _ in range(5):
        decision = await engine.route(req)
        results.append(decision.selected_agent_id)

    # Must be 100% deterministic across all runs
    assert all(r == results[0] for r in results)
    assert results[0] in ("agent_alpha", "agent_beta")


# ============================================================================
# 5. NO ELIGIBLE AGENT & SOURCE AGENT EXCLUSION (HANDOFF INTEGRATION)
# ============================================================================

@pytest.mark.asyncio
async def test_no_eligible_agent_decision():
    """When no candidate satisfies required capabilities, decision is NO_ELIGIBLE_AGENT."""
    registry = AdapterRegistry()
    adapter = MockConfigurableAdapter(
        adapter_id="read_only_agent",
        capabilities=["filesystem_read"],
    )
    registry.register_adapter(adapter)

    engine = RoutingEngine(adapter_registry=registry)
    req = RoutingRequest(
        mission_id="msn_none",
        task_id="tsk_none",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "filesystem_write"]
        ),
    )

    decision = await engine.route(req)
    assert decision.decision == RoutingDecisionType.NO_ELIGIBLE_AGENT
    assert decision.selected_agent_id is None
    assert "No eligible agent found" in decision.decision_reason


@pytest.mark.asyncio
async def test_handoff_routing_excludes_source_agent():
    """Handoff routing excludes the failing source agent and routes to the alternate eligible agent."""
    registry = AdapterRegistry()
    claude = MockConfigurableAdapter(
        adapter_id="claude_code",
        capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
    )
    codex = MockConfigurableAdapter(
        adapter_id="codex",
        capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
    )
    registry.register_adapter(claude)
    registry.register_adapter(codex)

    engine = RoutingEngine(adapter_registry=registry)

    # Exclude claude_code as it just failed
    req = RoutingRequest(
        mission_id="msn_handoff",
        task_id="tsk_handoff",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "filesystem_write"],
            excluded_agent_ids=["claude_code"],
        ),
    )

    decision = await engine.route(req)
    assert decision.decision == RoutingDecisionType.ROUTE
    assert decision.selected_agent_id == "codex"
    cand_claude = next(c for c in decision.candidates if c.agent_id == "claude_code")
    assert cand_claude.is_eligible is False
    assert any("explicitly excluded" in r for r in cand_claude.ineligibility_reasons)


# ============================================================================
# 6. ROUTING PERSISTENCE & EVENTS
# ============================================================================

@pytest.mark.asyncio
async def test_routing_persistence_and_restart(tmp_path):
    """Routing decision persists in SQLite WAL and survives process/db manager restart."""
    db_file = tmp_path / "supervisor_routing.db"
    db = DatabaseManager(db_path=str(db_file))
    mission_repo = MissionRepository(db)
    routing_repo = RoutingRepository(db)

    # Seed parent mission
    await mission_repo.save({
        "mission_id": "msn_persist_route",
        "title": "Routing Persistence Mission",
        "goal": "Verify SQLite durability of routing decisions",
        "status": "IN_PROGRESS",
    })

    registry = AdapterRegistry()
    adapter = MockConfigurableAdapter(
        adapter_id="persisted_agent",
        capabilities=["code_execution", "filesystem_write"],
    )
    registry.register_adapter(adapter)

    engine = RoutingEngine(adapter_registry=registry, repository=routing_repo)
    req = RoutingRequest(
        mission_id="msn_persist_route",
        task_id="tsk_persist_route",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "filesystem_write"]
        ),
    )

    decision = await engine.route(req)
    assert decision.decision == RoutingDecisionType.ROUTE

    # Re-open database to simulate restart
    db_reopened = DatabaseManager(db_path=str(db_file))
    reopened_repo = RoutingRepository(db_reopened)

    saved = await reopened_repo.get(decision.routing_id)
    assert saved is not None
    assert saved["routing_id"] == decision.routing_id
    assert saved["selected_agent_id"] == "persisted_agent"
    assert saved["decision"] == "ROUTE"
    assert len(saved["candidates"]) == 1
    assert "persisted_agent" in saved["decision_reason"]


@pytest.mark.asyncio
async def test_routing_events_emitted():
    """Verifies routing.started, routing.candidate.evaluated, and routing.completed are published."""
    bus = EventBus()
    emitted_events = []

    async def _on_event(e):
        emitted_events.append(e)

    await bus.subscribe(_on_event)

    registry = AdapterRegistry()
    adapter = MockConfigurableAdapter(
        adapter_id="event_agent",
        capabilities=["code_execution", "filesystem_write"],
    )
    registry.register_adapter(adapter)

    engine = RoutingEngine(adapter_registry=registry, event_bus=bus)
    req = RoutingRequest(
        mission_id="msn_ev",
        task_id="tsk_ev",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "filesystem_write"]
        ),
    )

    await engine.route(req)

    event_types = [
        e.payload.get("event_type") for e in emitted_events if isinstance(e.payload, dict)
    ]
    assert "routing.started" in event_types
    assert "routing.candidate.evaluated" in event_types
    assert "routing.completed" in event_types


# ============================================================================
# 7. KILLER SCENARIO: DYNAMIC ROUTING TO CODEX + INDEPENDENT VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_killer_scenario_dynamic_routing_to_codex_and_verification(tmp_path):
    """
    PHASE 6 KILLER SCENARIO:
    1. Mission: Fix authentication tests.
    2. Available agents:
       - Claude Code (2 successes, 3 failures, 1 handoff)
       - OpenAI Codex (8 successes, 1 failure, 0 handoffs)
       Both satisfy required capabilities: code_execution, filesystem_write, git, test_execution.
    3. Supervisor queries RoutingEngine:
       - Evaluates both candidates.
       - Reliability scoring favors Codex (+5.0 vs -5.5).
       - Selects Codex dynamically.
       - Emits routing events and persists routing decision.
    4. Task dispatched to Codex mock in isolated Git worktree.
    5. Codex applies the correct fix in auth/session.py and claims completion.
    6. Phase 4 Independent Verification Engine runs tests independently.
    7. Verification engine returns ACCEPT. Task verified complete.
    8. Asserts: routing.selected_agent == "codex" AND verification.decision == ACCEPT.
    """
    repo_dir = tmp_path / "auth_repo"
    repo_dir.mkdir()
    _init_dummy_git_repo(repo_dir)

    # Initialize auth/session.py with bug and test script
    auth_dir = repo_dir / "auth"
    auth_dir.mkdir()
    (auth_dir / "session.py").write_text(
        """def parse_token(token: str) -> dict:
    return {"token": token}
""",
        encoding="utf-8",
    )

    test_file = repo_dir / "test_auth.py"
    test_file.write_text(
        """import sys
from auth.session import parse_token

def test_bearer():
    res = parse_token("Bearer tok_secret_999")
    if res.get("token") != "tok_secret_999":
        print("FAIL: Expected 'tok_secret_999', got:", res.get("token"))
        sys.exit(1)
    print("PASS")
    sys.exit(0)

if __name__ == '__main__':
    test_bearer()
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Add auth logic and tests"], cwd=str(repo_dir), check=True)

    wt_mgr = GitWorktreeManager(repo_dir)
    wt_path = wt_mgr.create("msn_killer_route", "tsk_killer_route")

    # Codex mock script that applies the correct fix
    mock_codex_script = _create_mock_script(
        tmp_path,
        "codex_fix.py",
        """import sys
with open('auth/session.py', 'w') as f:
    f.write('''def parse_token(token: str) -> dict:
    if token.startswith("Bearer "):
        token = token[7:]
    return {"token": token}
''')
print('Codex successfully stripped Bearer token prefix.')
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
    routing_repo = RoutingRepository(db)

    # Seed parent mission and task
    await mission_repo.save({
        "mission_id": "msn_killer_route",
        "title": "Fix authentication tests",
        "goal": "Fix token parsing via dynamically routed agent",
        "repository_path": str(repo_dir),
        "status": "IN_PROGRESS",
    })
    await task_repo.save({
        "task_id": "tsk_killer_route",
        "mission_id": "msn_killer_route",
        "title": "Fix token parsing",
        "status": "PENDING",
    })

    adapter_registry = AdapterRegistry()
    claude_adapter = ClaudeCodeAdapter(
        event_bus=bus,
        worktree_manager=wt_mgr,
        executable_override="mock_claude_dummy",
    )
    codex_adapter = CodexAdapter(
        event_bus=bus,
        worktree_manager=wt_mgr,
        executable_override=mock_codex_script,
    )
    adapter_registry.register_adapter(claude_adapter)
    adapter_registry.register_adapter(codex_adapter)

    routing_engine = RoutingEngine(
        adapter_registry=adapter_registry,
        repository=routing_repo,
        event_bus=bus,
    )

    ver_engine = VerificationEngine(
        event_bus=bus,
        repository=ver_repo,
        worktree_manager=wt_mgr,
    )

    # 1. Routing Request with historical reliability context
    req = RoutingRequest(
        mission_id="msn_killer_route",
        task_id="tsk_killer_route",
        task_objective="Fix authentication test failures",
        task_requirements=TaskRequirements(
            task_type="bug_fix",
            required_capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
            preferred_capabilities=["terminal_execution"],
        ),
        context={
            "historical_metrics": {
                "claude_code": {"verified_successes": 2, "verification_failures": 3, "handoffs": 1},
                "codex": {"verified_successes": 8, "verification_failures": 1, "handoffs": 0},
            }
        },
    )

    # 2. Dynamic Routing Decision
    decision = await routing_engine.route(req)
    assert decision.decision == RoutingDecisionType.ROUTE
    assert decision.selected_agent_id == "codex"
    assert "codex" in decision.decision_reason

    # 3. Dispatch task to selected agent (Codex)
    target_adapter = adapter_registry.get_adapter(decision.selected_agent_id)
    assert target_adapter is not None

    dispatch = TaskDispatchPackage(
        task_id="tsk_killer_route",
        mission_id="msn_killer_route",
        objective="Fix token parsing to pass test_auth.py",
        workspace=str(wt_path),
        allowed_files=["auth/session.py"],
    )
    exec_result = await target_adapter.execute(dispatch)
    assert exec_result.status == AdapterProcessStatus.COMPLETED

    # 4. Phase 4 Independent Verification
    v_ctx = VerificationContext(
        task_id="tsk_killer_route",
        mission_id="msn_killer_route",
        workspace=str(wt_path),
        agent_id=decision.selected_agent_id,
        verification_requirements=["python test_auth.py"],
        allowed_files=["auth/session.py"],
        completion_claim={"summary": exec_result.summary},
    )
    ver_result = await ver_engine.verify(v_ctx)

    # 5. Required Final Assertions:
    assert decision.selected_agent_id == "codex"
    assert ver_result.decision == VerificationDecision.ACCEPT
    assert "Independent verification ACCEPTED" in ver_result.summary

    # Isolation check: primary repository was never touched
    primary_session = (repo_dir / "auth" / "session.py").read_text(encoding="utf-8")
    assert "startswith" not in primary_session


# ============================================================================
# 8. SECOND NEGATIVE SCENARIO: UNAVAILABLE + MISSING CAPABILITY
# ============================================================================

@pytest.mark.asyncio
async def test_negative_scenario_unavailable_and_missing_capability():
    """
    NEGATIVE SCENARIO (Section 25):
    - Claude = unavailable
    - Codex = missing required capability (e.g. database_migration)
    Expected: NO_ELIGIBLE_AGENT.
    Supervisor does NOT randomly select Claude or Codex, nor bypass requirements.
    """
    registry = AdapterRegistry()
    claude = MockConfigurableAdapter(
        adapter_id="claude_code",
        capabilities=["code_execution", "filesystem_write", "git", "test_execution"],
        available=False,
        availability_status=AdapterAvailabilityStatus.NOT_INSTALLED,
    )
    codex = MockConfigurableAdapter(
        adapter_id="codex",
        capabilities=["code_execution", "filesystem_write", "git"],  # lacks database_migration
        available=True,
    )
    registry.register_adapter(claude)
    registry.register_adapter(codex)

    engine = RoutingEngine(adapter_registry=registry)
    req = RoutingRequest(
        mission_id="msn_neg",
        task_id="tsk_neg",
        task_requirements=TaskRequirements(
            required_capabilities=["code_execution", "database_migration"]
        ),
    )

    decision = await engine.route(req)
    assert decision.decision == RoutingDecisionType.NO_ELIGIBLE_AGENT
    assert decision.selected_agent_id is None
    assert decision.selected_adapter_id is None
    assert "No eligible agent found" in decision.decision_reason

    # Confirm neither agent bypassed the gate
    for cand in decision.candidates:
        assert cand.is_eligible is False
        assert cand.score == 0.0
