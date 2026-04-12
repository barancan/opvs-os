import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        await websocket.accept()
        self._connections[client_id] = websocket
        await self.send_to(client_id, "status_snapshot", {"connected": True})

    def disconnect(self, client_id: str) -> None:
        self._connections.pop(client_id, None)

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        message = self._make_event(event_type, payload)
        dead: list[str] = []
        for client_id, websocket in self._connections.items():
            try:
                await websocket.send_text(message)
            except Exception:
                dead.append(client_id)
        for client_id in dead:
            self.disconnect(client_id)

    async def send_to(
        self, client_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        websocket = self._connections.get(client_id)
        if websocket is not None:
            message = self._make_event(event_type, payload)
            await websocket.send_text(message)

    def _make_event(self, event_type: str, payload: dict[str, Any]) -> str:
        return json.dumps(
            {
                "type": event_type,
                "payload": payload,
                "ts": datetime.utcnow().isoformat(),
            }
        )


manager = WebSocketManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, client_id: str = "default") -> None:
    await manager.connect(websocket, client_id)
    logger.info("WebSocket connected: client_id=%s", client_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info("WebSocket disconnected: client_id=%s", client_id)
