import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity

logger = logging.getLogger("supervisor.telemetry")


class ExecutionTelemetry(BaseModel):
    current_task: Optional[str] = None
    completed_tasks: int = 0
    failed_tasks: int = 0
    iteration_count: int = 0
    tool_calls: int = 0
    runtime_seconds: float = 0.0
    start_time: Optional[float] = None


class ReliabilityTelemetry(BaseModel):
    failure_count: int = 0
    repeated_failures: int = 0
    interventions: int = 0
    recovery_attempts: int = 0
    verification_failures: int = 0


class CostTelemetry(BaseModel):
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class RiskTelemetry(BaseModel):
    dangerous_actions: int = 0
    scope_violations: int = 0
    approval_requests: int = 0
    blocked_actions: int = 0


class MissionTelemetry(BaseModel):
    mission_id: str
    execution: ExecutionTelemetry = Field(default_factory=ExecutionTelemetry)
    reliability: ReliabilityTelemetry = Field(default_factory=ReliabilityTelemetry)
    cost: CostTelemetry = Field(default_factory=CostTelemetry)
    risk: RiskTelemetry = Field(default_factory=RiskTelemetry)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GlobalTelemetryOverview(BaseModel):
    active_missions: int = 0
    total_agents: int = 0
    total_interventions: int = 0
    system_health: str = "OK"  # OK, WARNING, CRITICAL
    total_tool_calls: int = 0
    total_failures: int = 0
    pending_approvals: int = 0
    total_cost_usd: float = 0.0


class TelemetryTracker:
    """
    Subscribes to EventBus events to maintain live metrics on Execution,
    Reliability, Cost, and Risk per mission and system-wide.
    """

    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._missions: Dict[str, MissionTelemetry] = {}
        self._pending_approvals_count: int = 0
        self._lock = asyncio.Lock()

        if self._event_bus:
            self._event_bus.subscribe_sync(self.handle_event)

    def _get_or_create(self, mission_id: str) -> MissionTelemetry:
        if mission_id not in self._missions:
            self._missions[mission_id] = MissionTelemetry(mission_id=mission_id)
        return self._missions[mission_id]

    async def get_mission_telemetry(self, mission_id: str) -> MissionTelemetry:
        async with self._lock:
            m = self._get_or_create(mission_id)
            if m.execution.start_time:
                m.execution.runtime_seconds = round(time.monotonic() - m.execution.start_time, 2)
            m.updated_at = datetime.now(timezone.utc)
            return m

    async def get_global_overview(self, active_missions_count: int = 0, total_agents_count: int = 0) -> GlobalTelemetryOverview:
        async with self._lock:
            total_interventions = sum(m.reliability.interventions for m in self._missions.values())
            total_tools = sum(m.execution.tool_calls for m in self._missions.values())
            total_fails = sum(m.reliability.failure_count for m in self._missions.values())
            total_cost = sum(m.cost.estimated_cost_usd for m in self._missions.values())
            total_risks = sum(m.risk.dangerous_actions + m.risk.scope_violations for m in self._missions.values())

            health = "OK"
            if self._pending_approvals_count > 0 or total_risks > 2:
                health = "WARNING"
            if any(m.risk.dangerous_actions > 0 for m in self._missions.values()):
                health = "CRITICAL" if total_fails > 5 else "WARNING"

            return GlobalTelemetryOverview(
                active_missions=active_missions_count,
                total_agents=total_agents_count,
                total_interventions=total_interventions,
                system_health=health,
                total_tool_calls=total_tools,
                total_failures=total_fails,
                pending_approvals=self._pending_approvals_count,
                total_cost_usd=round(total_cost, 4)
            )

    async def record_model_usage(
        self,
        mission_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0
    ) -> None:
        async with self._lock:
            m = self._get_or_create(mission_id)
            m.cost.model_calls += 1
            m.cost.input_tokens += input_tokens
            m.cost.output_tokens += output_tokens
            m.cost.estimated_cost_usd += cost_usd

    async def handle_event(self, event: Event) -> None:
        """Process incoming events to update execution, reliability, cost, and risk metrics."""
        mission_id = event.mission_id or "default"

        async with self._lock:
            m = self._get_or_create(mission_id)
            if not m.execution.start_time:
                m.execution.start_time = time.monotonic()
            m.execution.runtime_seconds = round(time.monotonic() - m.execution.start_time, 2)

            if event.task_id:
                m.execution.current_task = event.task_id

            # 1. Execution
            if event.type in (EventType.TOOL_CALL, EventType.TOOL_CALLED):
                m.execution.tool_calls += 1
            elif event.type == EventType.TASK_PROGRESS:
                m.execution.iteration_count += 1
            elif event.type == EventType.TASK_COMPLETED:
                m.execution.completed_tasks += 1
            elif event.type == EventType.TASK_FAILED:
                m.execution.failed_tasks += 1
                m.reliability.failure_count += 1

            # 2. Reliability & Failures
            if event.type in (EventType.TEST_FAILED, EventType.TOOL_FAILED):
                m.reliability.failure_count += 1
            elif event.type == EventType.SUPERVISOR_ALERT:
                anomaly_type = event.payload.get("anomaly_type") or event.payload.get("rule_name", "")
                if "LOOP" in anomaly_type or "REPEATED" in anomaly_type:
                    m.reliability.repeated_failures += 1
            elif event.type == EventType.SUPERVISOR_INTERVENTION:
                m.reliability.interventions += 1
            elif event.type == EventType.RECOVERY_STARTED:
                m.reliability.recovery_attempts += 1
            elif event.type in (EventType.VERIFICATION_FAILED, EventType.CI_BUILD_FAILED):
                m.reliability.verification_failures += 1
                m.reliability.failure_count += 1

            # 3. Risk & Danger
            if event.type == EventType.DANGER_DETECTED:
                m.risk.dangerous_actions += 1
            elif event.type == EventType.APPROVAL_REQUESTED:
                m.risk.approval_requests += 1
                self._pending_approvals_count += 1
            elif event.type == EventType.APPROVAL_RESOLVED:
                if self._pending_approvals_count > 0:
                    self._pending_approvals_count -= 1
                if event.payload.get("action") == "DENIED":
                    m.risk.blocked_actions += 1
            elif event.type == EventType.SUPERVISOR_ALERT and "SCOPE" in (event.payload.get("anomaly_type") or ""):
                m.risk.scope_violations += 1
            elif event.type == EventType.FILE_CONTENTION_DETECTED:
                m.risk.blocked_actions += 1

            # 4. Model usage
            if event.type == EventType.SUPERVISOR_REASONING_COMPLETED:
                m.cost.model_calls += 1
                # Standard Nemotron reasoning approximation
                m.cost.input_tokens += 1200
                m.cost.output_tokens += 150
                m.cost.estimated_cost_usd += round((1200 * 0.0000007) + (150 * 0.000002), 6)
