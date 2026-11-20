"""WebSocket connection management for dashboard push notifications."""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket, WebSocketDisconnect


class ConnectionManager:
    """Broadcast events to all connected dashboard clients."""

    def __init__(self) -> None:
        """Initialize an empty connection list."""
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track a WebSocket connection."""
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send a JSON event to every connected client."""
        for connection in list(self.active):
            try:
                await connection.send_json(event)
            except (RuntimeError, WebSocketDisconnect):
                self.disconnect(connection)


manager = ConnectionManager()
