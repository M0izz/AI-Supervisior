import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from core.events.bus import EventBus
from core.events.schema import (
    Event,
    EventType,
    EventSeverity,
    ToolCallPayload,
    ToolResultPayload,
)
from core.state.models import AgentContextPackage
from tools.base import BaseTool, ToolResult

logger = logging.getLogger("supervisor.agents")


class BaseAgent(ABC):
    """Abstract base agent with tool dispatching and event emission."""

    def __init__(self, agent_id: str, role: str, event_bus: EventBus, tools: Optional[Dict[str, BaseTool]] = None):
        self.agent_id = agent_id
        self.role = role
        self.event_bus = event_bus
        self.tools = tools or {}

    async def emit_action(self, mission_id: str, task_id: Optional[str], description: str, metadata: Optional[Dict[str, Any]] = None):
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=self.agent_id,
                type=EventType.AGENT_ACTION,
                payload={
                    "role": self.role,
                    "description": description,
                    **(metadata or {})
                }
            )
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        mission_id: str,
        task_id: Optional[str] = None
    ) -> ToolResult:
        """Execute a tool with duration tracking, sanitization, and comprehensive event emission."""
        import time
        target = arguments.get("path") or arguments.get("command") or arguments.get("test_command") or "workspace"
        sanitized_args = BaseTool.sanitize_arguments(arguments)

        # 1. Emit TOOL_CALL & TOOL_CALLED event
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=self.agent_id,
                type=EventType.TOOL_CALLED,
                payload={
                    "agent_id": self.agent_id,
                    "mission_id": mission_id,
                    "task_id": task_id,
                    "tool": tool_name,
                    "arguments": sanitized_args,
                    "target": str(target)
                }
            )
        )

        tool = self.tools.get(tool_name)
        if not tool:
            err_msg = f"Tool '{tool_name}' not available to agent {self.agent_id}."
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_id=self.agent_id,
                    type=EventType.TOOL_FAILED,
                    severity=EventSeverity.ERROR,
                    payload={"tool": tool_name, "error": err_msg}
                )
            )
            return ToolResult(success=False, error=err_msg)

        # 2. Execute tool with duration timing
        start_time = time.monotonic()
        try:
            result = await tool.execute(**arguments)
        except Exception as e:
            result = ToolResult(success=False, error=str(e))
        duration_ms = round((time.monotonic() - start_time) * 1000, 2)

        # 3. Check for danger detection
        if result.metadata.get("danger_detected"):
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_id=self.agent_id,
                    type=EventType.DANGER_DETECTED,
                    severity=EventSeverity.CRITICAL,
                    payload={
                        "tool": tool_name,
                        "arguments": sanitized_args,
                        "error": result.error,
                        "target": str(target)
                    }
                )
            )

        # 4. Emit TEST_RESULT or TOOL_COMPLETED / TOOL_FAILED
        if tool_name == "run_tests":
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_id=self.agent_id,
                    type=EventType.TEST_RESULT,
                    severity=EventSeverity.INFO if result.success else EventSeverity.WARNING,
                    payload={
                        "command": arguments.get("test_command", "tests"),
                        "passed": result.metadata.get("passed", 0),
                        "failed": result.metadata.get("failed", 0),
                        "error_signature": result.metadata.get("error_signature"),
                        "duration_ms": duration_ms,
                        "output": result.output[:500] if result.output else None,
                        "error": result.error[:500] if result.error else None,
                    }
                )
            )
        else:
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_id=self.agent_id,
                    type=EventType.TOOL_COMPLETED if result.success else EventType.TOOL_FAILED,
                    severity=EventSeverity.INFO if result.success else EventSeverity.WARNING,
                    payload={
                        "tool": tool_name,
                        "success": result.success,
                        "duration_ms": duration_ms,
                        "arguments": sanitized_args,
                        "output": result.output[:500] if result.output else None,
                        "error": result.error[:500] if result.error else None,
                        "target": str(target)
                    }
                )
            )

        return result

    @abstractmethod
    async def run(self, context_package: AgentContextPackage) -> Dict[str, Any]:
        """Run execution cycle with context package."""
        pass
