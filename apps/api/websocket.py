import asyncio
import logging
from typing import List, Set
from fastapi import WebSocket, WebSocketDisconnect
from core.events.schema import Event

logger = logging.getLogger("supervisor.websocket")


class WebSocketHub:
    """Manages active WebSocket connections from Control Room Dashboards."""

    def __init__(self):
        self._active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Active: {len(self._active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Active: {len(self._active_connections)}")

    async def broadcast_event(self, event: Event) -> None:
        """Forward an event from the EventBus to all connected frontend clients."""
        if not self._active_connections:
            return

        payload = event.model_dump_json()
        dead_sockets: List[WebSocket] = []

        async with self._lock:
            sockets = list(self._active_connections)

        for ws in sockets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead_sockets.append(ws)

        if dead_sockets:
            async with self._lock:
                for dead in dead_sockets:
                    self._active_connections.discard(dead)


ws_hub = WebSocketHub()
