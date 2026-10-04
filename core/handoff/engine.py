import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.protocol.schema import TaskDispatchPackage
from core.protocol.events import ProtocolEventType
from core.tasks.models import Task, TaskStatus
from adapters.registry import AdapterRegistry
from adapters.base import AgentAdapter
from core.handoff.models import (
    HandoffContextPackage,
    HandoffRecord,
    HandoffResult,
    HandoffStatus,
    HandoffTrigger,
)
from core.handoff.context import HandoffContextBuilder

logger = logging.getLogger("supervisor.handoff.engine")


class HandoffEngine:
    """
    Supervisory Task Handoff Engine.
    Coordinates deterministic, provenance-preserving transfer of tasks between agents
    when the primary agent stalls, loops, or fails independent verification.
    
    CORE PRODUCT INVARIANT:
    A handoff transfers responsibility, not authority.
    The Supervisor owns task state, context, worktree boundaries, and verification.
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        adapter_registry: Optional[AdapterRegistry] = None,
        repository: Optional[Any] = None,
        handoff_repo: Optional[Any] = None,
        task_manager: Optional[Any] = None,
        worktree_manager: Optional[Any] = None,
        verification_engine: Optional[Any] = None,
        routing_engine: Optional[Any] = None,
        max_handoffs_per_task: int = 3,
    ):
        self.event_bus = event_bus
        self.adapter_registry = adapter_registry
        self.repository = repository or handoff_repo
        self.task_manager = task_manager
        self.worktree_manager = worktree_manager
        self.verification_engine = verification_engine
        self.routing_engine = routing_engine
        self.max_handoffs_per_task = max_handoffs_per_task

        # Task handoff tracking: task_id -> list of handoff records
        self._task_handoff_history: Dict[str, List[HandoffRecord]] = {}
        self._lock = asyncio.Lock()

    def get_task_handoff_count(self, task_id: str) -> int:
        """Returns the number of handoffs previously executed for a task."""
        return len(self._task_handoff_history.get(task_id, []))

    async def can_handoff(
        self,
        task_id: str,
        target_agent_id: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Determines whether a task is eligible for handoff.
        Enforces loop protection, budget ceilings, and target adapter availability.
        """
        count = self.get_task_handoff_count(task_id)
        if count >= self.max_handoffs_per_task:
            return (
                False,
                f"HANDOFF_LIMIT_REACHED: Task {task_id} has reached the maximum handoff ceiling "
                f"({count}/{self.max_handoffs_per_task}). Operator review required.",
            )

        if not self.adapter_registry:
            return False, "AdapterRegistry not configured."

        target_adapter = self.adapter_registry.get_adapter(target_agent_id)
        if not target_adapter:
            return False, f"Target adapter '{target_agent_id}' is not registered."

        try:
            avail = await target_adapter.check_availability()
            if not avail.available:
                return False, f"Target adapter '{target_agent_id}' is unavailable: {avail.message}"
        except Exception as e:
            return False, f"Target adapter '{target_agent_id}' availability check failed: {e}"

        return True, None

    async def execute_handoff(
        self,
        mission_id: str,
        task_id: str,
        source_agent_id: str,
        target_agent_id: str,
        trigger: HandoffTrigger,
        reason: str,
        objective: str,
        workspace: str,
        allowed_scope: Optional[List[str]] = None,
        verification_requirements: Optional[List[str]] = None,
        failure_signature: Optional[str] = None,
        consecutive_failures: int = 0,
        watchdog_evidence: Optional[Dict[str, Any]] = None,
        verification_evidence: Optional[Dict[str, Any]] = None,
        source_claim: Optional[Dict[str, Any]] = None,
        executed_commands: Optional[List[str]] = None,
        timeout: Optional[float] = None,
        verify_after: bool = False,
        test_commands: Optional[List[str]] = None,
    ) -> HandoffResult:
        """
        Executes an end-to-end task handoff from source agent to target agent.
        1. Checks loop limits and target availability.
        2. Cancels/halts the source agent.
        3. Builds a provenance-preserving HandoffContextPackage.
        4. Dispatches the target agent in the same isolated worktree.
        5. Persists the handoff record to SQLite and publishes events.
        """
        handoff_id = f"hnd_{uuid.uuid4().hex[:12]}"

        # 0. Dynamic routing resolution if target_agent_id is unspecified or "auto"
        if (not target_agent_id or target_agent_id == "auto") and self.routing_engine:
            from core.routing.models import RoutingRequest, TaskRequirements
            prior_failed_agents = [
                h.source_agent_id for h in self._task_handoff_history.get(task_id, [])
            ]
            excluded_agents = list(set([source_agent_id] + prior_failed_agents))

            req = RoutingRequest(
                mission_id=mission_id,
                task_id=task_id,
                task_objective=objective,
                task_requirements=TaskRequirements(
                    task_type="bug_fix",
                    excluded_agent_ids=excluded_agents,
                ),
            )
            route_decision = await self.routing_engine.route(req)
            if route_decision.decision.value == "ROUTE" and route_decision.selected_agent_id:
                target_agent_id = route_decision.selected_agent_id
                logger.info(f"[HANDOFF] Dynamically routed handoff target to '{target_agent_id}'")
            else:
                deny_reason = f"Routing failed to find target agent: {route_decision.decision_reason}"
                record = HandoffRecord(
                    handoff_id=handoff_id,
                    mission_id=mission_id,
                    task_id=task_id,
                    source_agent_id=source_agent_id,
                    target_agent_id="none",
                    trigger=trigger,
                    status=HandoffStatus.REJECTED,
                    reason=reason,
                    error=deny_reason,
                )
                await self._persist_record(record)
                await self._emit_handoff_event(record, "handoff.failed", deny_reason)
                return HandoffResult(
                    handoff_id=handoff_id,
                    task_id=task_id,
                    success=False,
                    status=HandoffStatus.REJECTED,
                    source_agent_id=source_agent_id,
                    target_agent_id="none",
                    error=deny_reason,
                )

        logger.info(
            f"[HANDOFF] Initiating handoff {handoff_id}: Task {task_id} "
            f"from '{source_agent_id}' to '{target_agent_id}' ({trigger.value}: {reason})"
        )

        # 1. Validate handoff eligibility & loop protection
        eligible, deny_reason = await self.can_handoff(task_id, target_agent_id)
        if not eligible:
            logger.warning(f"[HANDOFF] Handoff rejected for task {task_id}: {deny_reason}")
            record = HandoffRecord(
                handoff_id=handoff_id,
                mission_id=mission_id,
                task_id=task_id,
                source_agent_id=source_agent_id,
                target_agent_id=target_agent_id,
                trigger=trigger,
                status=HandoffStatus.REJECTED,
                reason=reason,
                error=deny_reason,
            )
            await self._persist_record(record)
            await self._emit_handoff_event(record, "handoff.failed", deny_reason)

            # Signal that human operator review is required
            if self.event_bus:
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=task_id,
                        agent_id="supervisor",
                        type=EventType.SUPERVISOR_HUMAN_REQUIRED,
                        severity=EventSeverity.CRITICAL,
                        payload={
                            "handoff_id": handoff_id,
                            "reason": deny_reason,
                            "task_id": task_id,
                        },
                    )
                )

            return HandoffResult(
                handoff_id=handoff_id,
                task_id=task_id,
                success=False,
                status=HandoffStatus.REJECTED,
                source_agent_id=source_agent_id,
                target_agent_id=target_agent_id,
                error=deny_reason,
            )

        # 2. Cancel source agent to release worktree locks
        if self.adapter_registry:
            source_adapter = self.adapter_registry.get_adapter(source_agent_id)
            if source_adapter:
                try:
                    await source_adapter.cancel(task_id)
                    logger.info(f"[HANDOFF] Cancelled source agent '{source_agent_id}' for task {task_id}")
                except Exception as e:
                    logger.warning(f"[HANDOFF] Non-fatal error cancelling source agent '{source_agent_id}': {e}")

        # 3. Build structured Handoff Context Package
        prior_history = [
            h.model_dump(mode="json")
            for h in self._task_handoff_history.get(task_id, [])
        ]
        handoff_idx = len(prior_history) + 1

        context_package = HandoffContextBuilder.build(
            mission_id=mission_id,
            task_id=task_id,
            objective=objective,
            workspace=workspace,
            source_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            trigger=trigger,
            reason=reason,
            allowed_scope=allowed_scope,
            failure_signature=failure_signature,
            consecutive_failures=consecutive_failures,
            watchdog_evidence=watchdog_evidence,
            verification_evidence=verification_evidence,
            source_claim=source_claim,
            executed_commands=executed_commands,
            handoff_history=prior_history,
            handoff_count=handoff_idx,
        )

        # 4. Create and persist HandoffRecord
        record = HandoffRecord(
            handoff_id=handoff_id,
            mission_id=mission_id,
            task_id=task_id,
            source_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            trigger=trigger,
            status=HandoffStatus.TRANSFERRED,
            reason=reason,
            context_package=context_package,
            transferred_at=datetime.now(timezone.utc),
        )
        self._task_handoff_history.setdefault(task_id, []).append(record)
        await self._persist_record(record)

        # 5. Emit handoff events
        await self._emit_handoff_event(record, "handoff.requested", reason)
        await self._emit_handoff_event(record, "handoff.prepared", "Context package built")
        await self._emit_handoff_event(record, "handoff.started", f"Transferring to {target_agent_id}")

        # 6. Update Task in TaskManager to reflect target agent assignment
        if self.task_manager:
            try:
                task = await self.task_manager.get_task(mission_id, task_id)
                if task:
                    task.assigned_agent_id = target_agent_id
                    task.status = TaskStatus.IN_PROGRESS
                    task.metadata["handoff_count"] = handoff_idx
                    task.metadata["last_handoff_id"] = handoff_id
                    task.metadata["last_source_agent"] = source_agent_id
                    if self.task_manager._repository:
                        await self.task_manager._repository.save(task)
            except Exception as e:
                logger.warning(f"[HANDOFF] Failed to update task assignment in TaskManager: {e}")

        # 7. Formulate TaskDispatchPackage for Target Agent
        # WORKTREE CONTINUITY INVARIANT: Target agent operates in the exact same worktree
        target_dispatch = TaskDispatchPackage(
            task_id=task_id,
            mission_id=mission_id,
            objective=objective,
            workspace=workspace,
            allowed_files=allowed_scope or [],
            verification_requirements=verification_requirements or [],
            timeout=timeout or 300.0,
            context={
                "handoff": context_package.model_dump(mode="json"),
                "source_agent_id": source_agent_id,
                "handoff_id": handoff_id,
                "failure_reason": reason,
            },
        )

        # 8. Execute Target Agent
        target_adapter = self.adapter_registry.get_adapter(target_agent_id) if self.adapter_registry else None
        if not target_adapter:
            err = f"Target adapter '{target_agent_id}' missing at execution time."
            record.status = HandoffStatus.FAILED
            record.error = err
            await self._persist_record(record)
            await self._emit_handoff_event(record, "handoff.failed", err)
            return HandoffResult(
                handoff_id=handoff_id,
                task_id=task_id,
                success=False,
                status=HandoffStatus.FAILED,
                source_agent_id=source_agent_id,
                target_agent_id=target_agent_id,
                context_package=context_package,
                error=err,
            )

        try:
            logger.info(f"[HANDOFF] Executing target agent '{target_agent_id}' for task {task_id}")
            exec_result = await target_adapter.execute(target_dispatch)

            record.completed_at = datetime.now(timezone.utc)
            if exec_result.status.value in ("COMPLETED", "success"):
                record.status = HandoffStatus.COMPLETED
                record.result = exec_result.summary
                await self._persist_record(record)
                await self._emit_handoff_event(record, "handoff.completed", exec_result.summary)

                # Termination through Independent Verification
                verification_result = None
                if verify_after and self.verification_engine:
                    from core.verification.models import VerificationContext
                    v_ctx = VerificationContext(
                        task_id=task_id,
                        mission_id=mission_id,
                        workspace=workspace,
                        agent_id=target_agent_id,
                        verification_requirements=test_commands or [],
                        allowed_files=allowed_scope or [],
                        completion_claim={"summary": exec_result.summary},
                    )
                    verification_result = await self.verification_engine.verify(v_ctx)

                return HandoffResult(
                    handoff_id=handoff_id,
                    task_id=task_id,
                    success=True,
                    status=HandoffStatus.COMPLETED,
                    source_agent_id=source_agent_id,
                    target_agent_id=target_agent_id,
                    context_package=context_package,
                    verification_result=verification_result,
                )
            else:
                err = exec_result.failure_reason or f"Target agent failed with status {exec_result.status.value}"
                record.status = HandoffStatus.FAILED
                record.error = err
                await self._persist_record(record)
                await self._emit_handoff_event(record, "handoff.failed", err)
                return HandoffResult(
                    handoff_id=handoff_id,
                    task_id=task_id,
                    success=False,
                    status=HandoffStatus.FAILED,
                    source_agent_id=source_agent_id,
                    target_agent_id=target_agent_id,
                    context_package=context_package,
                    error=err,
                )
        except Exception as e:
            logger.error(f"[HANDOFF] Target agent execution raised exception: {e}", exc_info=True)
            record.status = HandoffStatus.FAILED
            record.error = str(e)
            record.completed_at = datetime.now(timezone.utc)
            await self._persist_record(record)
            await self._emit_handoff_event(record, "handoff.failed", str(e))
            return HandoffResult(
                handoff_id=handoff_id,
                task_id=task_id,
                success=False,
                status=HandoffStatus.FAILED,
                source_agent_id=source_agent_id,
                target_agent_id=target_agent_id,
                context_package=context_package,
                error=str(e),
            )

    async def _persist_record(self, record: HandoffRecord) -> None:
        """Persists handoff record to SQLite repository if configured."""
        if self.repository:
            try:
                await self.repository.save(
                    mission_id=record.mission_id,
                    task_id=record.task_id,
                    source_agent_id=record.source_agent_id,
                    target_agent_id=record.target_agent_id,
                    trigger=record.trigger.value,
                    status=record.status.value,
                    reason=record.reason,
                    context_package=record.context_package.model_dump(mode="json") if record.context_package else None,
                    handoff_id=record.handoff_id,
                    result=record.result,
                    error=record.error,
                )
            except Exception as e:
                logger.warning(f"[HANDOFF] Failed to persist handoff to SQLite: {e}")

    async def _emit_handoff_event(
        self,
        record: HandoffRecord,
        event_name: str,
        detail: str,
    ) -> None:
        """Emits a structured handoff lifecycle event onto the EventBus."""
        if not self.event_bus:
            return

        ev = Event(
            mission_id=record.mission_id,
            task_id=record.task_id,
            agent_id="supervisor",
            type=EventType.AGENT_ACTION,
            severity=EventSeverity.INFO if record.status != HandoffStatus.FAILED else EventSeverity.ERROR,
            payload={
                "event_type": event_name,
                "handoff_id": record.handoff_id,
                "source_agent_id": record.source_agent_id,
                "target_agent_id": record.target_agent_id,
                "trigger": record.trigger.value,
                "status": record.status.value,
                "detail": detail,
            },
        )
        try:
            await self.event_bus.publish(ev)
        except Exception as e:
            logger.warning(f"[HANDOFF] Failed to publish event {event_name}: {e}")
