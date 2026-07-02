"""API schemas — Pydantic request/response contracts.

Centralized so both the API implementation and the
FRONTEND_INTEGRATION_GUIDE stay in sync. Every endpoint's
input/output is defined here.
"""

from friday.api.schemas.commands import CommandRequest, CommandResponse
from friday.api.schemas.status import StatusResponse, HealthResponse
from friday.api.schemas.memory import (
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryEntrySchema,
    RecentMemoryResponse,
    MemoryEpisodeSchema,
    RememberFactRequest,
)
from friday.api.schemas.models import ModelInfoSchema, ModelsResponse
from friday.api.schemas.worldstate import WorldStateSchema
from friday.api.schemas.tasks import TaskStatusSchema, TaskMonitorResponse
from friday.api.schemas.events import WebSocketEvent, EventType
from friday.api.schemas.errors import ErrorResponse

__all__ = [
    "CommandRequest",
    "CommandResponse",
    "StatusResponse",
    "HealthResponse",
    "MemorySearchRequest",
    "MemorySearchResponse",
    "MemoryEntrySchema",
    "RecentMemoryResponse",
    "MemoryEpisodeSchema",
    "RememberFactRequest",
    "ModelInfoSchema",
    "ModelsResponse",
    "WorldStateSchema",
    "TaskStatusSchema",
    "TaskMonitorResponse",
    "WebSocketEvent",
    "EventType",
    "ErrorResponse",
]
