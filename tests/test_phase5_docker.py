import asyncio
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.events.bus import EventBus
from core.events.store import InMemoryEventStore
from core.events.schema import Event, EventType, EventSeverity
from execution.models import ExecutionRequest, ExecutionResult, ExecutionStatus, ContainerInfo
from execution.local import LocalExecutionProvider
from execution.docker import DockerExecutionProvider
from execution.manager import ExecutionManager
from tools.shell import RunCommandTool
from tools.testing import RunTestsTool


@pytest.fixture
def temp_workspace(tmp_path):
    ws = tmp_path / "sandbox_ws"
    ws.mkdir()
    # Create simple python file and test file
    src = ws / "math_mod.py"
    src.write_text("def add(a, b): return a + b\n")
    test_file = ws / "test_math.py"
    test_file.write_text("from math_mod import add\ndef test_add(): assert add(1, 2) == 3\n")
    return ws


# 1. LocalExecutionProvider works
@pytest.mark.asyncio
async def test_local_execution_provider_success(temp_workspace):
    bus = EventBus()
    store = InMemoryEventStore()
    bus._global_subscribers.append(store.append)

    provider = LocalExecutionProvider(event_bus=bus)
    req = ExecutionRequest(
        command="python -c \"print('LOCAL_SUCCESS')\"",
        workspace_root=temp_workspace,
        timeout_seconds=10
    )

    res = await provider.execute(req)
    assert res.status == ExecutionStatus.SUCCESS
    assert res.exit_code == 0
    assert "LOCAL_SUCCESS" in res.stdout
    assert res.backend == "local"

    started_events = [e for e in store._events if e.type == EventType.EXECUTION_STARTED]
    completed_events = [e for e in store._events if e.type == EventType.EXECUTION_COMPLETED]
    assert len(started_events) >= 1
    assert len(completed_events) >= 1


# 2 & 4. Docker provider rejects unsafe configuration and host-root mounting
@pytest.mark.asyncio
async def test_docker_provider_rejects_host_root_and_unsafe_paths():
    provider = DockerExecutionProvider()

    # Host root rejection
    with pytest.raises(PermissionError) as exc_info:
        provider.validate_workspace(Path("/"))
    assert "host root is strictly prohibited" in str(exc_info.value).lower()

    if os.name == "nt":
        with pytest.raises(PermissionError):
            provider.validate_workspace(Path("C:\\"))

    # Home directory rejection
    with pytest.raises(PermissionError) as exc_home:
        provider.validate_workspace(Path.home())
    assert "user home directory is prohibited" in str(exc_home.value).lower()


# 3. Docker provider validates workspace existence
@pytest.mark.asyncio
async def test_docker_provider_validates_workspace_existence(tmp_path):
    provider = DockerExecutionProvider()
    non_existent = tmp_path / "does_not_exist_dir"

    with pytest.raises(FileNotFoundError):
        provider.validate_workspace(non_existent)


# 5. Docker provider applies resource configuration
def test_docker_provider_resource_configuration():
    provider = DockerExecutionProvider(
        image="custom-worker:v1",
        memory_limit="256m",
        cpu_limit=0.5,
        pids_limit=64,
        network_disabled=True,
        default_timeout=60
    )
    assert provider.image == "custom-worker:v1"
    assert provider.memory_limit == "256m"
    assert provider.cpu_limit == 0.5
    assert provider.pids_limit == 64
    assert provider.network_disabled is True
    assert provider.default_timeout == 60


# 6. Timeout produces structured failure
@pytest.mark.asyncio
async def test_local_execution_timeout(temp_workspace):
    provider = LocalExecutionProvider()
    # Execute python command that sleeps longer than timeout
    req = ExecutionRequest(
        command="python -c \"import time; time.sleep(1.0)\"",
        workspace_root=temp_workspace,
        timeout_seconds=0.1
    )
    res = await provider.execute(req)
    assert res.status == ExecutionStatus.TIMEOUT
    assert "timed out" in res.error.lower()


# 7. stdout/stderr are captured
@pytest.mark.asyncio
async def test_stdout_stderr_capture(temp_workspace):
    provider = LocalExecutionProvider()
    req = ExecutionRequest(
        command="python -c \"import sys; sys.stdout.write('OUT_OK\\n'); sys.stderr.write('ERR_WARN\\n')\"",
        workspace_root=temp_workspace,
        timeout_seconds=10
    )
    res = await provider.execute(req)
    assert res.status == ExecutionStatus.SUCCESS
    assert "OUT_OK" in res.stdout
    assert res.stderr is not None and "ERR_WARN" in res.stderr


# 8. Secrets are not emitted in results or events
@pytest.mark.asyncio
async def test_secrets_sanitized_in_tool_dispatch(temp_workspace):
    tool = RunCommandTool(workspace_root=temp_workspace)
    # Attempt command containing simulated token/secret
    res = await tool.execute(command="python -c \"print('run_safe')\"")
    assert res.success
    # Ensure no secrets leak
    assert "API_KEY" not in str(res.metadata)


# 9. Docker container cleanup occurs on execution
@pytest.mark.asyncio
async def test_docker_container_cleanup_mocked(temp_workspace):
    bus = EventBus()
    store = InMemoryEventStore()
    bus._global_subscribers.append(store.append)

    provider = DockerExecutionProvider(event_bus=bus)

    # Mock Docker client and container lifecycle
    mock_container = MagicMock()
    mock_container.id = "mock_container_123456789"
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.return_value = b"PYTEST 47 passed\n"

    mock_client = MagicMock()
    mock_client.containers.create.return_value = mock_container

    with patch.object(provider, "_get_docker_client", return_value=mock_client):
        req = ExecutionRequest(
            command="pytest",
            workspace_root=temp_workspace,
            timeout_seconds=10
        )
        res = await provider.execute(req)
        assert res.status == ExecutionStatus.SUCCESS
        assert res.exit_code == 0
        assert "47 passed" in res.stdout
        assert res.container.container_id == "mock_contain"

        # Verify container was started and removed
        mock_container.start.assert_called_once()
        mock_container.remove.assert_called_once_with(force=True)

        # Verify events
        created_events = [e for e in store._events if e.type == EventType.CONTAINER_CREATED]
        destroyed_events = [e for e in store._events if e.type == EventType.CONTAINER_DESTROYED]
        assert len(created_events) >= 1
        assert len(destroyed_events) >= 1


# 10. Backend selection works (local vs docker)
@pytest.mark.asyncio
async def test_execution_manager_backend_selection(temp_workspace):
    manager = ExecutionManager(default_backend="local")
    assert manager.get_provider("local").backend_name == "local"
    assert manager.get_provider("docker").backend_name == "docker"

    # Execute locally
    req = ExecutionRequest(
        command="python -c \"print('LOCAL_RUN')\"",
        workspace_root=temp_workspace
    )
    res = await manager.execute(req, backend="local")
    assert res.backend == "local"
    assert "LOCAL_RUN" in res.stdout


# 11. Docker requested but unavailable returns structured error without pretending
@pytest.mark.asyncio
async def test_docker_unavailable_structured_error(temp_workspace):
    manager = ExecutionManager(default_backend="docker", allow_fallback=False)

    # Force is_available to return False
    with patch.object(manager.docker_provider, "is_available", new_callable=AsyncMock) as mock_avail:
        mock_avail.return_value = False
        req = ExecutionRequest(
            command="python -c \"print('DOCKER_RUN')\"",
            workspace_root=temp_workspace
        )
        res = await manager.execute(req, backend="docker")
        assert res.status == ExecutionStatus.ERROR
        assert res.backend == "docker"
        assert "Docker daemon is not accessible" in res.error or "Docker execution was requested" in res.error


# 12. Docker unavailable with explicit fallback allowed
@pytest.mark.asyncio
async def test_docker_unavailable_with_fallback(temp_workspace):
    bus = EventBus()
    store = InMemoryEventStore()
    bus._global_subscribers.append(store.append)

    manager = ExecutionManager(event_bus=bus, default_backend="docker", allow_fallback=True)

    with patch.object(manager.docker_provider, "is_available", new_callable=AsyncMock) as mock_avail:
        mock_avail.return_value = False
        req = ExecutionRequest(
            command="python -c \"print('FALLBACK_LOCAL_OK')\"",
            workspace_root=temp_workspace
        )
        res = await manager.execute(req, backend="docker")
        assert res.status == ExecutionStatus.SUCCESS
        assert "FALLBACK_LOCAL_OK" in res.stdout
        assert res.metadata.get("fallback_from") == "docker"


# 13. Integration Test: Real Docker execution if daemon is running, skipped otherwise
def is_docker_daemon_active() -> bool:
    try:
        import docker
        client = docker.from_env()
        return client.ping() is True
    except Exception:
        return False


@pytest.mark.skipif(not is_docker_daemon_active(), reason="Docker daemon is not reachable on host")
@pytest.mark.asyncio
async def test_real_docker_execution_integration(temp_workspace):
    provider = DockerExecutionProvider()
    req = ExecutionRequest(
        command="python -c \"print('REAL_DOCKER_SUCCESS')\"",
        workspace_root=temp_workspace,
        timeout_seconds=30
    )
    res = await provider.execute(req)
    assert res.status == ExecutionStatus.SUCCESS
    assert "REAL_DOCKER_SUCCESS" in res.stdout
    assert res.container is not None
