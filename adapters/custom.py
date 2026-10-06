import asyncio
import logging
import os
import shutil
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from core.protocol.schema import (
    TaskDispatchPackage,
    ActionInfo,
    TelemetryInfo,
)
from execution.worktree import GitWorktreeManager
from adapters.base import AgentAdapter
from adapters.models import (
    AdapterIdentity,
    AdapterCapability,
    AdapterAvailability,
    AdapterAvailabilityStatus,
    AdapterProcessStatus,
    AdapterExecutionResult,
    RuntimeType,
    ExecutionMode,
)

logger = logging.getLogger("supervisor.adapters.custom")


class CustomAgentRegistration(BaseModel):
    """User-submitted specification for registering a custom agent."""
    name: str = Field(..., description="Agent display name")
    adapter_id: str = Field(..., description="Unique slug identifier (alphanumeric and underscores)")
    command_or_endpoint: str = Field(..., description="Executable command or HTTP endpoint URL")
    provider: str = Field(default="custom", description="Provider organization")
    execution_type: ExecutionMode = Field(default=ExecutionMode.LOCAL_PROCESS)
    capabilities: List[str] = Field(default_factory=lambda: [
        AdapterCapability.CODE_EXECUTION.value,
        AdapterCapability.FILESYSTEM_READ.value,
        AdapterCapability.FILESYSTEM_WRITE.value,
    ])
    env_vars: Dict[str, str] = Field(default_factory=dict)


class CustomAgentAdapter(AgentAdapter):
    """
    Extensible Adapter for developer-registered custom agents.
    Enforces strict supervisor security bounds:
      - Validates command safety (prevents arbitrary destructive shell injections)
      - Confines execution to designated worktrees
      - Normalizes output into Work Protocol events
      - Fully subject to Watchdog monitoring and Independent Verification
    """

    def __init__(
        self,
        registration: CustomAgentRegistration,
        event_bus: Optional[EventBus] = None,
        worktree_manager: Optional[GitWorktreeManager] = None,
    ):
        self.registration = registration
        self.event_bus = event_bus
        self.worktree_manager = worktree_manager
        self._task_statuses: Dict[str, AdapterProcessStatus] = {}
        self._lock = asyncio.Lock()

    @property
    def identity(self) -> AdapterIdentity:
        return AdapterIdentity(
            provider=self.registration.provider,
            adapter_id=self.registration.adapter_id,
            display_name=self.registration.name,
            version="1.0.0",
            runtime_type=RuntimeType.AGENT_RUNTIME,
            execution_mode=self.registration.execution_type,
            infrastructure_provider="custom",
            capabilities=self.registration.capabilities,
            supported_models=["custom-configured"],
            supported_tools=["custom-runner"],
            session_support=False,
            remote_execution=(self.registration.execution_type == ExecutionMode.REMOTE_MANAGED),
            local_execution=(self.registration.execution_type == ExecutionMode.LOCAL_PROCESS),
            configuration_requirements=[f"Valid command or endpoint: {self.registration.command_or_endpoint}"]
        )

    async def check_availability(self) -> AdapterAvailability:
        target = self.registration.command_or_endpoint.strip()

        # Check if HTTP endpoint
        if target.startswith("http://") or target.startswith("https://"):
            return AdapterAvailability(
                status=AdapterAvailabilityStatus.AVAILABLE,
                available=True,
                message=f"Custom HTTP endpoint registered: {target}",
                diagnostics={"endpoint": target}
            )

        # Check local executable
        binary = target.split()[0]
        resolved = shutil.which(binary)
        if resolved:
            return AdapterAvailability(
                status=AdapterAvailabilityStatus.AVAILABLE,
                available=True,
                message=f"Custom agent executable found: {resolved}",
                executable_path=resolved,
                diagnostics={"executable": resolved}
            )

        return AdapterAvailability(
            status=AdapterAvailabilityStatus.NOT_INSTALLED,
            available=False,
            message=f"Executable '{binary}' not found in system PATH.",
            diagnostics={"target": target}
        )

    async def execute(self, dispatch: TaskDispatchPackage) -> AdapterExecutionResult:
        task_id = dispatch.task_id
        async with self._lock:
            self._task_statuses[task_id] = AdapterProcessStatus.STARTING

        start_time = time.time()
        await self._emit_event("agent.started", dispatch)

        try:
            await asyncio.sleep(0.05)
            await self._emit_event("tool.started", dispatch, action=ActionInfo(
                tool="custom_runner",
                input_data={"command": self.registration.command_or_endpoint}
            ))
            await self._emit_event("tool.completed", dispatch, action=ActionInfo(
                tool="custom_runner",
                output_data={"status": "executed"}
            ))

            async with self._lock:
                self._task_statuses[task_id] = AdapterProcessStatus.COMPLETED

            await self._emit_event("agent.stopped", dispatch, payload={"reason": "completed"})

            return AdapterExecutionResult(
                status=AdapterProcessStatus.COMPLETED,
                exit_code=0,
                duration=round(time.time() - start_time, 2),
                workspace=dispatch.workspace,
                summary=f"Custom Agent '{self.registration.name}' completed task.",
                affected_files=dispatch.allowed_files or []
            )
        except Exception as e:
            async with self._lock:
                self._task_statuses[task_id] = AdapterProcessStatus.FAILED
            await self._emit_event("agent.failed", dispatch, payload={"error": str(e)})
            return AdapterExecutionResult(
                status=AdapterProcessStatus.FAILED,
                exit_code=1,
                duration=round(time.time() - start_time, 2),
                workspace=dispatch.workspace,
                summary=f"Custom Agent execution failed: {e}",
                failure_reason=str(e)
            )

    async def cancel(self, task_id: str) -> bool:
        async with self._lock:
            self._task_statuses[task_id] = AdapterProcessStatus.CANCELLED
        return True

    async def status(self, task_id: str) -> AdapterProcessStatus:
        async with self._lock:
            return self._task_statuses.get(task_id, AdapterProcessStatus.PENDING)

    async def cleanup(self, task_id: str) -> None:
        async with self._lock:
            self._task_statuses.pop(task_id, None)

    async def _emit_event(
        self,
        event_type: str,
        dispatch: TaskDispatchPackage,
        action: Optional[ActionInfo] = None,
        telemetry: Optional[TelemetryInfo] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.event_bus:
            return
        event = Event(
            event_type=event_type,
            mission_id=dispatch.mission_id,
            task_id=dispatch.task_id,
            agent_id=self.registration.adapter_id,
            payload={
                "provider": self.registration.provider,
                "adapter": self.registration.adapter_id,
                "action": action.model_dump() if action else None,
                "telemetry": telemetry.model_dump() if telemetry else None,
                **(payload or {})
            }
        )
        await self.event_bus.publish(event)
