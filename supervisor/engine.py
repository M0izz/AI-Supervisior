import asyncio
import logging
from typing import Any, Dict, List, Optional
from core.events.bus import EventBus
from core.events.schema import Event, EventSeverity, EventType, SupervisorAlertPayload, SupervisorDecisionPayload
from core.missions.manager import MissionManager
from core.tasks.manager import TaskManager
from core.policies.models import PolicyConfig
from supervisor.decisions import SupervisorAction, SupervisorDecision
from supervisor.rules import DeterministicRuleEngine
from supervisor.state_machine import SupervisorStateMachine, SupervisorState
from supervisor.reasoning import SupervisoryReasoner

logger = logging.getLogger("supervisor.engine")


class SupervisorEngine:
    """
    Central Brain of the AI Work Supervisor.
    Combines deterministic rules (Layer A) with Nemotron reasoning (Layer B).
    """

    def __init__(
        self,
        event_bus: EventBus,
        mission_manager: MissionManager,
        task_manager: TaskManager,
        policy: Optional[PolicyConfig] = None,
        reasoner: Optional[SupervisoryReasoner] = None
    ):
        self.event_bus = event_bus
        self.mission_manager = mission_manager
        self.task_manager = task_manager
        self.policy = policy or PolicyConfig()
        self.rules = DeterministicRuleEngine(policy=self.policy)
        self.reasoner = reasoner or SupervisoryReasoner()
        self.state_machine = SupervisorStateMachine()

        self._recent_events: List[Event] = []
        self._recent_tests: List[Event] = []
        self._lock = asyncio.Lock()

        # Subscribe to EventBus
        asyncio.create_task(self._attach_listeners())

    async def _attach_listeners(self) -> None:
        await self.event_bus.subscribe(self.handle_event)

    async def handle_event(self, event: Event) -> None:
        """Process incoming events through Layer A rules and Layer B reasoning."""
        async with self._lock:
            self._recent_events.append(event)
            if len(self._recent_events) > 100:
                self._recent_events.pop(0)

            if event.type == EventType.TEST_RESULT:
                self._recent_tests.append(event)
                if len(self._recent_tests) > 20:
                    self._recent_tests.pop(0)

        # 1. Evaluate tool call safety (prior to/at execution)
        if event.type == EventType.TOOL_CALL:
            tool_name = event.payload.get("tool", "")
            args = event.payload.get("arguments", {})
            task = await self.task_manager.get_task(event.mission_id, event.task_id) if event.task_id else None

            anomaly = self.rules.evaluate_tool_call(tool_name, args, task=task)
            if anomaly:
                await self._trigger_anomaly_pipeline(event.mission_id, event.task_id, event.agent_id or "worker_01", anomaly)

        # 2. Evaluate test failures (loop detection)
        elif event.type == EventType.TEST_RESULT:
            task = await self.task_manager.get_task(event.mission_id, event.task_id) if event.task_id else None
            if task:
                anomaly = self.rules.evaluate_test_history(task, self._recent_tests)
                if anomaly:
                    await self._trigger_anomaly_pipeline(event.mission_id, event.task_id, event.agent_id or "worker_01", anomaly)

    async def _trigger_anomaly_pipeline(
        self,
        mission_id: str,
        task_id: Optional[str],
        agent_id: str,
        anomaly: Any
    ) -> None:
        """Trigger supervisor alert, Nemotron reasoning, and intervention."""
        # A. Emit Alert Event
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

        mission = await self.mission_manager.get_mission(mission_id)
        task = await self.task_manager.get_task(mission_id, task_id) if task_id else None

        # B. Call Layer B Nemotron Reasoning
        supervisory_ctx = self.reasoner.build_supervisory_context(
            mission_goal=mission.goal if mission else "Unknown",
            current_task_title=task.title if task else "General",
            agent_id=agent_id,
            recent_actions=[e.payload for e in self._recent_events[-6:]],
            error_signature=anomaly.evidence.get("error_signature"),
            constraints=[f"Max repeated failures: {self.policy.pause_after_repeated_failures}"],
            anomaly_type=anomaly.anomaly_type
        )

        decision = await self.reasoner.decide(supervisory_ctx)

        # C. Update State Machine
        self.state_machine.transition(decision.action, anomaly_type=anomaly.anomaly_type)

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

        # E. Enforce Decision Intervention
        if decision.action == SupervisorAction.PAUSE:
            await self.mission_manager.pause_mission(mission_id, reason=decision.reason)
        elif decision.action == SupervisorAction.DELEGATE:
            # Pause worker and notify operator/reviewer
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_id="supervisor",
                    type=EventType.AGENT_ACTION,
                    payload={
                        "action": "DELEGATE_TO_REVIEWER",
                        "target_agent": decision.target_agent or "reviewer_01",
                        "instruction": decision.recommended_strategy
                    }
                )
            )
