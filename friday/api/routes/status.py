"""Health and status routes."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from friday.api.schemas.status import HealthResponse, StatusResponse


def build_router(ctx, auth) -> APIRouter:
    """Build the status router."""
    router = APIRouter(prefix="/api", tags=["status"])

    @router.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Health check — no auth required. Used by clients to verify connectivity."""
        return HealthResponse(
            status="ok",
            version="0.1.0",
            uptime=time.time() - ctx.start_time,
        )

    @router.get("/status", response_model=StatusResponse, dependencies=[Depends(auth)])
    async def get_status() -> StatusResponse:
        """Full system status: mode, active goal, memory + model stats."""
        memory_stats = {}
        active_goal = None
        if ctx.memory:
            try:
                memory_stats = ctx.memory.get_statistics()
                if ctx.memory.working.active_goal:
                    active_goal = ctx.memory.working.active_goal.text
            except Exception:
                pass

        model_stats = {}
        if ctx.model_router:
            try:
                model_stats = ctx.model_router.get_usage_stats()
            except Exception:
                pass

        return StatusResponse(
            online=True,
            mode="active" if active_goal else "idle",
            active_goal=active_goal,
            uptime_seconds=time.time() - ctx.start_time,
            memory_stats=memory_stats,
            model_stats=model_stats,
        )

    return router
