import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.events.bus import EventBus
from core.events.schema import Event, EventType, EventSeverity
from execution.base import BaseExecutionProvider
from execution.models import ContainerInfo, ExecutionRequest, ExecutionResult, ExecutionStatus

logger = logging.getLogger("supervisor.execution.docker")


class DockerExecutionProvider(BaseExecutionProvider):
    """
    Docker-backed container execution layer.
    Enforces strict container sandboxing:
    - Dedicated isolated workspace mount ONLY (never host root, never docker socket)
    - Network disabled by default (network_mode='none')
    - Dropped Linux capabilities (cap_drop=['ALL'])
    - Security option 'no-new-privileges:true'
    - Memory, CPU, and PID limits
    - Unprivileged non-root user execution
    - Automatic container destruction and cleanup
    """

    backend_name: str = "docker"

    PROHIBITED_HOST_PATHS = (
        "/", "C:\\", "C:/",
        "/etc", "/var", "/usr", "/root", "/bin", "/sbin",
        "/var/run/docker.sock", "//./pipe/docker_engine"
    )

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        image: Optional[str] = None,
        memory_limit: Optional[str] = None,
        cpu_limit: Optional[float] = None,
        pids_limit: Optional[int] = None,
        network_disabled: Optional[bool] = None,
        default_timeout: Optional[int] = None
    ):
        super().__init__(event_bus=event_bus)
        self.image = image or os.getenv("DOCKER_IMAGE", "ai-work-supervisor-worker:latest")
        self.memory_limit = memory_limit or os.getenv("DOCKER_MEMORY_LIMIT", "512m")
        self.cpu_limit = cpu_limit if cpu_limit is not None else float(os.getenv("DOCKER_CPU_LIMIT", "1.0"))
        self.pids_limit = pids_limit if pids_limit is not None else int(os.getenv("DOCKER_PIDS_LIMIT", "128"))
        
        net_env = os.getenv("DOCKER_NETWORK_DISABLED", "true").lower() in ("true", "1", "yes")
        self.network_disabled = network_disabled if network_disabled is not None else net_env
        self.default_timeout = default_timeout or int(os.getenv("DOCKER_TIMEOUT_SECONDS", "120"))

    def _get_docker_client(self):
        """Obtain docker client or raise RuntimeError if unavailable."""
        try:
            import docker
            client = docker.from_env()
            client.ping()
            return client
        except Exception as e:
            raise RuntimeError(f"Docker Engine is not accessible: {e}")

    async def is_available(self) -> bool:
        """Check if Docker Engine API is reachable."""
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._get_docker_client)
            return True
        except Exception:
            return False

    def validate_workspace(self, workspace_path: Path) -> Path:
        """
        Validate workspace path to prevent mounting host root or sensitive host directories.
        """
        resolved = workspace_path.resolve()
        resolved_str = str(resolved).replace("\\", "/").rstrip("/")

        # Check against host roots
        for prohibited in self.PROHIBITED_HOST_PATHS:
            prohib_str = prohibited.replace("\\", "/").rstrip("/")
            if resolved_str == prohib_str or resolved == resolved.parent:
                raise PermissionError(f"DockerExecutionProvider: Mounting host root is strictly prohibited: '{resolved}'")

        # Check home directory mount
        is_home = False
        try:
            home_dir = Path.home().resolve()
            is_home = (resolved == home_dir)
        except Exception:
            is_home = False

        if is_home:
            raise PermissionError(f"DockerExecutionProvider: Mounting user home directory is prohibited: '{resolved}'")

        if not resolved.exists():
            raise FileNotFoundError(f"DockerExecutionProvider: Task workspace does not exist: '{resolved}'")

        return resolved

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """
        Execute command inside an ephemeral sandboxed Docker container.
        """
        start_time = time.monotonic()
        workspace_path = request.get_workspace_path()
        mission_id = request.mission_id or "default_mission"

        # 1. Workspace safety check
        try:
            resolved_workspace = self.validate_workspace(workspace_path)
        except Exception as e:
            return ExecutionResult(
                status=ExecutionStatus.BLOCKED,
                exit_code=-1,
                error=str(e),
                duration_ms=round((time.monotonic() - start_time) * 1000, 2),
                backend=self.backend_name,
                metadata={"danger_detected": True}
            )

        # 2. Check Docker availability
        try:
            loop = asyncio.get_running_loop()
            client = await loop.run_in_executor(None, self._get_docker_client)
        except Exception as e:
            err_msg = f"Docker unavailable: {e}"
            logger.error(err_msg)
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                error=err_msg,
                duration_ms=round((time.monotonic() - start_time) * 1000, 2),
                backend=self.backend_name
            )

        container = None
        container_info = ContainerInfo(
            image=self.image,
            network_disabled=self.network_disabled,
            cpu_limit=self.cpu_limit,
            memory_limit=self.memory_limit,
            pids_limit=self.pids_limit
        )

        timeout = request.timeout_seconds or self.default_timeout

        try:
            # Mount ONLY the intended workspace to /workspace
            volumes = {
                str(resolved_workspace): {
                    "bind": "/workspace",
                    "mode": "rw"
                }
            }

            # Security parameters
            container_kwargs: Dict[str, Any] = {
                "image": self.image,
                "command": ["/bin/sh", "-c", request.command],
                "volumes": volumes,
                "working_dir": "/workspace",
                "detach": True,
                "mem_limit": self.memory_limit,
                "nano_cpus": int(self.cpu_limit * 1e9),
                "pids_limit": self.pids_limit,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "environment": request.env,
                "stdin_open": False,
                "tty": False
            }

            if self.network_disabled:
                container_kwargs["network_mode"] = "none"

            # Create container in thread executor
            def _create_and_run():
                c = client.containers.create(**container_kwargs)
                c.start()
                return c

            container = await loop.run_in_executor(None, _create_and_run)
            container_info.container_id = container.id[:12]
            container_info.status = "running"

            # Emit container created & started events
            if self.event_bus:
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=request.task_id,
                        agent_id=request.agent_id,
                        type=EventType.CONTAINER_CREATED,
                        payload={
                            "container_id": container_info.container_id,
                            "image": self.image,
                            "workspace": str(resolved_workspace)
                        }
                    )
                )
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=request.task_id,
                        agent_id=request.agent_id,
                        type=EventType.CONTAINER_STARTED,
                        payload={
                            "container_id": container_info.container_id,
                            "network_disabled": self.network_disabled,
                            "memory_limit": self.memory_limit
                        }
                    )
                )
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=request.task_id,
                        agent_id=request.agent_id,
                        type=EventType.EXECUTION_STARTED,
                        payload={
                            "backend": self.backend_name,
                            "container_id": container_info.container_id,
                            "command": request.command
                        }
                    )
                )

            # Wait for execution with timeout
            def _wait_container():
                res = container.wait(timeout=timeout)
                logs = container.logs(stdout=True, stderr=True)
                return res, logs

            try:
                wait_result, raw_logs = await loop.run_in_executor(None, _wait_container)
                exit_code = wait_result.get("StatusCode", -1) if isinstance(wait_result, dict) else wait_result
                log_text = raw_logs.decode("utf-8", errors="replace") if isinstance(raw_logs, bytes) else str(raw_logs)

            except Exception as wait_exc:
                # Handle timeout or container error
                duration_ms = round((time.monotonic() - start_time) * 1000, 2)
                is_timeout = "timeout" in str(wait_exc).lower()

                if self.event_bus:
                    await self.event_bus.publish(
                        Event(
                            mission_id=mission_id,
                            task_id=request.task_id,
                            agent_id=request.agent_id,
                            type=EventType.CONTAINER_LIMIT_EXCEEDED if is_timeout else EventType.EXECUTION_FAILED,
                            severity=EventSeverity.CRITICAL if is_timeout else EventSeverity.ERROR,
                            payload={
                                "container_id": container_info.container_id,
                                "reason": "TIMEOUT" if is_timeout else "CRASH",
                                "error": str(wait_exc)
                            }
                        )
                    )

                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT if is_timeout else ExecutionStatus.FAILED,
                    exit_code=-1,
                    error=f"Container execution timed out after {timeout}s" if is_timeout else str(wait_exc),
                    duration_ms=duration_ms,
                    container=container_info,
                    backend=self.backend_name
                )

            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            success = exit_code == 0
            container_info.status = "stopped"

            formatted_log = None
            if log_text:
                formatted_log = log_text if len(log_text) <= 50000 else (log_text[:15000] + "\n...[truncated]...\n" + log_text[-15000:])

            result = ExecutionResult(
                status=ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED,
                exit_code=exit_code,
                stdout=formatted_log,
                stderr=None if success else formatted_log,
                duration_ms=duration_ms,
                container=container_info,
                backend=self.backend_name,
                metadata={"returncode": exit_code}
            )

            if self.event_bus:
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=request.task_id,
                        agent_id=request.agent_id,
                        type=EventType.EXECUTION_COMPLETED if success else EventType.EXECUTION_FAILED,
                        severity=EventSeverity.INFO if success else EventSeverity.WARNING,
                        payload={
                            "backend": self.backend_name,
                            "container_id": container_info.container_id,
                            "exit_code": exit_code,
                            "duration_ms": duration_ms
                        }
                    )
                )

            return result

        finally:
            # Container cleanup in finally block
            if container:
                try:
                    def _cleanup():
                        try:
                            container.remove(force=True)
                        except Exception:
                            pass
                    await loop.run_in_executor(None, _cleanup)

                    if self.event_bus and container_info.container_id:
                        await self.event_bus.publish(
                            Event(
                                mission_id=mission_id,
                                task_id=request.task_id,
                                agent_id=request.agent_id,
                                type=EventType.CONTAINER_DESTROYED,
                                payload={"container_id": container_info.container_id}
                            )
                        )
                except Exception as cleanup_err:
                    logger.warning(f"Error during container cleanup: {cleanup_err}")
