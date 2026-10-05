import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from adapters.registry import AdapterRegistry
from core.routing.models import (
    RoutingCandidate,
    RoutingDecision,
    RoutingDecisionType,
    RoutingRequest,
    TaskRequirements,
)
from core.routing.scorer import RoutingScorer

logger = logging.getLogger("supervisor.routing.engine")


class RoutingEngine:
    """
    Supervisory Dynamic Agent Router.
    Determines the best worker agent for a task based on explicit task requirements,
    adapter capabilities, current availability, and empirical reliability history.

    CORE PRODUCT INVARIANT:
    Routing is a Supervisor decision. Agents do NOT self-select or influence their score.
    """

    def __init__(
        self,
        adapter_registry: Optional[AdapterRegistry] = None,
        repository: Optional[Any] = None,
        routing_repo: Optional[Any] = None,
        verification_repo: Optional[Any] = None,
        handoff_repo: Optional[Any] = None,
        event_bus: Optional[EventBus] = None,
        memory_store: Optional[Any] = None,
    ):
        self.adapter_registry = adapter_registry
        self.repository = repository or routing_repo
        self.verification_repo = verification_repo
        self.handoff_repo = handoff_repo
        self.event_bus = event_bus
        self.memory_store = memory_store
        self._lock = asyncio.Lock()

    async def collect_agent_metrics(self, agent_id: str) -> Dict[str, Any]:
        """
        Gathers empirical performance metrics for an agent from SQLite repositories.
        Safe against cold-start environments with zero historical records.
        """
        metrics: Dict[str, Any] = {
            "verified_successes": 0,
            "verification_failures": 0,
            "handoffs": 0,
            "watchdog_interventions": 0,
        }

        # Query verifications table for this agent
        if self.verification_repo and hasattr(self.verification_repo, "db"):
            try:
                conn = await self.verification_repo.db.get_connection()
                try:
                    cursor = await conn.execute(
                        "SELECT status, count(*) FROM verifications WHERE details LIKE ? GROUP BY status;",
                        (f'%"assigned_agent_id": "{agent_id}"%',),
                    )
                    rows = await cursor.fetchall()
                    for status, count in rows:
                        if status in ("PASSED", "ACCEPT"):
                            metrics["verified_successes"] += count
                        elif status in ("FAILED", "REJECT"):
                            metrics["verification_failures"] += count
                finally:
                    await conn.close()
            except Exception as e:
                logger.debug(f"[ROUTER] Non-fatal error reading verification metrics for {agent_id}: {e}")

        # Query handoffs table where this agent was the failing source agent
        if self.handoff_repo and hasattr(self.handoff_repo, "db"):
            try:
                conn = await self.handoff_repo.db.get_connection()
                try:
                    cursor = await conn.execute(
                        "SELECT count(*) FROM handoffs WHERE source_agent_id = ?;",
                        (agent_id,),
                    )
                    row = await cursor.fetchone()
                    if row:
                        metrics["handoffs"] = row[0]
                finally:
                    await conn.close()
            except Exception as e:
                logger.debug(f"[ROUTER] Non-fatal error reading handoff metrics for {agent_id}: {e}")

        # Augment with memory-derived empirical performance if memory_store is available (Phase 7)
        if self.memory_store and hasattr(self.memory_store, "query"):
            try:
                from memory.models import MemoryQuery, MemoryStatus, MemoryType
                mem_records = await self.memory_store.query(MemoryQuery(limit=100))
                for r in mem_records:
                    if r.provenance.created_by == agent_id or agent_id in r.content or (r.details and agent_id in r.details):
                        if r.status == MemoryStatus.VERIFIED:
                            metrics["verified_successes"] += 1
                        elif r.status == MemoryStatus.REJECTED or r.memory_type == MemoryType.REJECTED_APPROACH:
                            metrics["verification_failures"] += 1
            except Exception as e:
                logger.debug(f"[ROUTER] Non-fatal error querying memory metrics: {e}")

        return metrics

    async def route(self, request: RoutingRequest) -> RoutingDecision:
        """
        Executes a deterministic routing decision for the given request.
        1. Emits routing.started event.
        2. Evaluates each candidate's capabilities, availability, and reliability.
        3. Enforces eligibility gates and calculates deterministic scores.
        4. Ranks candidates and resolves ties deterministically.
        5. Persists decision to SQLite WAL and emits lifecycle events.
        """
        async with self._lock:
            routing_id = request.routing_id or f"rtg_{uuid.uuid4().hex[:12]}"
            logger.info(
                f"[ROUTER] Initiating routing {routing_id} for task {request.task_id} "
                f"(mission {request.mission_id}, type {request.task_requirements.task_type})"
            )

            # 1. Emit routing.started event
            await self._emit_event(
                "routing.started",
                routing_id=routing_id,
                mission_id=request.mission_id,
                task_id=request.task_id,
                payload={
                    "task_type": request.task_requirements.task_type,
                    "required_capabilities": request.task_requirements.required_capabilities,
                    "preferred_capabilities": request.task_requirements.preferred_capabilities,
                    "excluded_agents": request.task_requirements.excluded_agent_ids,
                },
            )

            if not self.adapter_registry:
                err_msg = "AdapterRegistry is not configured in RoutingEngine."
                logger.error(f"[ROUTER] {err_msg}")
                decision = RoutingDecision(
                    routing_id=routing_id,
                    mission_id=request.mission_id,
                    task_id=request.task_id,
                    decision=RoutingDecisionType.REQUIRE_REVIEW,
                    decision_reason=err_msg,
                    requirements=request.task_requirements,
                )
                await self._persist_decision(decision)
                await self._emit_event(
                    "routing.failed",
                    routing_id=routing_id,
                    mission_id=request.mission_id,
                    task_id=request.task_id,
                    decision=RoutingDecisionType.REQUIRE_REVIEW.value,
                    payload={"error": err_msg},
                )
                return decision

            # 2. Gather candidates
            registered_identities = self.adapter_registry.list_adapters()
            evaluated_candidates: List[RoutingCandidate] = []

            for ident in registered_identities:
                agent_id = ident.adapter_id
                if request.candidate_agent_ids and agent_id not in request.candidate_agent_ids:
                    continue

                adapter = self.adapter_registry.get_adapter(agent_id)
                if not adapter:
                    continue

                # Query empirical historical metrics (augmented with caller context if provided)
                db_metrics = await self.collect_agent_metrics(agent_id)
                override_metrics = request.context.get("historical_metrics", {}).get(agent_id, {})
                metrics = {**db_metrics, **override_metrics}

                # Evaluate candidate
                candidate = await RoutingScorer.evaluate_candidate(
                    agent_id=agent_id,
                    adapter=adapter,
                    requirements=request.task_requirements,
                    historical_metrics=metrics,
                )
                evaluated_candidates.append(candidate)

                # Emit candidate evaluation event
                await self._emit_event(
                    "routing.candidate.evaluated",
                    routing_id=routing_id,
                    mission_id=request.mission_id,
                    task_id=request.task_id,
                    payload={
                        "candidate_agent_id": agent_id,
                        "is_eligible": candidate.is_eligible,
                        "score": candidate.score,
                        "summary": candidate.evaluation_summary,
                    },
                )

            # 3. Rank candidates
            ranked = RoutingScorer.rank_candidates(evaluated_candidates)
            eligible_candidates = [c for c in ranked if c.is_eligible]

            # 4. Formulate Decision
            if not eligible_candidates:
                reasons_summary = "; ".join(
                    f"{c.agent_id}: {'; '.join(c.ineligibility_reasons)}"
                    for c in evaluated_candidates
                )
                reason = (
                    f"No eligible agent found for task {request.task_id}. "
                    f"Required capabilities: {request.task_requirements.required_capabilities}. "
                    f"Candidate evaluation: [{reasons_summary}]"
                )
                decision = RoutingDecision(
                    routing_id=routing_id,
                    mission_id=request.mission_id,
                    task_id=request.task_id,
                    decision=RoutingDecisionType.NO_ELIGIBLE_AGENT,
                    selected_agent_id=None,
                    selected_adapter_id=None,
                    score=0.0,
                    decision_reason=reason,
                    candidates=ranked,
                    requirements=request.task_requirements,
                )
                await self._persist_decision(decision)
                await self._emit_event(
                    "routing.failed",
                    routing_id=routing_id,
                    mission_id=request.mission_id,
                    task_id=request.task_id,
                    decision=RoutingDecisionType.NO_ELIGIBLE_AGENT.value,
                    payload={"reason": reason},
                )
                return decision

            selected = eligible_candidates[0]
            alternatives = [c for c in eligible_candidates if c.agent_id != selected.agent_id]

            # Construct explainable decision rationale (Section 15)
            explanation_lines = [
                f"Selected: {selected.agent_id} (Score: {selected.score:.1f})",
                "Why:",
                f"- Required capabilities: {len(request.task_requirements.required_capabilities)}/{len(request.task_requirements.required_capabilities)} satisfied",
                f"- Preferred capabilities: {int(selected.score_breakdown.get('preferred_capability_match', 0.0) / RoutingScorer.PREFERRED_CAPABILITY_POINTS)}/{len(request.task_requirements.preferred_capabilities)} matched",
                f"- Available: {selected.is_available} ({selected.availability})",
                f"- Verified success history: {selected.historical_metrics.get('verified_successes', 0)}",
                f"- Verification failures: {selected.historical_metrics.get('verification_failures', 0)}",
                f"- Handoffs: {selected.historical_metrics.get('handoffs', 0)}",
            ]
            if alternatives:
                explanation_lines.append("Alternatives:")
                for alt in alternatives:
                    explanation_lines.append(f"- {alt.agent_id}: eligible, score {alt.score:.1f}")

            decision_reason = "\n".join(explanation_lines)

            decision = RoutingDecision(
                routing_id=routing_id,
                mission_id=request.mission_id,
                task_id=request.task_id,
                decision=RoutingDecisionType.ROUTE,
                selected_agent_id=selected.agent_id,
                selected_adapter_id=selected.adapter_id,
                score=selected.score,
                decision_reason=decision_reason,
                candidates=ranked,
                requirements=request.task_requirements,
            )

            # 5. Persist decision & emit routing.completed event
            await self._persist_decision(decision)
            await self._emit_event(
                "routing.completed",
                routing_id=routing_id,
                mission_id=request.mission_id,
                task_id=request.task_id,
                selected_agent=selected.agent_id,
                decision=RoutingDecisionType.ROUTE.value,
                payload={
                    "selected_agent_id": selected.agent_id,
                    "selected_adapter_id": selected.adapter_id,
                    "score": selected.score,
                    "decision_reason": decision_reason,
                },
            )

            return decision

    async def _persist_decision(self, decision: RoutingDecision) -> None:
        """Persists the routing decision record to SQLite repository if configured."""
        if self.repository:
            try:
                candidates_data = [c.model_dump(mode="json") for c in decision.candidates]
                requirements_data = (
                    decision.requirements.model_dump(mode="json")
                    if decision.requirements
                    else {}
                )
                await self.repository.save(
                    mission_id=decision.mission_id,
                    task_id=decision.task_id,
                    decision=decision.decision.value,
                    decision_reason=decision.decision_reason,
                    selected_agent_id=decision.selected_agent_id,
                    selected_adapter_id=decision.selected_adapter_id,
                    score=decision.score,
                    candidates=candidates_data,
                    requirements=requirements_data,
                    routing_id=decision.routing_id,
                )
            except Exception as e:
                logger.warning(f"[ROUTER] Failed to persist routing decision to SQLite: {e}")

    async def _emit_event(
        self,
        event_name: str,
        routing_id: str,
        mission_id: str,
        task_id: str,
        selected_agent: Optional[str] = None,
        decision: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Publishes a structured routing lifecycle event onto the EventBus."""
        if not self.event_bus:
            return

        ev = Event(
            mission_id=mission_id,
            task_id=task_id,
            agent_id="router",
            type=EventType.AGENT_ACTION,
            severity=EventSeverity.INFO if event_name != "routing.failed" else EventSeverity.WARNING,
            payload={
                "event_type": event_name,
                "routing_id": routing_id,
                "selected_agent": selected_agent,
                "decision": decision,
                **(payload or {}),
            },
        )
        try:
            await self.event_bus.publish(ev)
        except Exception as e:
            logger.warning(f"[ROUTER] Failed to publish {event_name} event: {e}")
