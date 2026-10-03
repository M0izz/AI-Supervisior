import asyncio
from datetime import datetime, timezone
from enum import Enum
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field, ConfigDict

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.policies.models import PolicyConfig
from core.protocol.schema import WorkProtocolEvent, TaskDispatchPackage
from core.protocol.actions import ActionInfo, TelemetryInfo
from core.protocol.events import ProtocolEventType
from supervisor.rules import DeterministicRuleEngine
from adapters.registry import AdapterRegistry
from adapters.base import AgentAdapter

logger = logging.getLogger("supervisor.watchdogs")


class WatchdogAction(str, Enum):
    """Supervisory action recommended by a watchdog."""
    ALLOW = "ALLOW"
    WARN = "WARN"
    PAUSE = "PAUSE"
    CANCEL = "CANCEL"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class WatchdogDecision(BaseModel):
    """
    Structured outcome of a deterministic watchdog evaluation.
    Provider-agnostic decision containing the rule violation, severity, and recommended intervention.
    """
    action: WatchdogAction = WatchdogAction.ALLOW
    rule_id: Optional[str] = None
    severity: str = "info"  # info, warning, error, critical
    reason: str = "Execution permitted by supervisory watchdogs."
    mission_id: str
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    event_id: Optional[str] = None
    recommended_action: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class InterventionRecord(BaseModel):
    """Audit trail record for a supervisory intervention."""
    intervention_id: str = Field(..., description="Unique intervention identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mission_id: str
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    event_id: Optional[str] = None
    rule_id: str
    action: WatchdogAction
    severity: str
    reason: str
    adapter_cancelled: bool = False
    result: str = "COMPLETED"

    model_config = ConfigDict(arbitrary_types_allowed=True)


def _normalize_event(event: Union[WorkProtocolEvent, Event, Dict[str, Any]]) -> Dict[str, Any]:
    """Extracts a uniform dictionary representation across protocol models and EventBus events."""
    if isinstance(event, WorkProtocolEvent):
        return {
            "event_id": event.event_id,
            "mission_id": event.mission_id,
            "task_id": event.task_id,
            "agent_id": event.agent_id,
            "event_type": event.event_type,
            "action": event.action.model_dump() if event.action else {},
            "telemetry": event.telemetry.model_dump() if event.telemetry else {},
            "payload": event.payload or {},
        }
    elif isinstance(event, Event):
        payload = event.payload or {}
        action = payload.get("action") or {}
        telemetry = payload.get("telemetry") or {}
        event_type = payload.get("event_type") or event.type.value if hasattr(event.type, "value") else str(event.type)
        return {
            "event_id": event.event_id,
            "mission_id": event.mission_id,
            "task_id": event.task_id or payload.get("task_id"),
            "agent_id": event.agent_id or payload.get("agent_id"),
            "event_type": event_type,
            "action": action if isinstance(action, dict) else {},
            "telemetry": telemetry if isinstance(telemetry, dict) else {},
            "payload": payload,
        }
    elif isinstance(event, dict):
        return {
            "event_id": event.get("event_id") or event.get("id"),
            "mission_id": event.get("mission_id", "default"),
            "task_id": event.get("task_id"),
            "agent_id": event.get("agent_id"),
            "event_type": event.get("event_type") or event.get("type", ""),
            "action": event.get("action") or {},
            "telemetry": event.get("telemetry") or {},
            "payload": event.get("payload") or {},
        }
    else:
        return {"mission_id": "unknown", "event_type": "unknown"}


class WatchdogEngine:
    """
    Central Deterministic Supervisory Watchdog Engine.
    Passively monitors live Work Protocol event streams, evaluating safety, scope,
    loop detection, and execution budget boundaries without LLM non-determinism.
    """

    def __init__(
        self,
        policy: Optional[PolicyConfig] = None,
        rule_engine: Optional[DeterministicRuleEngine] = None,
    ):
        self.policy = policy or PolicyConfig()
        self.rule_engine = rule_engine or DeterministicRuleEngine(policy=self.policy)

        # Live per-task monitoring state
        self._task_failure_signatures: Dict[str, List[str]] = {}  # task_id -> list of normalized signatures
        self._task_scopes: Dict[str, List[str]] = {}  # task_id -> list of allowed file patterns
        self._task_turn_counts: Dict[str, int] = {}  # task_id -> action/command counts
        self._task_start_times: Dict[str, float] = {}  # task_id -> start monotonic timestamp
        self._task_budgets: Dict[str, Dict[str, Any]] = {}  # task_id -> budget limits
        self._lock = asyncio.Lock()

    def register_task_scope(
        self,
        task_id: str,
        allowed_files: List[str],
        budget: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """Configures authoritative scope boundaries and budgets for an ongoing task."""
        self._task_scopes[task_id] = [f.replace("\\", "/").strip("./") for f in (allowed_files or [])]
        budget_dict = dict(budget or {})
        if timeout:
            budget_dict["timeout"] = timeout
        self._task_budgets[task_id] = budget_dict
        self._task_start_times.setdefault(task_id, time.monotonic())
        self._task_turn_counts.setdefault(task_id, 0)
        self._task_failure_signatures.setdefault(task_id, [])

    def register_dispatch(self, dispatch: TaskDispatchPackage) -> None:
        """Registers task constraints directly from a TaskDispatchPackage."""
        self.register_task_scope(
            task_id=dispatch.task_id,
            allowed_files=dispatch.allowed_files,
            budget=dispatch.budget,
            timeout=dispatch.timeout,
        )

    def evaluate_event(self, raw_event: Union[WorkProtocolEvent, Event, Dict[str, Any]]) -> WatchdogDecision:
        """
        Deterministically evaluates a live protocol event.
        Guarantees isolation: an unexpected error in one watchdog does not crash supervision.
        """
        try:
            d = _normalize_event(raw_event)
        except Exception as e:
            logger.warning(f"Watchdog received malformed event: {e}")
            return WatchdogDecision(
                action=WatchdogAction.WARN,
                rule_id="MALFORMED_EVENT",
                severity="warning",
                reason=f"Malformed event rejected by watchdog normalizer: {e}",
                mission_id="unknown",
            )

        mission_id = d.get("mission_id") or "default"
        task_id = d.get("task_id")
        agent_id = d.get("agent_id")
        event_id = d.get("event_id")
        event_type = str(d.get("event_type", ""))
        action = d.get("action") or {}
        telemetry = d.get("telemetry") or {}
        payload = d.get("payload") or {}

        # Initialize tracking for task if needed
        if task_id and task_id not in self._task_start_times:
            self._task_start_times[task_id] = time.monotonic()
            self._task_turn_counts[task_id] = 0
            self._task_failure_signatures[task_id] = []

        # --------------------------------------------------------------------
        # 1. DANGEROUS COMMAND INSPECTION
        # --------------------------------------------------------------------
        try:
            cmd = None
            if event_type in ("command.started", ProtocolEventType.COMMAND_STARTED.value):
                cmd = action.get("target") or payload.get("command")
            elif action.get("action_type") == "command_execute":
                cmd = action.get("target") or action.get("parameters", {}).get("command")

            if cmd and isinstance(cmd, str):
                if self.policy.is_command_dangerous(cmd):
                    return WatchdogDecision(
                        action=WatchdogAction.REQUIRE_APPROVAL if self.policy.require_approval_for_destructive_commands else WatchdogAction.CANCEL,
                        rule_id="DANGEROUS_COMMAND",
                        severity="critical",
                        reason=f"Command matches prohibited dangerous pattern: '{cmd}'",
                        mission_id=mission_id,
                        task_id=task_id,
                        agent_id=agent_id,
                        event_id=event_id,
                        recommended_action="CANCEL",
                        evidence={"command": cmd},
                    )
        except Exception as e:
            logger.warning(f"Error evaluating dangerous command rule: {e}")

        # --------------------------------------------------------------------
        # 2. SCOPE VIOLATION INSPECTION
        # --------------------------------------------------------------------
        try:
            target_path = None
            if event_type in ("file.changed", ProtocolEventType.FILE_CHANGED.value):
                target_path = action.get("target") or payload.get("path")
            elif action.get("action_type") in ("file_write", "file_delete", "file_edit"):
                target_path = action.get("target") or action.get("parameters", {}).get("path")

            if target_path and isinstance(target_path, str):
                norm_path = target_path.replace("\\", "/").strip()

                # Check 2A: Path traversal attempt (e.g. '../')
                if ".." in norm_path or norm_path.startswith("/") or re.match(r"^[a-zA-Z]:", norm_path):
                    # Flag path escaping workspace
                    return WatchdogDecision(
                        action=WatchdogAction.CANCEL,
                        rule_id="SCOPE_VIOLATION",
                        severity="error",
                        reason=f"Path traversal or absolute path escape detected: '{target_path}'",
                        mission_id=mission_id,
                        task_id=task_id,
                        agent_id=agent_id,
                        event_id=event_id,
                        recommended_action="CANCEL",
                        evidence={"target_path": target_path},
                    )

                # Check 2B: Protected paths (.git, .env, secrets, schema.sql)
                if self.policy.is_path_protected(norm_path):
                    return WatchdogDecision(
                        action=WatchdogAction.CANCEL,
                        rule_id="SCOPE_VIOLATION",
                        severity="critical",
                        reason=f"Modification to protected path forbidden: '{target_path}'",
                        mission_id=mission_id,
                        task_id=task_id,
                        agent_id=agent_id,
                        event_id=event_id,
                        recommended_action="CANCEL",
                        evidence={"target_path": target_path},
                    )

                # Check 2C: Allowed files whitelist (if registered for this task)
                allowed = self._task_scopes.get(task_id, [])
                if allowed and self.policy.prevent_modifications_outside_task_scope:
                    clean_target = norm_path.strip("./")
                    # Match exact or glob suffix
                    is_allowed = any(
                        clean_target == exp or clean_target.endswith(exp) or clean_target.startswith(exp.rstrip("*"))
                        for exp in allowed
                    )
                    if not is_allowed:
                        return WatchdogDecision(
                            action=WatchdogAction.CANCEL,
                            rule_id="SCOPE_VIOLATION",
                            severity="error",
                            reason=f"File modification '{target_path}' violates declared task scope: {allowed}",
                            mission_id=mission_id,
                            task_id=task_id,
                            agent_id=agent_id,
                            event_id=event_id,
                            recommended_action="CANCEL",
                            evidence={"target_path": target_path, "allowed_scope": allowed},
                        )
        except Exception as e:
            logger.warning(f"Error evaluating scope violation rule: {e}")

        # --------------------------------------------------------------------
        # 3. REPEATED FAILURE / LOOP DETECTION
        # --------------------------------------------------------------------
        try:
            if event_type in ("test.failed", "task.failed", ProtocolEventType.TEST_FAILED.value):
                err = (
                    payload.get("error_signature")
                    or payload.get("error")
                    or payload.get("details")
                    or action.get("result")
                    or "TEST_FAILURE"
                )
                sig = self.rule_engine.normalize_signature(str(err))
                if task_id:
                    failures = self._task_failure_signatures.setdefault(task_id, [])
                    failures.append(sig)

                    threshold = self.policy.pause_after_repeated_failures
                    if len(failures) >= threshold:
                        recent = failures[-threshold:]
                        if len(set(recent)) == 1:
                            return WatchdogDecision(
                                action=WatchdogAction.CANCEL,
                                rule_id="LOOP_DETECTED",
                                severity="critical",
                                reason=(
                                    f"Repeated failure loop detected: {threshold} consecutive failures "
                                    f"with identical signature '{sig}'"
                                ),
                                mission_id=mission_id,
                                task_id=task_id,
                                agent_id=agent_id,
                                event_id=event_id,
                                recommended_action="CANCEL",
                                evidence={
                                    "error_signature": sig,
                                    "consecutive_failures": threshold,
                                    "history": recent,
                                },
                            )
        except Exception as e:
            logger.warning(f"Error evaluating loop detection rule: {e}")

        # --------------------------------------------------------------------
        # 4. EXECUTION BUDGET ENFORCEMENT
        # --------------------------------------------------------------------
        try:
            if task_id:
                # Count action turns
                if event_type in ("command.started", "agent.action.executed", ProtocolEventType.COMMAND_STARTED.value):
                    self._task_turn_counts[task_id] = self._task_turn_counts.get(task_id, 0) + 1
                    turn_count = self._task_turn_counts[task_id]

                    budget = self._task_budgets.get(task_id, {})
                    max_turns = budget.get("max_iterations") or self.policy.max_turns_per_task
                    if turn_count > max_turns:
                        return WatchdogDecision(
                            action=WatchdogAction.CANCEL,
                            rule_id="BUDGET_EXCEEDED",
                            severity="error",
                            reason=f"Turn budget exceeded: {turn_count}/{max_turns} actions executed.",
                            mission_id=mission_id,
                            task_id=task_id,
                            agent_id=agent_id,
                            event_id=event_id,
                            recommended_action="CANCEL",
                            evidence={"turn_count": turn_count, "limit": max_turns},
                        )

                # Check duration budget
                start_time = self._task_start_times.get(task_id, time.monotonic())
                elapsed = time.monotonic() - start_time
                budget = self._task_budgets.get(task_id, {})
                timeout_limit = budget.get("timeout")
                if timeout_limit and elapsed > timeout_limit:
                    return WatchdogDecision(
                        action=WatchdogAction.CANCEL,
                        rule_id="TIMEOUT_EXCEEDED",
                        severity="error",
                        reason=f"Execution duration budget exceeded: {elapsed:.1f}s > {timeout_limit:.1f}s.",
                        mission_id=mission_id,
                        task_id=task_id,
                        agent_id=agent_id,
                        event_id=event_id,
                        recommended_action="CANCEL",
                        evidence={"elapsed_seconds": elapsed, "timeout": timeout_limit},
                    )
        except Exception as e:
            logger.warning(f"Error evaluating execution budget rule: {e}")

        # Default outcome: permitted
        return WatchdogDecision(
            action=WatchdogAction.ALLOW,
            rule_id="PERMITTED",
            severity="info",
            reason="Action permitted by supervisory policy.",
            mission_id=mission_id,
            task_id=task_id,
            agent_id=agent_id,
            event_id=event_id,
        )


class InterventionController:
    """
    Decoupled Supervisory Intervention Controller.
    Receives decisions from WatchdogEngine and executes corresponding adapter control actions
    (e.g., cancelling runaway Claude Code processes, issuing approvals, recording audit records).
    Maintains strict idempotency to prevent repeated cancellation cascades.
    """

    def __init__(
        self,
        watchdog_engine: WatchdogEngine,
        adapter_registry: Optional[AdapterRegistry] = None,
        event_bus: Optional[EventBus] = None,
        approval_repo: Optional[Any] = None,
        event_repo: Optional[Any] = None,
    ):
        self.watchdog_engine = watchdog_engine
        self.adapter_registry = adapter_registry
        self.event_bus = event_bus
        self.approval_repo = approval_repo
        self.event_repo = event_repo

        # Idempotency set: task_ids that have already received terminal intervention
        self._intervened_tasks: Set[str] = set()
        self._audit_records: List[InterventionRecord] = []
        self._lock = asyncio.Lock()

        # Connect to live EventBus if provided
        if self.event_bus:
            self.event_bus.subscribe_sync(self.handle_event)

    def is_task_intervened(self, task_id: Optional[str]) -> bool:
        """Checks if a task has already received an intervention."""
        return bool(task_id and task_id in self._intervened_tasks)

    def get_audit_records(self, task_id: Optional[str] = None) -> List[InterventionRecord]:
        """Returns the intervention audit trail."""
        if task_id:
            return [r for r in self._audit_records if r.task_id == task_id]
        return list(self._audit_records)

    async def handle_event(self, event: Union[WorkProtocolEvent, Event, Dict[str, Any]]) -> WatchdogDecision:
        """
        Consumes a live protocol event, queries WatchdogEngine, and executes interventions.
        Idempotent: will not repeatedly cancel an already terminated task.
        """
        decision = self.watchdog_engine.evaluate_event(event)

        if decision.action == WatchdogAction.ALLOW:
            return decision

        task_id = decision.task_id
        mission_id = decision.mission_id
        agent_id = decision.agent_id or "claude_code"

        # Idempotency check: if task already received terminal intervention, do not cancel again
        async with self._lock:
            if task_id and task_id in self._intervened_tasks:
                logger.info(f"[INTERVENTION] Task {task_id} already intervened; ignoring redundant trigger.")
                return decision

            if decision.action in (WatchdogAction.CANCEL, WatchdogAction.PAUSE, WatchdogAction.REQUIRE_APPROVAL):
                if task_id:
                    self._intervened_tasks.add(task_id)

        adapter_cancelled = False

        # Execute intervention on adapter
        if decision.action in (WatchdogAction.CANCEL, WatchdogAction.PAUSE, WatchdogAction.REQUIRE_APPROVAL):
            if self.adapter_registry and task_id:
                adapter = self.adapter_registry.get_adapter(agent_id) or self.adapter_registry.get_adapter("claude_code")
                if adapter:
                    try:
                        adapter_cancelled = await adapter.cancel(task_id)
                        logger.warning(
                            f"[INTERVENTION] Cancelled adapter '{adapter.identity.adapter_id}' "
                            f"for task {task_id} due to {decision.rule_id} ({decision.reason})"
                        )
                    except Exception as e:
                        logger.error(f"[INTERVENTION] Error cancelling adapter for task {task_id}: {e}")

        # Integrate with human approval repository if action requires approval
        if decision.action == WatchdogAction.REQUIRE_APPROVAL and self.approval_repo and task_id:
            try:
                await self.approval_repo.create(
                    mission_id=mission_id,
                    task_id=task_id,
                    action_type=decision.rule_id or "DANGEROUS_ACTION",
                    description=decision.reason,
                )
            except Exception as e:
                logger.warning(f"[INTERVENTION] Failed to persist approval request: {e}")

        # Record audit trail
        import uuid
        record = InterventionRecord(
            intervention_id=f"intv_{uuid.uuid4().hex[:12]}",
            mission_id=mission_id,
            task_id=task_id,
            agent_id=agent_id,
            event_id=decision.event_id,
            rule_id=decision.rule_id or "UNKNOWN_RULE",
            action=decision.action,
            severity=decision.severity,
            reason=decision.reason,
            adapter_cancelled=adapter_cancelled,
            result="CANCELLED" if adapter_cancelled else "RECORDED",
        )
        self._audit_records.append(record)

        # Emit supervisor.intervention event onto EventBus
        if self.event_bus:
            intv_event = Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id="supervisor",
                type=EventType.SUPERVISOR_INTERVENTION,
                severity=EventSeverity.CRITICAL if decision.severity in ("critical", "error") else EventSeverity.WARNING,
                payload={
                    "event_type": ProtocolEventType.SUPERVISOR_INTERVENED.value,
                    "provider": "supervisor",
                    "rule_id": decision.rule_id,
                    "action": decision.action.value,
                    "reason": decision.reason,
                    "evidence": decision.evidence,
                    "adapter_cancelled": adapter_cancelled,
                    "audit_record": record.model_dump(mode="json"),
                },
            )
            try:
                await self.event_bus.publish(intv_event)
            except Exception as e:
                logger.warning(f"[INTERVENTION] Failed to publish intervention event: {e}")

        # Persist intervention record to SQLite if repository available
        if self.event_repo:
            try:
                await self.event_repo.append({
                    "mission_id": mission_id,
                    "task_id": task_id,
                    "agent_id": "supervisor",
                    "event_type": ProtocolEventType.SUPERVISOR_INTERVENED.value,
                    "severity": decision.severity,
                    "payload": record.model_dump(mode="json"),
                })
            except Exception as e:
                logger.warning(f"[INTERVENTION] Failed to persist intervention to SQLite: {e}")


        return decision
