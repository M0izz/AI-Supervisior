from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import List, Optional

from core.protocol.schema import TaskDispatchPackage
from core.protocol.validators import validate_dispatch_package
from adapters.models import (
    AdapterIdentity,
    AdapterAvailability,
    AdapterProcessStatus,
    AdapterExecutionResult,
)

logger = logging.getLogger("supervisor.adapters.base")


class AgentAdapter(ABC):
    """
    Abstract Universal Agent Adapter Contract.
    Defines the standard boundary between AI Supervisor and any external agent runtime
    (Claude Code, OpenAI Codex, Gemini CLI, local LLMs, etc.).
    """

    @property
    @abstractmethod
    def identity(self) -> AdapterIdentity:
        """Returns structured metadata identifying this adapter."""
        pass

    @property
    def capabilities(self) -> List[str]:
        """Convenience property returning the declared capabilities of this adapter."""
        return self.identity.capabilities

    @abstractmethod
    async def check_availability(self) -> AdapterAvailability:
        """
        Lightweight probe verifying whether the required CLI tool, binary, or credentials
        are installed and available in the local environment.
        Must NOT launch full tasks or consume significant quota.
        """
        pass

    async def prepare(self, dispatch: TaskDispatchPackage) -> bool:
        """
        Pre-flight validation ensuring dispatch package correctness and workspace isolation.
        Can be overridden or extended by specific adapters.
        """
        validate_dispatch_package(dispatch)
        ws_path = Path(dispatch.workspace)
        if not ws_path.exists() or not ws_path.is_dir():
            raise ValueError(f"Target workspace does not exist or is not a directory: {dispatch.workspace}")
        return True

    @abstractmethod
    async def execute(self, dispatch: TaskDispatchPackage) -> AdapterExecutionResult:
        """
        Executes an assigned task inside its designated isolated workspace/worktree.
        Streams lifecycle events and returns a structured outcome upon termination.
        """
        pass

    @abstractmethod
    async def cancel(self, task_id: str) -> bool:
        """
        Cancels an ongoing task process gracefully, escalating if needed.
        """
        pass

    @abstractmethod
    async def status(self, task_id: str) -> AdapterProcessStatus:
        """
        Returns the real-time process lifecycle status for a given task.
        """
        pass

    @abstractmethod
    async def cleanup(self, task_id: str) -> None:
        """
        Releases process handles and internal session tracking resources.
        """
        pass
