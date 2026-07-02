"""System status and health schemas."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response (no auth required)."""

    status: str = Field("ok", description="Service status")
    version: str = Field(..., description="FRIDAY version")
    uptime: float = Field(..., description="Uptime in seconds")


class StatusResponse(BaseModel):
    """Full system status (requires auth)."""

    online: bool = Field(True, description="Whether the system is operational")
    mode: str = Field("idle", description="Current mode: idle or active")
    active_goal: Optional[str] = Field(None, description="Current goal text if FRIDAY is executing")
    uptime_seconds: float = Field(0.0, description="Uptime in seconds")
    memory_stats: Dict[str, Any] = Field(
        default_factory=dict, description="Memory tier statistics (working/episodic/procedural/semantic)"
    )
    model_stats: Dict[str, Any] = Field(
        default_factory=dict, description="Model router usage statistics"
    )
