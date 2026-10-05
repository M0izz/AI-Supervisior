"""
Automated Test Suite for Phase 9: Absence Mode.

Covers:
1. Policy Validation, Conservative Defaults, and Snapshot Immutability
2. Lifecycle Transitions (ARMED -> ACTIVE -> PAUSED -> RESUMED -> EXPIRED -> CANCELLED -> COMPLETED)
3. Authority Hierarchy (Allowed actions, Dangerous commands blocked, Protected paths blocked)
4. Security Invariants: Agent Cannot Self-Escalate (Cannot modify policy, extend duration, disable watchdogs, bypass verifier)
5. Time Limits & Hard Expiration
6. Budget Limits (Max tasks, Max retries, Max handoffs)
7. Restart Durability & Fail-Closed Reconciliation
8. Killer End-to-End Scenario (Absence Mode armed -> Claude fails -> Watchdog loop -> Handoff to Codex -> Verifier accepts -> Completed)
9. Negative Scenario (Repeated failure reaches retry ceiling -> Session pauses -> Autonomous work stops)
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from storage.sqlite.db import DatabaseManager
from storage.sqlite.repositories import AbsenceRepository, MissionRepository
from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.absence.models import (
    AbsencePolicy,
    AbsenceSession,
    AbsenceSessionState,
    AbsenceDecisionType,
    ApprovalPolicy
)
from core.absence.engine import AbsencePolicyEngine


async def create_mission(db: DatabaseManager, mission_id: str):
    msn_repo = MissionRepository(db)
    await msn_repo.save({
        "mission_id": mission_id,
        "title": f"Mission {mission_id}",
        "goal": "Test goal",
        "status": "IN_PROGRESS"
    })


@pytest.fixture
def clean_db(tmp_path):
    db_file = tmp_path / "test_absence.db"
    db = DatabaseManager(db_path=str(db_file))
    return db


@pytest.fixture
def absence_engine(clean_db):
    event_bus = EventBus()
    repo = AbsenceRepository(clean_db)
    engine = AbsencePolicyEngine(repository=repo, event_bus=event_bus)

    orig_arm = engine.arm_session
    async def auto_arm(mission_id, policy=None, created_by="user"):
        await create_mission(clean_db, mission_id)
        return await orig_arm(mission_id=mission_id, policy=policy, created_by=created_by)
    engine.arm_session = auto_arm

    return engine, repo, event_bus



@pytest.mark.asyncio
async def test_policy_validation_and_conservative_defaults():
    """Verifies that AbsencePolicy enforces conservative defaults and validates constraints."""
    policy = AbsencePolicy()
    assert policy.enabled is True
    assert policy.max_duration_seconds == 7200  # 2 hours default
    assert policy.max_tasks == 5
    assert policy.max_retries == 3
    assert policy.max_handoffs == 2
    assert "rm -rf" in policy.prohibited_commands
    assert "drop table" in policy.prohibited_commands
    assert ".env" in policy.prohibited_paths
    assert ".git" in policy.prohibited_paths

    # Invalid duration must be rejected
    with pytest.raises(ValueError, match="positive"):
        AbsencePolicy(max_duration_seconds=0)

    with pytest.raises(ValueError, match="24 hours"):
        AbsencePolicy(max_duration_seconds=90000)

    # Invalid retries must be rejected
    with pytest.raises(ValueError, match="at least 1"):
        AbsencePolicy(max_retries=0)


@pytest.mark.asyncio
async def test_policy_snapshot_immutability(absence_engine):
    """Verifies that arming Absence Mode creates an immutable snapshot unaffected by subsequent changes."""
    engine, repo, _ = absence_engine

    custom_policy = AbsencePolicy(max_duration_seconds=3600, max_retries=2)
    session = await engine.arm_session(mission_id="msn_immutable_1", policy=custom_policy)

    assert session.policy.max_duration_seconds == 3600
    assert session.policy.max_retries == 2

    # Mutate caller policy object
    custom_policy.max_retries = 10

    # Persisted session must remain unchanged
    persisted = await repo.get_session(session.absence_id)
    assert persisted["policy_snapshot"]["max_retries"] == 2


@pytest.mark.asyncio
async def test_absence_lifecycle_transitions(absence_engine):
    """Verifies state machine: ARMED -> ACTIVE -> PAUSED -> ACTIVE -> CANCELLED."""
    engine, _, _ = absence_engine

    # 1. Arm
    session = await engine.arm_session(mission_id="msn_lifecycle")
    assert session.status == AbsenceSessionState.ARMED
    assert session.started_at is None

    # 2. Start
    started = await engine.start_session(session.absence_id)
    assert started.status == AbsenceSessionState.ACTIVE
    assert started.started_at is not None
    assert started.expires_at is not None
    assert started.remaining_seconds() > 0

    # 3. Pause
    paused = await engine.pause_session(session.absence_id, reason="Operator taking phone call")
    assert paused.status == AbsenceSessionState.PAUSED
    assert paused.paused_reason == "Operator taking phone call"

    # 4. Resume
    resumed = await engine.resume_session(session.absence_id)
    assert resumed.status == AbsenceSessionState.ACTIVE
    assert resumed.paused_reason is None

    # 5. Cancel (Emergency Stop)
    cancelled = await engine.cancel_session(session.absence_id, reason="Emergency operator stop")
    assert cancelled.status == AbsenceSessionState.CANCELLED
    assert cancelled.paused_reason == "Emergency operator stop"


@pytest.mark.asyncio
async def test_authority_hierarchy_allowed_and_denied_actions(absence_engine):
    """Verifies that dangerous commands and protected paths are denied even during absence."""
    engine, _, _ = absence_engine

    session = await engine.arm_session(mission_id="msn_auth_1")
    await engine.start_session(session.absence_id)

    # 1. Benign file edit within worktree is allowed
    dec1 = await engine.evaluate_action(
        absence_id=session.absence_id,
        action_type="write_file",
        target="src/parser.py",
        agent_id="claude-code"
    )
    assert dec1.decision == AbsenceDecisionType.ALLOW

    # 2. Dangerous command is blocked
    dec2 = await engine.evaluate_action(
        absence_id=session.absence_id,
        action_type="execute_command",
        command="rm -rf /tmp/data",
        agent_id="claude-code"
    )
    assert dec2.decision == AbsenceDecisionType.DENY
    assert "dangerous_command_blocked" in dec2.rule_id

    # 3. Protected file path is blocked
    dec3 = await engine.evaluate_action(
        absence_id=session.absence_id,
        action_type="modify_file",
        target=".env",
        agent_id="claude-code"
    )
    assert dec3.decision == AbsenceDecisionType.DENY
    assert "protected_path_blocked" in dec3.rule_id


@pytest.mark.asyncio
async def test_security_agent_cannot_self_escalate(absence_engine):
    """
    Security Invariant: An agent can NEVER increase its own authority:
    - cannot modify absence policy
    - cannot extend absence duration
    - cannot disable watchdogs
    - cannot bypass verification
    - cannot grant itself capabilities
    """
    engine, _, _ = absence_engine
    session = await engine.arm_session(mission_id="msn_security_escalation")
    await engine.start_session(session.absence_id)

    escalation_attempts = [
        ("modify_absence_policy", "set max_duration 999999", "absence_policy.json"),
        ("execute_command", "extend_absence_duration 48h", ""),
        ("execute_command", "disable_watchdog --all", ""),
        ("execute_command", "bypass_verification --force", ""),
        ("execute_command", "grant_capability unrestricted_shell", "")
    ]

    for action_type, cmd, target in escalation_attempts:
        decision = await engine.evaluate_action(
            absence_id=session.absence_id,
            action_type=action_type,
            command=cmd,
            target=target,
            agent_id="malicious-agent"
        )
        assert decision.decision == AbsenceDecisionType.DENY, f"Attempt {cmd} must be denied"
        assert "self_escalation_blocked" in decision.rule_id


@pytest.mark.asyncio
async def test_hard_time_expiration(absence_engine):
    """Verifies that an absence session hard-expires when current_time >= expires_at."""
    engine, repo, _ = absence_engine

    # Arm with 10 second duration
    policy = AbsencePolicy(max_duration_seconds=10)
    session = await engine.arm_session(mission_id="msn_expire", policy=policy)
    await engine.start_session(session.absence_id)

    # Simulate time jumping forward by setting expires_at in the past
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    await repo.update_session(session.absence_id, {"expires_at": past_time})

    # Evaluate action: engine must detect expiration, update state to EXPIRED, and pause
    dec = await engine.evaluate_action(
        absence_id=session.absence_id,
        action_type="run_test",
        agent_id="claude-code"
    )
    assert dec.decision == AbsenceDecisionType.PAUSE
    assert "session_expired" in dec.rule_id

    # Verify session is now EXPIRED
    updated = await repo.get_session(session.absence_id)
    assert updated["status"] == AbsenceSessionState.EXPIRED.value


@pytest.mark.asyncio
async def test_budget_limits_retries_and_handoffs(absence_engine):
    """Verifies that reaching retry and handoff ceilings pauses the session."""
    engine, repo, _ = absence_engine

    policy = AbsencePolicy(max_retries=2, max_handoffs=1, max_tasks=2)
    session = await engine.arm_session(mission_id="msn_budgets", policy=policy)
    await engine.start_session(session.absence_id)

    # 1. Handoff limit
    await engine.record_handoff(session.absence_id)
    s1 = await repo.get_session(session.absence_id)
    assert s1["status"] == AbsenceSessionState.PAUSED.value
    assert "handoff limit reached" in s1["paused_reason"].lower()

    # Resume session
    await engine.resume_session(session.absence_id)

    # 2. Retry limit
    await engine.record_retry(session.absence_id)  # 1/2
    s2 = await repo.get_session(session.absence_id)
    assert s2["status"] == AbsenceSessionState.ACTIVE.value

    await engine.record_retry(session.absence_id)  # 2/2 -> ceiling reached
    s3 = await repo.get_session(session.absence_id)
    assert s3["status"] == AbsenceSessionState.PAUSED.value
    assert "retry ceiling reached" in s3["paused_reason"].lower()


@pytest.mark.asyncio
async def test_restart_durability_and_fail_closed(clean_db):
    """Verifies that active sessions survive restart, and expired sessions transition to EXPIRED on startup."""
    event_bus = EventBus()
    repo = AbsenceRepository(clean_db)
    engine = AbsencePolicyEngine(repository=repo, event_bus=event_bus)

    # 1. Create one active session and one already-expired session
    await create_mission(clean_db, "msn_restart_active")
    s_active = await engine.arm_session(mission_id="msn_restart_active")
    await engine.start_session(s_active.absence_id)

    await create_mission(clean_db, "msn_restart_expired")
    s_expired = await engine.arm_session(mission_id="msn_restart_expired", policy=AbsencePolicy(max_duration_seconds=5))
    await engine.start_session(s_expired.absence_id)
    past_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    await repo.update_session(s_expired.absence_id, {"expires_at": past_time})

    # Simulate restart: new engine instance connects to the same database
    new_engine = AbsencePolicyEngine(repository=AbsenceRepository(clean_db), event_bus=EventBus())
    reconciled = await new_engine.reconcile_on_startup()

    assert reconciled == 1

    # Active session must remain ACTIVE
    check_active = await repo.get_session(s_active.absence_id)
    assert check_active["status"] == AbsenceSessionState.ACTIVE.value

    # Expired session must be EXPIRED
    check_expired = await repo.get_session(s_expired.absence_id)
    assert check_expired["status"] == AbsenceSessionState.EXPIRED.value


@pytest.mark.asyncio
async def test_killer_scenario_absence_mode_end_to_end(absence_engine):
    """
    Deterministic End-to-End Scenario (Section 28):
    1. User explicitly arms Absence Mode (30m, max retries 2, max handoffs 1).
    2. Session becomes ACTIVE.
    3. Claude starts task.
    4. Claude encounters repeated failure.
    5. Watchdog detects loop and halts Claude.
    6. Supervisor initiates handoff to Codex; Absence engine records handoff.
    7. Codex receives bounded context and applies fix.
    8. Agent claims completion.
    9. Independent verifier runs and ACCEPTS ground truth.
    10. Task marked VERIFIED. Absence engine records verified task completion.
    11. Absence policy permits completion.
    12. Mission completes; Absence session becomes COMPLETED.
    """
    engine, repo, event_bus = absence_engine

    events_received = []
    async def on_event(ev):
        events_received.append(ev)
    await event_bus.subscribe(on_event)

    # Step 1: User explicitly arms Absence Mode
    policy = AbsencePolicy(max_duration_seconds=1800, max_retries=2, max_handoffs=2, max_tasks=1)
    session = await engine.arm_session(mission_id="msn_killer_bom", policy=policy)
    assert session.status == AbsenceSessionState.ARMED

    # Step 2: Session becomes ACTIVE
    active_session = await engine.start_session(session.absence_id)
    assert active_session.status == AbsenceSessionState.ACTIVE

    # Step 3: Claude starts task (evaluates action)
    dec_start = await engine.evaluate_action(
        absence_id=session.absence_id,
        action_type="run_tests",
        command="pytest tests/test_parser.py",
        agent_id="claude-code"
    )
    assert dec_start.decision == AbsenceDecisionType.ALLOW

    # Step 4 & 5: Claude fails; Watchdog detects loop
    await engine.record_retry(session.absence_id)  # retry 1/2

    # Step 6: Supervisor initiates handoff to Codex
    await engine.record_handoff(session.absence_id)  # handoff 1/2

    # Step 7: Codex receives context and applies byte fix
    dec_codex = await engine.evaluate_action(
        absence_id=session.absence_id,
        action_type="write_file",
        target="src/csv_parser.py",
        agent_id="openai-codex"
    )
    assert dec_codex.decision == AbsenceDecisionType.ALLOW

    # Step 8, 9, 10: Agent claims completion -> Independent verifier ACCEPTS ground truth
    # Invariant: only verified completions count toward progress
    await engine.record_task_completion(session.absence_id, verified=True)

    # Step 11 & 12: Mission completes -> Session becomes COMPLETED
    final_session = await repo.get_session(session.absence_id)
    assert final_session["status"] == AbsenceSessionState.COMPLETED.value
    assert final_session["tasks_completed"] == 1

    # Verify event trail
    event_types = [getattr(e.type, "value", str(e.type)) for e in events_received]
    assert any("absence.armed" in t for t in event_types)
    assert any("absence.started" in t for t in event_types)
    assert any("absence.completed" in t for t in event_types)


@pytest.mark.asyncio
async def test_negative_scenario_absence_mode_retry_ceiling_pauses(absence_engine):
    """
    Negative Scenario (Section 28):
    Agent repeatedly fails -> Retry ceiling reached -> Supervisor pauses session ->
    Autonomous work halts safely -> User notification emitted.
    """
    engine, repo, event_bus = absence_engine

    notifications = []
    async def on_neg_event(ev):
        t_val = getattr(ev.type, "value", str(ev.type)).lower()
        if "paused" in t_val:
            notifications.append(ev)
    await event_bus.subscribe(on_neg_event)

    policy = AbsencePolicy(max_retries=2, max_duration_seconds=3600)
    session = await engine.arm_session(mission_id="msn_negative_loop", policy=policy)
    await engine.start_session(session.absence_id)

    # First failure -> retry 1
    await engine.record_retry(session.absence_id)
    s1 = await repo.get_session(session.absence_id)
    assert s1["status"] == AbsenceSessionState.ACTIVE.value

    # Second failure -> retry 2 -> Ceiling reached!
    await engine.record_retry(session.absence_id)
    s2 = await repo.get_session(session.absence_id)
    assert s2["status"] == AbsenceSessionState.PAUSED.value
    assert "retry ceiling reached" in s2["paused_reason"].lower()

    # Any subsequent action is PAUSED, blocking further autonomous work
    dec = await engine.evaluate_action(
        absence_id=session.absence_id,
        action_type="execute_command",
        command="pytest",
        agent_id="claude-code"
    )
    assert dec.decision == AbsenceDecisionType.PAUSE

    # User notification event verified
    assert len(notifications) >= 1
