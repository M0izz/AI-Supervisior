from abc import ABC, abstractmethod
from typing import Optional
from core.events.bus import EventBus
from execution.models import ExecutionRequest, ExecutionResult


class BaseExecutionProvider(ABC):
    """Abstract base provider for task command execution."""

    backend_name: str = "base"

    def __init__(self, event_bus: Optional[EventBus] = None):
        self.event_bus = event_bus

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if execution backend is currently operational and available."""
        pass

    @abstractmethod
    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute command within isolated workspace boundaries."""
        pass
