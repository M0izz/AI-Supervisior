import logging
import os
from typing import Dict, Optional

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from execution.base import BaseExecutionProvider
from execution.docker import DockerExecutionProvider
from execution.local import LocalExecutionProvider
from execution.models import ExecutionRequest, ExecutionResult, ExecutionStatus

logger = logging.getLogger("supervisor.execution.manager")


class ExecutionManager:
    """
    Unified Execution Manager.
    Routes agent tool and shell requests transparently to either
    LocalExecutionProvider or DockerExecutionProvider based on configuration.
    Handles fallback behavior and publishes supervisory telemetry.
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        default_backend: Optional[str] = None,
        allow_fallback: Optional[bool] = None
    ):
        self.event_bus = event_bus
        self.default_backend = default_backend or os.getenv("EXECUTION_BACKEND", "local").lower()
        
        fallback_env = os.getenv("EXECUTION_ALLOW_FALLBACK", "false").lower() in ("true", "1", "yes")
        self.allow_fallback = allow_fallback if allow_fallback is not None else fallback_env

        self.local_provider = LocalExecutionProvider(event_bus=self.event_bus)
        self.docker_provider = DockerExecutionProvider(event_bus=self.event_bus)

    def get_provider(self, backend: Optional[str] = None) -> BaseExecutionProvider:
        b = (backend or self.default_backend).lower()
        if b == "docker":
            return self.docker_provider
        return self.local_provider

    async def execute(
        self,
        request: ExecutionRequest,
        backend: Optional[str] = None
    ) -> ExecutionResult:
        selected_backend = (backend or self.default_backend).lower()

        if selected_backend == "docker":
            docker_ok = await self.docker_provider.is_available()
            if docker_ok:
                return await self.docker_provider.execute(request)

            mission_id = request.mission_id or "default_mission"

            # Docker is requested but unavailable
            if not self.allow_fallback:
                err_msg = (
                    "Docker execution was requested (EXECUTION_BACKEND=docker), "
                    "but the Docker daemon is not accessible on this system."
                )
                logger.error(err_msg)
                if self.event_bus:
                    await self.event_bus.publish(
                        Event(
                            mission_id=mission_id,
                            task_id=request.task_id,
                            agent_id=request.agent_id,
                            type=EventType.EXECUTION_FAILED,
                            severity=EventSeverity.ERROR,
                            payload={"backend": "docker", "error": err_msg}
                        )
                    )
                return ExecutionResult(
                    status=ExecutionStatus.ERROR,
                    exit_code=-1,
                    error=err_msg,
                    backend="docker"
                )

            # Fallback to local execution
            logger.warning("Docker is unavailable; explicitly falling back to LocalExecutionProvider.")
            if self.event_bus:
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=request.task_id,
                        agent_id=request.agent_id,
                        type=EventType.EXECUTION_STARTED,
                        severity=EventSeverity.WARNING,
                        payload={
                            "requested_backend": "docker",
                            "fallback_backend": "local",
                            "reason": "Docker daemon unavailable"
                        }
                    )
                )

            result = await self.local_provider.execute(request)
            result.metadata["fallback_from"] = "docker"
            return result

        # Default local execution
        return await self.local_provider.execute(request)
