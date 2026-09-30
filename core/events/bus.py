import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from core.events.schema import Event, EventType

logger = logging.getLogger("supervisor.event_bus")

# Type alias for async event handler
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    Central Asynchronous Event Bus.
    Allows agents, supervisor, memory, and dashboard websocket hubs to publish
    and subscribe to events in real time without hard coupling.
    """

    def __init__(self):
        # Specific subscribers by EventType
        self._subscribers: Dict[EventType, List[EventHandler]] = {}
        # Wildcard subscribers (receive all events)
        self._global_subscribers: List[EventHandler] = []
        # Filtered mission subscribers: mission_id -> list of handlers
        self._mission_subscribers: Dict[str, List[EventHandler]] = {}
        # Lock for thread-safe handler mutation
        self._lock = asyncio.Lock()

    def subscribe_sync(
        self,
        handler: EventHandler,
        event_type: Optional[EventType] = None,
        mission_id: Optional[str] = None
    ) -> None:
        """Synchronously subscribe an async handler."""
        if mission_id:
            if mission_id not in self._mission_subscribers:
                self._mission_subscribers[mission_id] = []
            self._mission_subscribers[mission_id].append(handler)
        elif event_type:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)
        else:
            self._global_subscribers.append(handler)

    async def subscribe(
        self,
        handler: EventHandler,
        event_type: Optional[EventType] = None,
        mission_id: Optional[str] = None
    ) -> None:
        """Subscribe an async handler to specific event types or global stream."""
        self.subscribe_sync(handler, event_type, mission_id)

    async def unsubscribe(
        self,
        handler: EventHandler,
        event_type: Optional[EventType] = None,
        mission_id: Optional[str] = None
    ) -> None:
        """Unsubscribe an async handler."""
        async with self._lock:
            if mission_id and mission_id in self._mission_subscribers:
                self._mission_subscribers[mission_id] = [
                    h for h in self._mission_subscribers[mission_id] if h != handler
                ]
            elif event_type and event_type in self._subscribers:
                self._subscribers[event_type] = [
                    h for h in self._subscribers[event_type] if h != handler
                ]
            else:
                self._global_subscribers = [
                    h for h in self._global_subscribers if h != handler
                ]

    async def publish(self, event: Event) -> None:
        """
        Publish an event to all matching subscribers asynchronously.
        Ensures an exception in one handler does not halt other handlers.
        """
        targets: List[EventHandler] = []

        async with self._lock:
            # 1. Global subscribers
            targets.extend(self._global_subscribers)

            # 2. Type-specific subscribers
            if event.type in self._subscribers:
                targets.extend(self._subscribers[event.type])

            # 3. Mission-specific subscribers
            if event.mission_id in self._mission_subscribers:
                targets.extend(self._mission_subscribers[event.mission_id])

        if not targets:
            return

        # Deduplicate handlers that match both type and mission
        unique_targets = list(dict.fromkeys(targets))

        # Run all subscriber handlers concurrently
        results = await asyncio.gather(
            *[self._safe_invoke(handler, event) for handler in unique_targets],
            return_exceptions=True
        )

        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Error handling event {event.event_id}: {res}")

    async def _safe_invoke(self, handler: EventHandler, event: Event) -> None:
        try:
            await handler(event)
        except Exception as e:
            logger.exception(f"Unhandled error in event handler {handler.__name__ if hasattr(handler, '__name__') else handler}: {e}")
            raise
