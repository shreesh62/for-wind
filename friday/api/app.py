"""FRIDAY API — FastAPI backend for desktop and mobile clients.

API-first architecture (ADR-017). All business logic in the backend.
Frontends are thin clients that consume these contracts.

Structure:
    friday/api/
    ├── app.py            ← this file (assembly)
    ├── dependencies.py   ← AppContext, auth
    ├── schemas/          ← Pydantic contracts
    └── routes/           ← modular routers

Consumed by:
- Future desktop app (localhost)
- Future mobile app (remote, authenticated)

Auth: X-API-Key header (REST), ?token= (WebSocket)
Docs: auto-generated at /docs (OpenAPI)
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from friday.api.dependencies import AppContext, make_auth_dependency
from friday.api.routes import (
    commands as commands_routes,
    status as status_routes,
    memory as memory_routes,
    models as models_routes,
    tasks as tasks_routes,
    perception as perception_routes,
    websocket as websocket_routes,
)


def create_friday_api(
    bridge=None,
    memory=None,
    model_router=None,
    api_key: Optional[str] = None,
) -> FastAPI:
    """Create the FRIDAY FastAPI application.

    Args:
        bridge: FridayBridge for command execution
        memory: FridayMemory for memory access
        model_router: ModelRouter for model info
        api_key: Required API key (defaults to REMOTE_API_KEY env)

    Returns:
        Configured FastAPI app
    """
    ctx = AppContext(
        bridge=bridge,
        memory=memory,
        model_router=model_router,
        api_key=api_key if api_key is not None else os.getenv("REMOTE_API_KEY", ""),
        start_time=time.time(),
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        yield

    app = FastAPI(
        title="FRIDAY API",
        description="AI Operating System — backend platform for desktop and mobile clients",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store context on app state for introspection
    app.state.ctx = ctx

    # Build auth dependency bound to this api_key
    auth = make_auth_dependency(ctx.api_key)

    # Register modular routers
    app.include_router(status_routes.build_router(ctx, auth))
    app.include_router(commands_routes.build_router(ctx, auth))
    app.include_router(memory_routes.build_router(ctx, auth))
    app.include_router(models_routes.build_router(ctx, auth))
    app.include_router(tasks_routes.build_router(ctx, auth))
    app.include_router(perception_routes.build_router(ctx, auth))
    app.include_router(websocket_routes.build_router(ctx))

    return app
