import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# WebSocket event type constants
WS_KILL_SWITCH_ACTIVATED = "kill_switch_activated"
WS_KILL_SWITCH_RECOVERED = "kill_switch_recovered"
WS_CHAT_TOKEN = "chat_token"
WS_CHAT_COMPLETE = "chat_complete"
WS_CHAT_ERROR = "chat_error"
WS_NOTIFICATION_CREATED = "notification_created"
WS_NOTIFICATION_UPDATED = "notification_updated"
WS_COMPACT_TRIGGERED = "compact_triggered"
WS_TOOL_APPROVAL_REQUIRED = "tool_approval_required"
WS_TOOL_USED = "tool_used"
WS_TOOL_RESULT = "tool_result"
WS_TOOL_REJECTED = "tool_rejected"
WS_JOB_STARTED = "job_started"
WS_JOB_COMPLETED = "job_completed"
WS_JOB_FAILED = "job_failed"

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
