"""WebSocket event schemas — real-time event stream contracts."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events streamed over WebSocket."""

    # Outbound (server → client)
    COMMAND_COMPLETED = "command_completed"
    COMMAND_RESPONSE = "command_response"
    STATUS_UPDATE = "status_update"
    TASK_PROGRESS = "task_progress"
    NOTIFICATION = "notification"
    SCREENSHOT = "screenshot"
    ERROR = "error"
    PONG = "pong"

    # Inbound (client → server)
    COMMAND = "command"
    PING = "ping"
    SUBSCRIBE = "subscribe"


class WebSocketEvent(BaseModel):
    """A WebSocket message envelope.

    All WebSocket messages (both directions) use this shape:
        { "type": "<event_type>", "data": { ... } }
    """

    type: EventType
    data: Dict[str, Any] = Field(default_factory=dict)
