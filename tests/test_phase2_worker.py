import asyncio
import os
import pytest
from pathlib import Path
from agents.worker.agent import WorkerAgent
from agents.worker.models import WorkerState, WorkerAction
from core.events.bus import EventBus
from core.events.schema import Event, EventType
from core.state.models import AgentContextPackage
from tools import get_default_tools
from tools.base import BaseTool


@pytest.fixture
def temp_workspace(tmp_path):
    ws = tmp_path / "sandbox"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src" / "sample.py").write_text("print('hello')", encoding="utf-8")
    return ws


def test_workspace_jail_rejection(temp_workspace):
    tools = get_default_tools(temp_workspace)
    read_tool = tools["read_file"]

    # Traversal rejection
    with pytest.raises(PermissionError) as exc_info:
        read_tool.resolve_path("../outside.py")
    assert "traversal token" in str(exc_info.value).lower()

    # Absolute path outside rejection
    with pytest.raises(PermissionError) as exc_info2:
        read_tool.resolve_path("C:/Windows/System32/drivers/etc/hosts")
    assert "outside workspace sandbox jail" in str(exc_info2.value).lower()


def test_dangerous_command_rejection(temp_workspace):
    tools = get_default_tools(temp_workspace)
    run_cmd_tool = tools["run_command"]

    with pytest.raises(PermissionError) as exc_info:
        run_cmd_tool.validate_command("rm -rf ./build")
    assert "dangerous command pattern" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_worker_tool_dispatch_and_events(temp_workspace):
    bus = EventBus()
    events = []
    await bus.subscribe(lambda e: events.append(e))

    tools = get_default_tools(temp_workspace)
    worker = WorkerAgent(agent_id="worker_test", event_bus=bus, tools=tools)

    res = await worker.call_tool("read_file", {"path": "src/sample.py"}, mission_id="msn_1", task_id="task_1")
    assert res.success is True
    assert "hello" in res.output

    # Check emitted events
    event_types = [e.type for e in events]
    assert EventType.TOOL_CALLED in event_types
    assert EventType.TOOL_COMPLETED in event_types


@pytest.mark.asyncio
async def test_worker_pause_and_resume():
    bus = EventBus()
    worker = WorkerAgent(agent_id="worker_pause_test", event_bus=bus)

    assert worker.state == WorkerState.IDLE
    worker.pause()
    assert worker.state == WorkerState.PAUSED

    worker.resume()
    assert worker.state == WorkerState.RUNNING


@pytest.mark.asyncio
async def test_worker_autonomous_loop(temp_workspace):
    bus = EventBus()
    tools = get_default_tools(temp_workspace)

    # Custom decision strategy: read file, then finish
    def custom_strategy(ctx, history):
        if not history:
            return WorkerAction(action="read_file", arguments={"path": "src/sample.py"}, thought_summary="Checking file")
        return WorkerAction(action="finish_task", arguments={}, thought_summary="Completed inspection")

    worker = WorkerAgent(agent_id="worker_loop_test", event_bus=bus, tools=tools, decision_callback=custom_strategy)

    ctx = AgentContextPackage(
        mission_id="msn_loop",
        objective="Inspect sample",
        task={"id": "task_loop", "title": "Inspect sample"}
    )

    result = await worker.run(ctx)
    assert result["status"] == "completed"
    assert worker.state == WorkerState.COMPLETED
