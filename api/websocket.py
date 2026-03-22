"""WebSocket endpoint for real-time dashboard updates.

Provides push-based updates for:
- Pod status changes
- GPU utilization streaming
- Incident alerts
- Chat response notifications
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage active WebSocket connections.

    Provides methods to accept new connections, remove disconnected
    clients, and broadcast JSON messages to all connected clients.
    """

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection.

        Args:
            websocket: The incoming WebSocket connection to accept.
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "WebSocket client connected",
            extra={"total_connections": len(self.active_connections)},
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket from the active list.

        Args:
            websocket: The WebSocket connection to remove.
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            "WebSocket client disconnected",
            extra={"total_connections": len(self.active_connections)},
        )

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected WebSocket clients.

        Silently removes clients that have disconnected or error during send.

        Args:
            message: Dictionary payload to broadcast as JSON.
        """
        disconnected: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except WebSocketDisconnect:
                disconnected.append(connection)
            except Exception as e:
                logger.warning(
                    "Failed to send WebSocket message",
                    extra={"error": str(e)},
                )
                disconnected.append(connection)

        # Clean up any disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()

# ---------------------------------------------------------------------------
# WebSocket Router
# ---------------------------------------------------------------------------

ws_router = APIRouter()


@ws_router.websocket("/ws/updates")
async def websocket_updates(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time infrastructure updates.

    Accepts a WebSocket connection and keeps it alive, listening for
    incoming messages (e.g., ping/pong or subscription requests).
    Server-side events are pushed via the ConnectionManager.broadcast method.

    Args:
        websocket: The incoming WebSocket connection.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive by receiving messages from client.
            # Clients can send ping or subscription messages.
            data: str = await websocket.receive_text()
            logger.debug("WebSocket received message", extra={"data": data})

            # Echo acknowledgment back to the client
            await websocket.send_json({"type": "ack", "message": data})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket client disconnected normally")
    except Exception as e:
        logger.error("WebSocket connection error", extra={"error": str(e)})
        manager.disconnect(websocket)
