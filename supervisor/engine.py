import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from core.events.bus import EventBus
from core.events.schema import Event, EventSeverity, EventType, SupervisorAlertPayload, SupervisorDecisionPayload
from core.missions.manager import MissionManager
from core.missions.models import MissionStatus
from core.tasks.manager import TaskManager
from core.policies.models import PolicyConfig
from supervisor.decisions import SupervisorAction, SupervisorDecision
from supervisor.rules import DeterministicRuleEngine, AnomalyReport
from supervisor.state_machine import SupervisorStateMachine, SupervisorState
from supervisor.reasoning import SupervisoryReasoner
from agents.registry import AgentRegistry
from supervisor.telemetry import TelemetryTracker
from supervisor.approvals import ApprovalManager

logger = logging.getLogger("supervisor.engine")


class SupervisorEngine:
    """
    Central Brain of the AI Work Supervisor.
    Combines deterministic rules (Layer A) with Nemotron reasoning (Layer B).
    Watches the live EventBus, detects failure/drift, and intervenes.
    Coordinates multi-agent workflows, verifies claims, and enforces human approvals.
    """

    def __init__(
        self,
        event_bus: EventBus,
        mission_manager: MissionManager,
        task_manager: TaskManager,
        policy: Optional[PolicyConfig] = None,
        reasoner: Optional[SupervisoryReasoner] = None,
        registry: Optional[AgentRegistry] = None,
        telemetry: Optional[TelemetryTracker] = None,
        approval_manager: Optional[ApprovalManager] = None
    ):
        self.event_bus = event_bus
        self.mission_manager = mission_manager
        self.task_manager = task_manager
        self.policy = policy or PolicyConfig()
        self.rules = DeterministicRuleEngine(policy=self.policy)
        from integrations.nebius.provider import BaseReasoningProvider
        if isinstance(reasoner, BaseReasoningProvider):
            self.reasoner = SupervisoryReasoner(provider=reasoner)
        else:
            self.reasoner = reasoner or SupervisoryReasoner()
        self._default_state_machine = SupervisorStateMachine()
        self._mission_state_machines: Dict[str, SupervisorStateMachine] = {}
        self._mission_events: Dict[str, List[Event]] = {}
        self._mission_tests: Dict[str, List[Event]] = {}
        self._worker_missions: Dict[str, str] = {}
        self._last_active_mission_id: Optional[str] = None
        self.registry = registry
        self.telemetry = telemetry
        self.approval_manager = approval_manager

        self._recent_events: List[Event] = []
        self._recent_tests: List[Event] = []
        self._registered_workers: Dict[str, Any] = {}
        self._rejected_approaches: Dict[str, List[str]] = {}
        self._task_metrics: Dict[str, Dict[str, Any]] = {}  # task_id -> {iterations, tool_calls, start_time}
        self._ci_alerted_builds: set = set()
        self._lock = asyncio.Lock()

        # Subscribe to EventBus
        self.event_bus.subscribe_sync(self.handle_event)

    @property
    def state_machine(self) -> SupervisorStateMachine:
        """Returns the state machine for the most recent active mission or default."""
        if self._last_active_mission_id and self._last_active_mission_id in self._mission_state_machines:
            return self._mission_state_machines[self._last_active_mission_id]
        return self._default_state_machine

    @state_machine.setter
    def state_machine(self, sm: SupervisorStateMachine) -> None:
        self._default_state_machine = sm

    def get_state_machine(self, mission_id: Optional[str] = None) -> SupervisorStateMachine:
        """Returns isolated state machine for the specified mission."""
        if not mission_id:
            return self.state_machine
        if mission_id not in self._mission_state_machines:
            self._mission_state_machines[mission_id] = SupervisorStateMachine()
        return self._mission_state_machines[mission_id]

    def register_worker(self, worker: Any, mission_id: Optional[str] = None) -> None:
        """Register active worker instance for direct supervisor intervention (pause/resume)."""
        self._registered_workers[worker.agent_id] = worker
        mid = mission_id or getattr(worker, "mission_id", None)
        if mid:
            self._worker_missions[worker.agent_id] = mid
            self._last_active_mission_id = mid
        logger.info(f"[SUPERVISOR] Registered worker {worker.agent_id} (mission={mid})")
        if self.registry:
            asyncio.create_task(
                self.registry.register_agent(
                    agent_id=worker.agent_id,
                    agent_type="WORKER",
                    mission_id=mid,
                    agent_instance=worker
                )
            )

    def register_agent(
        self,
        agent: Any,
        agent_type: str = "WORKER",
        mission_id: Optional[str] = None
    ) -> None:
        """Register any agent (PLANNER, WORKER, REVIEWER, VERIFIER, SUPERVISOR) with supervisor & registry."""
        agent_id = getattr(agent, "agent_id", str(agent))
        norm_type = str(agent_type).upper()
        if norm_type == "WORKER" and hasattr(agent, "pause"):
            self._registered_workers[agent_id] = agent
        mid = mission_id or getattr(agent, "mission_id", None)
        if mid:
            self._worker_missions[agent_id] = mid
            self._last_active_mission_id = mid
        logger.info(f"[SUPERVISOR] Registered {norm_type} agent {agent_id} (mission={mid})")
        if self.registry:
            asyncio.create_task(
                self.registry.register_agent(
                    agent_id=agent_id,
                    agent_type=norm_type,
                    mission_id=mid,
                    agent_instance=agent
                )
            )

    def pause_mission_workers(self, mission_id: str) -> None:
        """Pauses only workers belonging to the specified mission."""
        for a_id, w in self._registered_workers.items():
            if self._worker_missions.get(a_id) == mission_id or not self._worker_missions.get(a_id):
                if hasattr(w, "pause"):
                    w.pause()

    def resume_mission_workers(self, mission_id: str) -> None:
        """Resumes only workers belonging to the specified mission."""
        for a_id, w in self._registered_workers.items():
            if self._worker_missions.get(a_id) == mission_id or not self._worker_missions.get(a_id):
                if hasattr(w, "resume"):
                    w.resume()

    def register_rejected_approach(self, mission_id: str, approach: str) -> None:
        """Register a disproven/rejected approach to prevent repetition."""
        if mission_id not in self._rejected_approaches:
            self._rejected_approaches[mission_id] = []
        self._rejected_approaches[mission_id].append(approach)
        logger.info(f"[SUPERVISOR] Registered rejected approach for mission {mission_id}: '{approach}'")

    async def _attach_listeners(self) -> None:
        await self.event_bus.subscribe(self.handle_event)

    async def handle_event(self, event: Event) -> None:
        """Process incoming events through Layer A rules and Layer B reasoning."""
        mid = event.mission_id or "default"
        self._last_active_mission_id = mid
        if mid not in self._mission_state_machines:
            self._mission_state_machines[mid] = SupervisorStateMachine()
        if mid not in self._mission_events:
            self._mission_events[mid] = []
        if mid not in self._mission_tests:
            self._mission_tests[mid] = []

        if event.agent_id and mid and event.agent_id not in self._worker_missions:
            self._worker_missions[event.agent_id] = mid

        async with self._lock:
            self._recent_events.append(event)
            self._mission_events[mid].append(event)
            if len(self._recent_events) > 100:
                self._recent_events.pop(0)
            if len(self._mission_events[mid]) > 100:
                self._mission_events[mid].pop(0)

            # Update metrics per task
            if event.task_id:
                if event.task_id not in self._task_metrics:
                    self._task_metrics[event.task_id] = {
                        "iterations": 0,
                        "tool_calls": 0,
                        "start_time": time.monotonic()
                    }
                if event.type in (EventType.TOOL_CALL, EventType.TOOL_CALLED):
                    self._task_metrics[event.task_id]["tool_calls"] += 1
                elif event.type == EventType.TASK_PROGRESS:
                    self._task_metrics[event.task_id]["iterations"] += 1
                    if event.agent_id:
                        self._task_metrics[event.task_id]["worker_id"] = event.agent_id

            if event.type in (EventType.TEST_RESULT, EventType.TEST_COMPLETED, EventType.TEST_FAILED):
                self._recent_tests.append(event)
                self._mission_tests[mid].append(event)
                if len(self._recent_tests) > 20:
                    self._recent_tests.pop(0)
                if len(self._mission_tests[mid]) > 20:
                    self._mission_tests[mid].pop(0)

        # 1. Danger detected event from tool jail
        if event.type == EventType.DANGER_DETECTED:
            logger.warning(f"[SUPERVISOR] Danger event received: {event.payload}")
            anomaly = AnomalyReport(
                anomaly_type="DANGEROUS_ACTION",
                description=f"Dangerous action detected by tool sandbox: {event.payload.get('error', 'policy violation')}",
                evidence=event.payload,
                recommended_action=SupervisorAction.REQUEST_APPROVAL
            )
            await self._trigger_anomaly_pipeline(event.mission_id, event.task_id, event.agent_id or "worker_01", anomaly)
            return

        # 2. Evaluate tool call safety (prior to/at execution)
        if event.type in (EventType.TOOL_CALL, EventType.TOOL_CALLED):
            tool_name = event.payload.get("tool", "")
            args = event.payload.get("arguments", {})
            task = await self.task_manager.get_task(event.mission_id, event.task_id) if event.task_id else None

            # Check if action repeats a rejected strategy
            args_str = str(args).lower()
            rejected_list = self._rejected_approaches.get(event.mission_id, [])
            for rejected in rejected_list:
                if rejected.lower() in args_str or (rejected.lower() in event.payload.get("target", "").lower()):
                    logger.warning(f"[SUPERVISOR] Worker repeated rejected strategy: '{rejected}'")
                    await self.event_bus.publish(
                        Event(
                            mission_id=event.mission_id,
                            task_id=event.task_id,
                            agent_id=event.agent_id,
                            type=EventType.RECOVERY_STRATEGY_REPEATED,
                            severity=EventSeverity.CRITICAL,
                            payload={
                                "rejected_strategy": rejected,
                                "tool": tool_name,
                                "arguments": args
                            }
                        )
                    )
                    if event.agent_id in self._registered_workers:
                        self._registered_workers[event.agent_id].pause()
                    self.get_state_machine(event.mission_id).set_state(SupervisorState.INVESTIGATING)
                    self._default_state_machine.set_state(SupervisorState.INVESTIGATING)
                    return

            # Check file contention if multiple agents are modifying the same file
            if self.registry and event.agent_id:
                target_path = args.get("path")
                if target_path and tool_name in ("write_file", "edit_file"):
                    holder = await self.registry.check_file_contention(
                        event.agent_id,
                        target_path,
                        event.mission_id or ""
                    )
                    if holder:
                        logger.warning(f"[SUPERVISOR] Contention: {event.agent_id} blocked on {target_path} (active by {holder})")
                        if event.agent_id in self._registered_workers:
                            self._registered_workers[event.agent_id].pause()
                        return

            anomaly = self.rules.evaluate_tool_call(tool_name, args, task=task)
            if anomaly:
                await self._trigger_anomaly_pipeline(event.mission_id, event.task_id, event.agent_id or "worker_01", anomaly)
                return

        # 3. Release file locks upon tool completion or failure
        elif event.type in (EventType.TOOL_COMPLETED, EventType.TOOL_FAILED):
            if self.registry and event.agent_id:
                tool_name = event.payload.get("tool", "")
                if tool_name in ("write_file", "edit_file"):
                    target_path = event.payload.get("arguments", {}).get("path")
                    if target_path:
                        await self.registry.release_file(event.agent_id, target_path)

        # 4. Evaluate test failures (loop detection & no progress)
        elif event.type in (EventType.TEST_RESULT, EventType.TEST_COMPLETED, EventType.TEST_FAILED):
            task = await self.task_manager.get_task(event.mission_id, event.task_id) if event.task_id else None
            if task:
                mission_tests = self._mission_tests.get(mid, self._recent_tests)
                # A. Check repeated failure loop
                loop_anomaly = self.rules.evaluate_test_history(task, mission_tests)
                if loop_anomaly:
                    await self._trigger_anomaly_pipeline(event.mission_id, event.task_id, event.agent_id or "worker_01", loop_anomaly)
                    return

                # B. Check no progress
                no_progress_anomaly = self.rules.evaluate_no_progress(task, mission_tests)
                if no_progress_anomaly:
                    await self._trigger_anomaly_pipeline(event.mission_id, event.task_id, event.agent_id or "worker_01", no_progress_anomaly)
                    return

        # 5. Evaluate independent verification results (detect worker false claims)
        elif event.type == EventType.VERIFICATION_RESULT:
            passed = event.payload.get("passed", 0)
            failed = event.payload.get("failed", 0)
            if failed > 0:
                logger.warning(f"[SUPERVISOR] Verification FAILED for task {event.task_id}: {failed} failures.")
                await self.event_bus.publish(
                    Event(
                        mission_id=event.mission_id,
                        task_id=event.task_id,
                        agent_id="supervisor",
                        type=EventType.VERIFICATION_FAILED,
                        severity=EventSeverity.CRITICAL,
                        payload={
                            "error": f"Verifier found {failed} failing tests. Worker claim of completion rejected.",
                            "passed": passed,
                            "failed": failed,
                            "error_signature": event.payload.get("error_signature")
                        }
                    )
                )
                if event.mission_id and event.task_id:
                    await self.task_manager.reopen_task(
                        event.mission_id,
                        event.task_id,
                        reason=f"Verifier rejected completion: {failed} tests failed"
                    )
                task = await self.task_manager.get_task(event.mission_id, event.task_id) if event.task_id else None
                worker_id = (task.assigned_agent_id if task else None) or self._task_metrics.get(event.task_id, {}).get("worker_id")
                if not worker_id and self._registered_workers:
                    worker_id = next(iter(self._registered_workers.keys()))
                worker_id = worker_id or "worker_01"

                # Actively pause registered worker
                if worker_id in self._registered_workers:
                    self._registered_workers[worker_id].pause()

                anomaly = AnomalyReport(
                    anomaly_type="VERIFICATION_FAILED",
                    description=f"Worker claimed task was done, but independent verifier found {failed} failing tests.",
                    evidence=event.payload,
                    recommended_action=SupervisorAction.DELEGATE
                )
                await self._trigger_anomaly_pipeline(event.mission_id, event.task_id, worker_id, anomaly)
                return

        # 5b. Evaluate independent CI / Jenkins results (detect worker false claims via CI)
        elif event.type in (EventType.CI_BUILD_FAILED, EventType.CI_TEST_RESULTS_AVAILABLE):
            failed = event.payload.get("tests_failed", 0)
            result = event.payload.get("result", "")
            build_id = str(event.payload.get("build_id", ""))
            build_key = f"{event.task_id}_{build_id}" if build_id else f"{event.task_id}_anon"
            if (failed > 0 or result in ("FAILURE", "UNSTABLE")) and build_key not in self._ci_alerted_builds:
                self._ci_alerted_builds.add(build_key)
                logger.warning(f"[SUPERVISOR] Independent CI verification FAILED for task {event.task_id}: {failed} failures.")
                if event.mission_id and event.task_id:
                    await self.task_manager.reopen_task(
                        event.mission_id,
                        event.task_id,
                        reason=f"Jenkins CI rejected completion: {failed} tests failed"
                    )
                task = await self.task_manager.get_task(event.mission_id, event.task_id) if event.task_id else None
                worker_id = (task.assigned_agent_id if task else None) or self._task_metrics.get(event.task_id, {}).get("worker_id")
                if not worker_id and self._registered_workers:
                    worker_id = next(iter(self._registered_workers.keys()))
                worker_id = worker_id or "worker_01"

                # Actively pause registered worker
                if worker_id in self._registered_workers:
                    self._registered_workers[worker_id].pause()

                anomaly = AnomalyReport(
                    anomaly_type="CI_FAILURE",
                    description=f"Worker claimed task was done, but independent Jenkins CI found {failed} failing tests.",
                    evidence=event.payload,
                    recommended_action=SupervisorAction.DELEGATE
                )
                await self._trigger_anomaly_pipeline(event.mission_id, event.task_id, worker_id, anomaly)
                return

        elif event.type == EventType.CI_UNAVAILABLE:
            logger.warning(f"[SUPERVISOR] Jenkins CI is unavailable for mission {event.mission_id}.")
            task = await self.task_manager.get_task(event.mission_id, event.task_id) if event.task_id else None
            worker_id = (task.assigned_agent_id if task else None) or self._task_metrics.get(event.task_id, {}).get("worker_id")
            if not worker_id and self._registered_workers:
                worker_id = next(iter(self._registered_workers.keys()))
            worker_id = worker_id or "worker_01"

            if worker_id in self._registered_workers:
                self._registered_workers[worker_id].pause()

            anomaly = AnomalyReport(
                anomaly_type="CI_UNAVAILABLE",
                description=f"Independent Jenkins CI is unavailable: {event.payload.get('error', 'connection refused')}. Task remains unverified.",
                evidence=event.payload,
                recommended_action=SupervisorAction.PAUSE
            )
            await self._trigger_anomaly_pipeline(event.mission_id, event.task_id, worker_id, anomaly)
            return

        elif event.type == EventType.CI_TIMEOUT:
            logger.warning(f"[SUPERVISOR] Jenkins CI build timed out for task {event.task_id}.")
            task = await self.task_manager.get_task(event.mission_id, event.task_id) if event.task_id else None
            worker_id = (task.assigned_agent_id if task else None) or self._task_metrics.get(event.task_id, {}).get("worker_id")
            if not worker_id and self._registered_workers:
                worker_id = next(iter(self._registered_workers.keys()))
            worker_id = worker_id or "worker_01"

            if worker_id in self._registered_workers:
                self._registered_workers[worker_id].pause()

            anomaly = AnomalyReport(
                anomaly_type="CI_TIMEOUT",
                description="Jenkins CI verification timed out. Task remains unverified.",
                evidence=event.payload,
                recommended_action=SupervisorAction.PAUSE
            )
            await self._trigger_anomaly_pipeline(event.mission_id, event.task_id, worker_id, anomaly)
            return

        elif event.type == EventType.CI_BUILD_COMPLETED:
            passed = event.payload.get("tests_passed", 0)
            failed = event.payload.get("tests_failed", 0)
            if failed == 0 and passed > 0:
                logger.info(f"[SUPERVISOR] Independent Jenkins CI passed ({passed} tests passed). Handing off to Verifier.")

        # 6. Evaluate budget (only on progress or tool calls, avoiding supervisor event recursion)
        if event.type in (EventType.TASK_PROGRESS, EventType.TOOL_CALL, EventType.TOOL_CALLED) and event.task_id and event.task_id in self._task_metrics:
            m = self._task_metrics[event.task_id]
            elapsed = time.monotonic() - m["start_time"]
            budget_anomaly = self.rules.evaluate_budget(m["iterations"], m["tool_calls"], elapsed)
            if budget_anomaly and not m.get("budget_alerted"):
                m["budget_alerted"] = True
                await self._trigger_anomaly_pipeline(event.mission_id, event.task_id, event.agent_id or "worker_01", budget_anomaly)
                return

    async def _trigger_anomaly_pipeline(
        self,
        mission_id: str,
        task_id: Optional[str],
        agent_id: str,
        anomaly: AnomalyReport
    ) -> None:
        """Trigger supervisor alert, Nemotron reasoning, and intervention."""
        logger.warning(f"[SUPERVISOR] anomaly={anomaly.anomaly_type} agent={agent_id} task={task_id}")

        # Transition state machine to INVESTIGATING or PAUSED
        if anomaly.anomaly_type == "DANGEROUS_ACTION":
            self.state_machine.set_state(SupervisorState.PAUSED)
        else:
            self.state_machine.set_state(SupervisorState.INVESTIGATING)

        # Pause registered worker immediately if dangerous or loop
        if agent_id in self._registered_workers:
            self._registered_workers[agent_id].pause()

        # A. Emit Alert Events
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                type=EventType.SUPERVISOR_ALERT,
                severity=EventSeverity.WARNING,
                payload=SupervisorAlertPayload(
                    rule_name=anomaly.anomaly_type,
                    description=anomaly.description,
                    anomaly_type=anomaly.anomaly_type,
                    evidence=anomaly.evidence
                ).model_dump()
            )
        )
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                type=EventType.SUPERVISOR_ANOMALY_DETECTED,
                severity=EventSeverity.WARNING,
                payload={
                    "anomaly_type": anomaly.anomaly_type,
                    "description": anomaly.description,
                    "evidence": anomaly.evidence
                }
            )
        )

        mission = await self.mission_manager.get_mission(mission_id)
        task = await self.task_manager.get_task(mission_id, task_id) if task_id else None

        # B. Call Layer B Nemotron Reasoning with failure fallback
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                type=EventType.SUPERVISOR_REASONING_STARTED,
                payload={"anomaly_type": anomaly.anomaly_type}
            )
        )

        supervisory_ctx = self.reasoner.build_supervisory_context(
            mission_goal=mission.goal if mission else "Unknown",
            current_task_title=task.title if task else "General",
            agent_id=agent_id,
            recent_actions=[e.payload for e in self._recent_events[-6:]],
            error_signature=anomaly.evidence.get("error_signature"),
            constraints=[f"Max repeated failures: {self.policy.pause_after_repeated_failures}"],
            anomaly_type=anomaly.anomaly_type
        )

        try:
            decision = await self.reasoner.decide(supervisory_ctx)
        except Exception as e:
            logger.error(f"[SUPERVISOR] Model reasoning failed: {e}. Falling back to safe deterministic rule.")
            decision = SupervisorDecision(
                action=anomaly.recommended_action,
                severity="high",
                confidence=0.85,
                reason=f"Model fallback: deterministic policy selected {anomaly.recommended_action.value} for {anomaly.anomaly_type}.",
                target_agent="reviewer_01" if anomaly.recommended_action == SupervisorAction.DELEGATE else None,
                source="deterministic_fallback"
            )

        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                type=EventType.SUPERVISOR_REASONING_COMPLETED,
                payload={
                    "decision": decision.action.value,
                    "confidence": decision.confidence,
                    "reason": decision.reason
                }
            )
        )

        # C. Update State Machine
        sm = self.get_state_machine(mission_id)
        sm.transition(decision.action, anomaly_type=anomaly.anomaly_type)
        self._default_state_machine.transition(decision.action, anomaly_type=anomaly.anomaly_type)
        logger.info(f"[SUPERVISOR] action={decision.action.value} state={sm.current_state.value}")

        # D. Emit Decision Event
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id,
                type=EventType.SUPERVISOR_DECISION,
                severity=EventSeverity.WARNING if decision.action != SupervisorAction.CONTINUE else EventSeverity.INFO,
                payload=SupervisorDecisionPayload(
                    decision=decision.action.value,
                    severity=decision.severity,
                    confidence=decision.confidence,
                    reason=decision.reason,
                    recommended_action=decision.recommended_strategy,
                    target_agent=decision.target_agent,
                    model_source=decision.source
                ).model_dump()
            )
        )

        # E. Emit Intervention Event
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id="supervisor",
                type=EventType.SUPERVISOR_INTERVENTION,
                severity=EventSeverity.WARNING,
                payload={
                    "intervention": decision.action.value,
                    "target_agent": decision.target_agent,
                    "reason": decision.reason,
                    "recommended_strategy": decision.recommended_strategy
                }
            )
        )

        # F. Enforce Intervention
        if decision.action == SupervisorAction.PAUSE:
            await self.mission_manager.pause_mission(mission_id, reason=decision.reason)
            if agent_id in self._registered_workers:
                self._registered_workers[agent_id].pause()
        elif decision.action == SupervisorAction.DELEGATE:
            if agent_id in self._registered_workers:
                self._registered_workers[agent_id].pause()
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_id="supervisor",
                    type=EventType.AGENT_ACTION,
                    payload={
                        "action": "DELEGATE_TO_REVIEWER",
                        "target_agent": decision.target_agent or "reviewer_01",
                        "instruction": decision.recommended_strategy or decision.reason
                    }
                )
            )
        elif decision.action == SupervisorAction.REQUEST_APPROVAL:
            target_desc = str(anomaly.evidence.get("target") or anomaly.evidence.get("command") or anomaly.evidence.get("path") or "workspace")
            await self.request_approval(
                mission_id=mission_id,
                agent_id=agent_id,
                action_type=anomaly.anomaly_type,
                target=target_desc,
                reason=decision.reason,
                risk_level="critical" if anomaly.anomaly_type == "DANGEROUS_ACTION" else "high",
                task_id=task_id
            )
        elif decision.action == SupervisorAction.HUMAN_REQUIRED:
            await self.human_required(
                mission_id=mission_id,
                reason=decision.reason,
                agent_id=agent_id,
                task_id=task_id
            )

    # =========================================================================
    # Structured Human Intervention Requests & Control Plane Methods
    # =========================================================================

    async def request_approval(
        self,
        mission_id: str,
        agent_id: str,
        action_type: str,
        target: str,
        reason: str,
        risk_level: str = "high",
        task_id: Optional[str] = None
    ) -> Any:
        """Structured human intervention: request explicit approval for dangerous/protected action."""
        if agent_id in self._registered_workers:
            self._registered_workers[agent_id].pause()

        sm = self.get_state_machine(mission_id)
        sm.transition(SupervisorAction.REQUEST_APPROVAL)
        self._default_state_machine.transition(SupervisorAction.REQUEST_APPROVAL)

        await self.mission_manager.update_status(
            mission_id,
            MissionStatus.WAITING_APPROVAL,
            reason=f"Approval required: {reason}"
        )

        if self.approval_manager:
            return await self.approval_manager.create_request(
                mission_id=mission_id,
                agent_id=agent_id,
                action_type=action_type,
                target=target,
                reason=reason,
                risk_level=risk_level,
                task_id=task_id
            )
        else:
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_id=agent_id,
                    type=EventType.APPROVAL_REQUESTED,
                    severity=EventSeverity.CRITICAL if risk_level in ("high", "critical") else EventSeverity.WARNING,
                    payload={
                        "action_type": action_type,
                        "target": target,
                        "reason": reason,
                        "risk_level": risk_level
                    }
                )
            )

    async def human_required(
        self,
        mission_id: str,
        reason: str,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> Any:
        """Structured intervention: repeated unrecoverable failures trigger HUMAN_REQUIRED."""
        if agent_id and agent_id in self._registered_workers:
            self._registered_workers[agent_id].pause()
        elif not agent_id:
            self.pause_mission_workers(mission_id)

        sm = self.get_state_machine(mission_id)
        sm.transition(SupervisorAction.HUMAN_REQUIRED)
        self._default_state_machine.transition(SupervisorAction.HUMAN_REQUIRED)

        await self.mission_manager.update_status(
            mission_id,
            MissionStatus.WAITING_APPROVAL,
            reason=f"Human intervention required: {reason}"
        )

        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=agent_id or "supervisor",
                type=EventType.SUPERVISOR_HUMAN_REQUIRED,
                severity=EventSeverity.CRITICAL,
                payload={
                    "reason": reason,
                    "target_agent": agent_id,
                    "task_id": task_id
                }
            )
        )

        if self.approval_manager:
            return await self.approval_manager.create_request(
                mission_id=mission_id,
                agent_id=agent_id or "supervisor",
                action_type="HUMAN_REQUIRED",
                target="mission_intervention",
                reason=reason,
                risk_level="critical",
                task_id=task_id
            )

    async def take_control(
        self,
        mission_id: str,
        operator: str = "human_operator",
        reason: str = "Manual override"
    ) -> None:
        """Operator explicitly takes control of mission."""
        self.pause_mission_workers(mission_id)
        sm = self.get_state_machine(mission_id)
        sm.transition(SupervisorAction.TAKE_CONTROL)
        self._default_state_machine.transition(SupervisorAction.TAKE_CONTROL)

        await self.mission_manager.pause_mission(
            mission_id,
            reason=f"Manual control taken by {operator}: {reason}"
        )

        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                agent_id=operator,
                type=EventType.OPERATOR_TAKE_CONTROL,
                severity=EventSeverity.WARNING,
                payload={"operator": operator, "reason": reason}
            )
        )

    async def pause(
        self,
        mission_id: str,
        reason: str = "Paused by supervisor or operator",
        agent_id: Optional[str] = None
    ) -> None:
        """Pause mission or specific agent."""
        if agent_id:
            if agent_id in self._registered_workers:
                self._registered_workers[agent_id].pause()
            if self.registry:
                await self.registry.pause_agent(agent_id)
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    agent_id=agent_id,
                    type=EventType.AGENT_PAUSED,
                    severity=EventSeverity.WARNING,
                    payload={"agent_id": agent_id, "reason": reason}
                )
            )
        else:
            self.pause_mission_workers(mission_id)
            sm = self.get_state_machine(mission_id)
            sm.transition(SupervisorAction.PAUSE)
            self._default_state_machine.transition(SupervisorAction.PAUSE)
            await self.mission_manager.pause_mission(mission_id, reason=reason)
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    type=EventType.OPERATOR_PAUSE,
                    severity=EventSeverity.INFO,
                    payload={"reason": reason}
                )
            )

    async def resume(
        self,
        mission_id: str,
        reason: str = "Resumed by supervisor or operator",
        agent_id: Optional[str] = None
    ) -> None:
        """Resume mission or specific agent."""
        if agent_id:
            if agent_id in self._registered_workers:
                self._registered_workers[agent_id].resume()
            if self.registry:
                await self.registry.resume_agent(agent_id)
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    agent_id=agent_id,
                    type=EventType.AGENT_RESUMED,
                    severity=EventSeverity.INFO,
                    payload={"agent_id": agent_id, "reason": reason}
                )
            )
        else:
            self.resume_mission_workers(mission_id)
            sm = self.get_state_machine(mission_id)
            sm.transition(SupervisorAction.RESUME)
            self._default_state_machine.transition(SupervisorAction.RESUME)
            await self.mission_manager.resume_mission(mission_id)
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    type=EventType.OPERATOR_RESUME,
                    severity=EventSeverity.INFO,
                    payload={"reason": reason}
                )
            )

    async def cancel(
        self,
        mission_id: str,
        reason: str = "Cancelled by supervisor or operator"
    ) -> None:
        """Cancel mission and halt all its agents."""
        self.pause_mission_workers(mission_id)
        sm = self.get_state_machine(mission_id)
        sm.transition(SupervisorAction.CANCEL)
        self._default_state_machine.transition(SupervisorAction.CANCEL)
        await self.mission_manager.cancel_mission(mission_id, reason=reason)
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                type=EventType.OPERATOR_CANCEL,
                severity=EventSeverity.WARNING,
                payload={"reason": reason}
            )
        )
