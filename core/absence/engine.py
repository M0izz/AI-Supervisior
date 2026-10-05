"""
Absence Policy Engine for Phase 9.

Enforces bounded autonomy, conservative limits, auditable decisions,
and the core invariant:
"Absence Mode expands continuity, not authority."
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from storage.sqlite.repositories import AbsenceRepository
from core.absence.models import (
    AbsencePolicy,
    AbsenceSession,
    AbsenceSessionState,
    AbsenceDecision,
    AbsenceDecisionType,
    ApprovalPolicy,
    VerificationPolicy
)

logger = logging.getLogger("supervisor.absence")


class AbsencePolicyEngine:
    """
    Deterministic decision engine enforcing Absence Mode authority and lifecycle.
    Never relies on non-deterministic LLMs for safety authorization.
    """

    def __init__(
        self,
        repository: AbsenceRepository,
        event_bus: Optional[EventBus] = None,
        default_policy: Optional[AbsencePolicy] = None
    ):
        self.repository = repository
        self.event_bus = event_bus
        self.default_policy = default_policy or AbsencePolicy()

    # -------------------------------------------------------------------------
    # Lifecycle Management
    # -------------------------------------------------------------------------

    async def arm_session(
        self,
        mission_id: str,
        policy: Optional[AbsencePolicy] = None,
        created_by: str = "user"
    ) -> AbsenceSession:
        """
        Explicitly arms Absence Mode for a mission, freezing a policy snapshot.
        """
        active = await self.repository.get_active_session(mission_id)
        if active and active.get("status") in [AbsenceSessionState.ARMED.value, AbsenceSessionState.ACTIVE.value]:
            # Return existing active session
            return self._to_session_model(active)

        resolved_policy = policy or self.default_policy
        session = AbsenceSession(
            mission_id=mission_id,
            status=AbsenceSessionState.ARMED,
            policy=resolved_policy,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        saved = await self.repository.save_session(self._session_to_repo_dict(session))
        model = self._to_session_model(saved)

        await self._emit_event(
            EventType.ABSENCE_ARMED,
            mission_id=mission_id,
            payload={
                "absence_id": model.absence_id,
                "max_duration_seconds": model.policy.max_duration_seconds,
                "max_retries": model.policy.max_retries,
                "max_tasks": model.policy.max_tasks,
                "created_by": created_by
            }
        )
        return model

    async def start_session(self, absence_id: str) -> AbsenceSession:
        """
        Activates an ARMED or PAUSED absence session, starting the hard expiration clock.
        """
        raw = await self.repository.get_session(absence_id)
        if not raw:
            raise ValueError(f"Absence session {absence_id} not found")

        session = self._to_session_model(raw)
        now = datetime.now(timezone.utc)

        # Set or preserve expiration
        if not session.started_at:
            session.started_at = now
            session.expires_at = now + timedelta(seconds=session.policy.max_duration_seconds)

        if session.is_expired(now):
            session.status = AbsenceSessionState.EXPIRED
            session.paused_reason = "Session expired before activation"
        else:
            session.status = AbsenceSessionState.ACTIVE
            session.paused_reason = None

        session.updated_at = now
        saved = await self.repository.save_session(self._session_to_repo_dict(session))
        model = self._to_session_model(saved)

        if model.status == AbsenceSessionState.ACTIVE:
            await self._emit_event(
                EventType.ABSENCE_STARTED,
                mission_id=model.mission_id,
                payload={
                    "absence_id": model.absence_id,
                    "started_at": model.started_at.isoformat() if model.started_at else None,
                    "expires_at": model.expires_at.isoformat() if model.expires_at else None,
                    "remaining_seconds": model.remaining_seconds()
                }
            )
        return model

    async def pause_session(self, absence_id: str, reason: str = "Operator paused") -> AbsenceSession:
        """
        Pauses an active absence session. Revokes autonomous continuation.
        """
        raw = await self.repository.get_session(absence_id)
        if not raw:
            raise ValueError(f"Absence session {absence_id} not found")

        session = self._to_session_model(raw)
        session.status = AbsenceSessionState.PAUSED
        session.paused_reason = reason
        session.updated_at = datetime.now(timezone.utc)

        saved = await self.repository.save_session(self._session_to_repo_dict(session))
        model = self._to_session_model(saved)

        await self._emit_event(
            EventType.ABSENCE_PAUSED,
            mission_id=model.mission_id,
            severity=EventSeverity.WARNING,
            payload={"absence_id": model.absence_id, "reason": reason}
        )
        return model

    async def resume_session(self, absence_id: str) -> AbsenceSession:
        """
        Resumes a paused session after checking hard expiration.
        """
        raw = await self.repository.get_session(absence_id)
        if not raw:
            raise ValueError(f"Absence session {absence_id} not found")

        session = self._to_session_model(raw)
        now = datetime.now(timezone.utc)

        if session.is_expired(now):
            session.status = AbsenceSessionState.EXPIRED
            session.paused_reason = "Hard expiration reached"
            saved = await self.repository.save_session(self._session_to_repo_dict(session))
            await self._emit_event(
                EventType.ABSENCE_EXPIRED,
                mission_id=session.mission_id,
                severity=EventSeverity.WARNING,
                payload={"absence_id": absence_id, "reason": "Expired while paused"}
            )
            return self._to_session_model(saved)

        session.status = AbsenceSessionState.ACTIVE
        session.paused_reason = None
        session.updated_at = now

        saved = await self.repository.save_session(self._session_to_repo_dict(session))
        model = self._to_session_model(saved)

        await self._emit_event(
            EventType.ABSENCE_RESUMED,
            mission_id=model.mission_id,
            payload={"absence_id": model.absence_id, "remaining_seconds": model.remaining_seconds()}
        )
        return model

    async def cancel_session(self, absence_id: str, reason: str = "Emergency stop") -> AbsenceSession:
        """
        Emergency stop: Cancels the absence session and revokes all autonomous authorization.
        """
        raw = await self.repository.get_session(absence_id)
        if not raw:
            raise ValueError(f"Absence session {absence_id} not found")

        session = self._to_session_model(raw)
        session.status = AbsenceSessionState.CANCELLED
        session.paused_reason = reason
        session.updated_at = datetime.now(timezone.utc)

        saved = await self.repository.save_session(self._session_to_repo_dict(session))
        model = self._to_session_model(saved)

        await self._emit_event(
            EventType.ABSENCE_CANCELLED,
            mission_id=model.mission_id,
            severity=EventSeverity.WARNING,
            payload={"absence_id": model.absence_id, "reason": reason}
        )
        return model

    async def complete_session(self, absence_id: str, reason: str = "Mission verified and completed") -> AbsenceSession:
        """
        Marks the absence session COMPLETED after independent verification passes.
        """
        raw = await self.repository.get_session(absence_id)
        if not raw:
            raise ValueError(f"Absence session {absence_id} not found")

        session = self._to_session_model(raw)
        session.status = AbsenceSessionState.COMPLETED
        session.paused_reason = None
        session.updated_at = datetime.now(timezone.utc)

        saved = await self.repository.save_session(self._session_to_repo_dict(session))
        model = self._to_session_model(saved)

        await self._emit_event(
            EventType.ABSENCE_COMPLETED,
            mission_id=model.mission_id,
            severity=EventSeverity.INFO,
            payload={
                "absence_id": model.absence_id,
                "reason": reason,
                "tasks_completed": model.tasks_completed
            }
        )
        return model

    # -------------------------------------------------------------------------
    # Authority & Decision Evaluation
    # -------------------------------------------------------------------------

    async def evaluate_action(
        self,
        absence_id: str,
        action_type: str,
        target: str = "",
        command: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> AbsenceDecision:
        """
        Deterministic Authority Hierarchy Evaluation:
        Safety Restrictions > User Policy > Supervisor Rules > Task Constraints > Agent Request.
        """
        raw = await self.repository.get_session(absence_id)
        now = datetime.now(timezone.utc)

        if not raw:
            return await self._record_decision(
                absence_id=absence_id,
                mission_id="unknown",
                decision=AbsenceDecisionType.DENY,
                rule_id="session.not_found",
                reason="Absence session does not exist",
                action=action_type,
                task_id=task_id,
                agent_id=agent_id
            )

        session = self._to_session_model(raw)
        policy = session.policy

        # 1. HARD SECURITY GATES: Agent cannot self-escalate authority
        if self._is_self_escalation_attempt(action_type, command, target):
            return await self._record_decision(
                absence_id=absence_id,
                mission_id=session.mission_id,
                decision=AbsenceDecisionType.DENY,
                rule_id="security.self_escalation_blocked",
                reason="Agent cannot modify absence policy, extend duration, disable watchdogs, or bypass verifier",
                action=action_type,
                task_id=task_id,
                agent_id=agent_id
            )

        # 2. PROHIBITED COMMANDS & PROTECTED PATHS
        if command and policy.is_command_prohibited(command):
            return await self._record_decision(
                absence_id=absence_id,
                mission_id=session.mission_id,
                decision=AbsenceDecisionType.DENY,
                rule_id="safety.dangerous_command_blocked",
                reason=f"Command matches prohibited dangerous patterns: {command[:80]}",
                action=action_type,
                task_id=task_id,
                agent_id=agent_id
            )

        if target and policy.is_path_prohibited(target):
            return await self._record_decision(
                absence_id=absence_id,
                mission_id=session.mission_id,
                decision=AbsenceDecisionType.DENY,
                rule_id="safety.protected_path_blocked",
                reason=f"Target path is protected by security policy: {target}",
                action=action_type,
                task_id=task_id,
                agent_id=agent_id
            )

        # 3. SESSION STATUS & EXPIRATION
        if session.is_expired(now):
            await self.pause_session(absence_id, reason="Hard session expiration reached")
            session.status = AbsenceSessionState.EXPIRED
            await self.repository.update_session(absence_id, {"status": "EXPIRED", "paused_reason": "Expired"})
            await self._emit_event(EventType.ABSENCE_EXPIRED, mission_id=session.mission_id)
            return await self._record_decision(
                absence_id=absence_id,
                mission_id=session.mission_id,
                decision=AbsenceDecisionType.PAUSE,
                rule_id="lifecycle.session_expired",
                reason="Absence session duration has expired; halting autonomous continuation",
                action=action_type,
                task_id=task_id,
                agent_id=agent_id
            )

        if session.status != AbsenceSessionState.ACTIVE:
            return await self._record_decision(
                absence_id=absence_id,
                mission_id=session.mission_id,
                decision=AbsenceDecisionType.PAUSE,
                rule_id="lifecycle.session_not_active",
                reason=f"Absence session is currently {session.status.value}",
                action=action_type,
                task_id=task_id,
                agent_id=agent_id
            )

        # 4. MEASURABLE BUDGETS & LIMITS
        if session.tasks_completed >= policy.max_tasks:
            await self.pause_session(absence_id, reason=f"Max tasks limit ({policy.max_tasks}) reached")
            return await self._record_decision(
                absence_id=absence_id,
                mission_id=session.mission_id,
                decision=AbsenceDecisionType.PAUSE,
                rule_id="budget.max_tasks_exceeded",
                reason=f"Reached session task completion limit ({session.tasks_completed}/{policy.max_tasks})",
                action=action_type,
                task_id=task_id,
                agent_id=agent_id
            )

        if session.retries_count >= policy.max_retries:
            await self.pause_session(absence_id, reason=f"Max retries limit ({policy.max_retries}) reached")
            return await self._record_decision(
                absence_id=absence_id,
                mission_id=session.mission_id,
                decision=AbsenceDecisionType.PAUSE,
                rule_id="budget.max_retries_exceeded",
                reason=f"Reached session retry ceiling ({session.retries_count}/{policy.max_retries})",
                action=action_type,
                task_id=task_id,
                agent_id=agent_id
            )

        if session.handoffs_count >= policy.max_handoffs:
            await self.pause_session(absence_id, reason=f"Max handoffs limit ({policy.max_handoffs}) reached")
            return await self._record_decision(
                absence_id=absence_id,
                mission_id=session.mission_id,
                decision=AbsenceDecisionType.PAUSE,
                rule_id="budget.max_handoffs_exceeded",
                reason=f"Reached cross-agent handoff limit ({session.handoffs_count}/{policy.max_handoffs})",
                action=action_type,
                task_id=task_id,
                agent_id=agent_id
            )

        # 5. APPROVAL POLICY EVALUATION
        if policy.approval_policy == ApprovalPolicy.ALWAYS_ASK:
            return await self._record_decision(
                absence_id=absence_id,
                mission_id=session.mission_id,
                decision=AbsenceDecisionType.REQUIRE_USER,
                rule_id="approval.always_ask",
                reason="Policy requires human operator confirmation for all actions",
                action=action_type,
                task_id=task_id,
                agent_id=agent_id
            )

        if policy.approval_policy == ApprovalPolicy.NEVER_ALLOW:
            return await self._record_decision(
                absence_id=absence_id,
                mission_id=session.mission_id,
                decision=AbsenceDecisionType.DENY,
                rule_id="approval.never_allow",
                reason="Policy prohibits autonomous execution of unapproved actions",
                action=action_type,
                task_id=task_id,
                agent_id=agent_id
            )

        # Default: AUTO_APPROVE_WITHIN_POLICY
        return await self._record_decision(
            absence_id=absence_id,
            mission_id=session.mission_id,
            decision=AbsenceDecisionType.ALLOW,
            rule_id="policy.auto_approve_within_bounds",
            reason="Action is within authorized absence policy bounds and worktree isolation",
            action=action_type,
            task_id=task_id,
            agent_id=agent_id
        )

    # -------------------------------------------------------------------------
    # Progress & Counter Recording
    # -------------------------------------------------------------------------

    async def record_task_completion(self, absence_id: str, verified: bool = False) -> None:
        """
        Records a task completion. Enforces invariant:
        Agent completion != verified completion. Only verified completions advance progress.
        """
        if not verified:
            logger.warning(f"Unverified task completion reported for {absence_id}; ignoring.")
            return

        raw = await self.repository.get_session(absence_id)
        if not raw:
            return
        session = self._to_session_model(raw)
        new_tasks = session.tasks_completed + 1
        await self.repository.update_session(absence_id, {"tasks_completed": new_tasks})

        if new_tasks >= session.policy.max_tasks:
            await self.complete_session(absence_id, reason="All authorized absence tasks completed and verified")

    async def record_retry(self, absence_id: str) -> None:
        """Increments task retry counter; pauses if retry limit reached."""
        raw = await self.repository.get_session(absence_id)
        if not raw:
            return
        session = self._to_session_model(raw)
        new_retries = session.retries_count + 1
        await self.repository.update_session(absence_id, {"retries_count": new_retries})

        if new_retries >= session.policy.max_retries:
            await self.pause_session(
                absence_id,
                reason=f"Autonomous retry ceiling reached ({new_retries}/{session.policy.max_retries})"
            )

    async def record_handoff(self, absence_id: str) -> None:
        """Increments handoff counter; pauses if handoff limit reached."""
        raw = await self.repository.get_session(absence_id)
        if not raw:
            return
        session = self._to_session_model(raw)
        new_handoffs = session.handoffs_count + 1
        await self.repository.update_session(absence_id, {"handoffs_count": new_handoffs})

        if new_handoffs >= session.policy.max_handoffs:
            await self.pause_session(
                absence_id,
                reason=f"Cross-agent handoff limit reached ({new_handoffs}/{session.policy.max_handoffs})"
            )

    # -------------------------------------------------------------------------
    # Restart & Fail-Closed Reconciliation
    # -------------------------------------------------------------------------

    async def reconcile_on_startup(self) -> int:
        """
        Reconciles active absence sessions upon backend restart:
        - Expired sessions are transitioned to EXPIRED.
        - Corrupted or unparseable sessions fail closed into BLOCKED.
        Returns count of reconciled sessions.
        """
        active_list = await self.repository.list_active_sessions()
        reconciled = 0
        now = datetime.now(timezone.utc)

        for raw in active_list:
            try:
                session = self._to_session_model(raw)
                if session.is_expired(now):
                    await self.repository.update_session(
                        session.absence_id,
                        {"status": AbsenceSessionState.EXPIRED.value, "paused_reason": "Expired across restart"}
                    )
                    await self._emit_event(
                        EventType.ABSENCE_EXPIRED,
                        mission_id=session.mission_id,
                        severity=EventSeverity.WARNING,
                        payload={"absence_id": session.absence_id, "reason": "Expired during backend shutdown"}
                    )
                    reconciled += 1
            except Exception as e:
                # Fail-closed on corrupted session
                aid = raw.get("absence_id")
                if aid:
                    await self.repository.update_session(
                        aid,
                        {"status": AbsenceSessionState.BLOCKED.value, "paused_reason": f"Corrupted policy: {e}"}
                    )
                    reconciled += 1

        return reconciled

    # -------------------------------------------------------------------------
    # Helper Utilities
    # -------------------------------------------------------------------------

    def _is_self_escalation_attempt(self, action_type: str, command: Optional[str], target: str) -> bool:
        cmd_str = (command or "").lower()
        act_str = action_type.lower()
        tgt_str = target.lower()

        forbidden_phrases = [
            "extend_absence", "disable_watchdog", "bypass_verification",
            "grant_capability", "modify_absence_policy", "set_autonomy"
        ]
        if any(p in act_str or p in cmd_str or p in tgt_str for p in forbidden_phrases):
            return True

        if "absence_policy" in tgt_str or "policy_snapshot" in tgt_str:
            return True

        return False

    async def _record_decision(
        self,
        absence_id: str,
        mission_id: str,
        decision: AbsenceDecisionType,
        rule_id: str,
        reason: str,
        action: str,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AbsenceDecision:
        dec = AbsenceDecision(
            absence_id=absence_id,
            mission_id=mission_id,
            task_id=task_id,
            agent_id=agent_id,
            decision=decision,
            rule_id=rule_id,
            reason=reason,
            action=action,
            metadata=metadata or {},
            timestamp=datetime.now(timezone.utc)
        )
        await self.repository.save_decision(dec.model_dump(mode="json"))

        ev_type = EventType.ABSENCE_ACTION_ALLOWED if decision == AbsenceDecisionType.ALLOW else EventType.ABSENCE_ACTION_DENIED
        await self._emit_event(
            ev_type,
            mission_id=mission_id,
            payload={
                "absence_id": absence_id,
                "decision": decision.value,
                "rule_id": rule_id,
                "reason": reason,
                "action": action
            }
        )
        return dec

    async def _emit_event(
        self,
        event_type: EventType,
        mission_id: str,
        severity: EventSeverity = EventSeverity.INFO,
        payload: Optional[Dict[str, Any]] = None
    ) -> None:
        if not self.event_bus:
            return
        event = Event(
            type=event_type,
            severity=severity,
            mission_id=mission_id,
            payload=payload or {}
        )
        try:
            await self.event_bus.publish(event)
        except Exception as e:
            logger.warning(f"Failed to publish absence event {event_type.value}: {e}")

    def _to_session_model(self, data: Dict[str, Any]) -> AbsenceSession:
        policy_data = data.get("policy_snapshot")
        if isinstance(policy_data, dict):
            policy = AbsencePolicy(**policy_data)
        elif isinstance(policy_data, AbsencePolicy):
            policy = policy_data
        else:
            policy = AbsencePolicy()

        started_at = data.get("started_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)

        expires_at = data.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif not created_at:
            created_at = datetime.now(timezone.utc)

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif not updated_at:
            updated_at = created_at

        return AbsenceSession(
            absence_id=data.get("absence_id", ""),
            mission_id=data.get("mission_id", ""),
            status=AbsenceSessionState(data.get("status", "ARMED")),
            policy=policy,
            started_at=started_at,
            expires_at=expires_at,
            created_by=data.get("created_by", "user"),
            tasks_completed=data.get("tasks_completed", 0),
            retries_count=data.get("retries_count", 0),
            handoffs_count=data.get("handoffs_count", 0),
            paused_reason=data.get("paused_reason"),
            created_at=created_at,
            updated_at=updated_at
        )

    def _session_to_repo_dict(self, session: AbsenceSession) -> Dict[str, Any]:
        return {
            "absence_id": session.absence_id,
            "mission_id": session.mission_id,
            "status": session.status.value,
            "policy_snapshot": session.policy.model_dump(mode="json"),
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "expires_at": session.expires_at.isoformat() if session.expires_at else None,
            "created_by": session.created_by,
            "tasks_completed": session.tasks_completed,
            "retries_count": session.retries_count,
            "handoffs_count": session.handoffs_count,
            "paused_reason": session.paused_reason,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat()
        }
