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
        """Execute a tool and emit TOOL_CALL and TOOL_RESULT events."""
        target = arguments.get("path") or arguments.get("command") or arguments.get("test_command") or "workspace"

        # 1. Emit TOOL_CALL event
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=self.agent_id,
                type=EventType.TOOL_CALL,
                payload=ToolCallPayload(
                    tool=tool_name,
                    arguments=arguments,
                    target=str(target)
                ).model_dump()
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
                    type=EventType.TOOL_ERROR,
                    severity=EventSeverity.ERROR,
                    payload={"tool": tool_name, "error": err_msg}
                )
            )
            return ToolResult(success=False, error=err_msg)

        # 2. Execute tool
        try:
            result = await tool.execute(**arguments)
        except Exception as e:
            result = ToolResult(success=False, error=str(e))

        # 3. Emit TOOL_RESULT or TEST_RESULT event
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
                    type=EventType.TOOL_RESULT,
                    severity=EventSeverity.INFO if result.success else EventSeverity.WARNING,
                    payload=ToolResultPayload(
                        tool=tool_name,
                        success=result.success,
                        output=result.output[:500] if result.output else None,
                        error=result.error[:500] if result.error else None,
                        target=str(target)
                    ).model_dump()
                )
            )

        return result

    @abstractmethod
    async def run(self, context_package: AgentContextPackage) -> Dict[str, Any]:
        """Run execution cycle with context package."""
        pass
