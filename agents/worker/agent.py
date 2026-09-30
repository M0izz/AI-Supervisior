import asyncio
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional
from agents.base import BaseAgent
from agents.worker.models import WorkerAction, WorkerState
from core.events.bus import EventBus
from core.events.schema import Event, EventSeverity, EventType
from core.state.models import AgentContextPackage
from tools.base import BaseTool, ToolResult

logger = logging.getLogger("supervisor.worker")


class WorkerAgent(BaseAgent):
    """
    Autonomous Worker Agent.
    Operates inside the sandboxed workspace using registered tools,
    respecting supervisor pauses and utilizing recovery context.
    """

    def __init__(
        self,
        agent_id: str = "worker_01",
        event_bus: Optional[EventBus] = None,
        tools: Optional[Dict[str, BaseTool]] = None,
        max_iterations: int = 25,
        timeout_seconds: int = 60,
        decision_callback: Optional[Callable[[AgentContextPackage, List[Dict[str, Any]]], WorkerAction]] = None
    ):
        super().__init__(agent_id=agent_id, role="Worker", event_bus=event_bus or EventBus(), tools=tools)
        self.state: WorkerState = WorkerState.IDLE
        self.max_iterations = int(os.getenv("SUPERVISOR_MAX_ITERATIONS", max_iterations))
        self.timeout_seconds = timeout_seconds
        self.decision_callback = decision_callback or self._default_decision_strategy
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused by default
        self._is_cancelled = False
        self._execution_history: List[Dict[str, Any]] = []

    def pause(self) -> None:
        """Pause worker execution immediately."""
        self.state = WorkerState.PAUSED
        self._pause_event.clear()
        logger.info(f"Worker {self.agent_id} paused.")

    def resume(self, recovery_context: Optional[AgentContextPackage] = None) -> None:
        """Resume worker execution, optionally incorporating new recovery context."""
        if recovery_context:
            self.state = WorkerState.RECOVERING
        else:
            self.state = WorkerState.RUNNING
        self._pause_event.set()
        logger.info(f"Worker {self.agent_id} resumed in state {self.state.value}.")

    def cancel(self) -> None:
        """Cancel worker execution."""
        self._is_cancelled = True
        self.state = WorkerState.FAILED
        self._pause_event.set()

    async def run(self, context_package: AgentContextPackage) -> Dict[str, Any]:
        """
        Execute the autonomous worker loop against the sandboxed workspace.
        Does NOT declare task verified - only execution completed.
        """
        self.state = WorkerState.RUNNING
        self._is_cancelled = False
        self._pause_event.set()
        mission_id = context_package.mission_id
        task = context_package.task
        task_id = task.get("id", "task_unknown")

        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=self.agent_id,
                type=EventType.AGENT_STARTED,
                payload={"role": self.role, "objective": context_package.objective, "task": task}
            )
        )

        start_time = time.monotonic()
        iteration = 0

        while iteration < self.max_iterations and not self._is_cancelled:
            # Check timeout
            if (time.monotonic() - start_time) > self.timeout_seconds:
                self.state = WorkerState.FAILED
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=task_id,
                        agent_id=self.agent_id,
                        type=EventType.AGENT_FAILED,
                        severity=EventSeverity.ERROR,
                        payload={"reason": f"Execution timed out after {self.timeout_seconds}s."}
                    )
                )
                return {"status": "timeout", "iterations": iteration}

            # Check if paused (e.g. by Supervisor)
            if not self._pause_event.is_set():
                self.state = WorkerState.PAUSED
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=task_id,
                        agent_id=self.agent_id,
                        type=EventType.AGENT_PAUSED,
                        severity=EventSeverity.WARNING,
                        payload={"reason": "Paused by supervisor intervention or operator."}
                    )
                )
                await self._pause_event.wait()
                if self._is_cancelled:
                    break
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=task_id,
                        agent_id=self.agent_id,
                        type=EventType.AGENT_RESUMED,
                        payload={"state": self.state.value}
                    )
                )

            iteration += 1

            # 1. Ask decision provider for next action
            try:
                worker_action: WorkerAction = self.decision_callback(context_package, self._execution_history)
            except Exception as e:
                logger.error(f"Error formulating worker action: {e}")
                worker_action = WorkerAction(
                    action="finish_task",
                    arguments={},
                    thought_summary=f"Encountered error formulating action: {e}"
                )

            # 2. Check for completion request
            if worker_action.action == "finish_task":
                self.state = WorkerState.COMPLETED
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=task_id,
                        agent_id=self.agent_id,
                        type=EventType.AGENT_COMPLETED,
                        payload={
                            "summary": worker_action.thought_summary,
                            "iterations": iteration,
                            "duration_seconds": round(time.monotonic() - start_time, 2)
                        }
                    )
                )
                return {
                    "status": "completed",
                    "iterations": iteration,
                    "summary": worker_action.thought_summary
                }

            # 3. Validate tool
            tool_name = worker_action.action
            if tool_name not in self.tools:
                await self.event_bus.publish(
                    Event(
                        mission_id=mission_id,
                        task_id=task_id,
                        agent_id=self.agent_id,
                        type=EventType.TOOL_FAILED,
                        severity=EventSeverity.ERROR,
                        payload={"tool": tool_name, "error": f"Tool '{tool_name}' not available."}
                    )
                )
                continue

            # 4. Emit action description (thought_summary only, no chain-of-thought)
            await self.emit_action(
                mission_id=mission_id,
                task_id=task_id,
                description=worker_action.thought_summary,
                metadata={"action": tool_name}
            )

            # 5. Execute tool via sandbox
            result = await self.call_tool(
                tool_name=tool_name,
                arguments=worker_action.arguments,
                mission_id=mission_id,
                task_id=task_id
            )

            # 6. Record observation in execution history
            self._execution_history.append({
                "iteration": iteration,
                "action": tool_name,
                "arguments": worker_action.arguments,
                "success": result.success,
                "output": result.output[:300] if result.output else None,
                "error": result.error[:300] if result.error else None,
                "metadata": result.metadata
            })

            # Emit task progress
            await self.event_bus.publish(
                Event(
                    mission_id=mission_id,
                    task_id=task_id,
                    agent_id=self.agent_id,
                    type=EventType.TASK_PROGRESS,
                    payload={"iteration": iteration, "last_action": tool_name, "success": result.success}
                )
            )

            # Allow cooperative context switch
            await asyncio.sleep(0.01)

        # Reached max iterations
        self.state = WorkerState.FAILED
        await self.event_bus.publish(
            Event(
                mission_id=mission_id,
                task_id=task_id,
                agent_id=self.agent_id,
                type=EventType.AGENT_FAILED,
                severity=EventSeverity.ERROR,
                payload={"reason": f"Exceeded maximum iterations limit ({self.max_iterations})."}
            )
        )
        return {"status": "max_iterations_reached", "iterations": iteration}

    def _default_decision_strategy(
        self,
        context: AgentContextPackage,
        history: List[Dict[str, Any]]
    ) -> WorkerAction:
        """
        Deterministic, real decision strategy for the demo project coding tasks.
        Observes real test outputs, applies naive attempts, and uses recovery context
        when present to apply the genuine fix.
        """
        task_id = context.task.get("id", "")

        # Check if we have received a recovery strategy from Reviewer/Memory
        recovery_rec = None
        for item in context.relevant_memory:
            if "BOM" in item.get("fact", "") or "utf-8" in item.get("fact", "").lower():
                recovery_rec = item.get("fact")

        # Did we just run tests and they passed?
        if history and history[-1]["action"] == "run_tests":
            last_meta = history[-1].get("metadata", {})
            if last_meta.get("passed", 0) > 0 and last_meta.get("failed", 0) == 0:
                return WorkerAction(
                    action="finish_task",
                    arguments={},
                    thought_summary="All tests passed successfully. Task execution finished."
                )

        # Did we just edit the file with recovery fix?
        if history and history[-1]["action"] == "edit_file" and history[-1]["success"]:
            return WorkerAction(
                action="run_tests",
                arguments={"test_command": "python -m pytest tests/test_parser.py -v"},
                thought_summary="Running pytest to verify parser modifications."
            )

        # Has recovery context arrived?
        if recovery_rec:
            return WorkerAction(
                action="edit_file",
                arguments={
                    "path": "src/parser.py",
                    "target_content": '    reader = csv.DictReader(io.StringIO(raw_content))',
                    "replacement_content": '    cleaned = raw_content.lstrip("\\ufeff")\n    reader = csv.DictReader(io.StringIO(cleaned))'
                },
                thought_summary=f"Applying recommended recovery strategy: normalize UTF-8 BOM before CSV parsing."
            )

        # Initial steps:
        if not history:
            return WorkerAction(
                action="read_file",
                arguments={"path": "src/parser.py"},
                thought_summary="Inspecting existing CSV parser implementation."
            )

        # Next: Run tests to establish baseline
        if len(history) == 1 and history[0]["action"] == "read_file":
            return WorkerAction(
                action="run_tests",
                arguments={"test_command": "python -m pytest tests/test_parser.py -v"},
                thought_summary="Running test suite to verify baseline functionality."
            )

        # If tests failed without recovery, retry tests or naive inspection
        return WorkerAction(
            action="run_tests",
            arguments={"test_command": "python -m pytest tests/test_parser.py -v"},
            thought_summary="Retrying test execution to confirm failure signature."
        )
