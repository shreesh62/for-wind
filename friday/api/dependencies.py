"""Shared API dependencies — auth, service accessors.

Uses a simple app-state container so routes can access the
bridge, memory, and model router without globals.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, List, Optional

from fastapi import Header, HTTPException, WebSocket


@dataclass
class AppContext:
    """Container for shared services, attached to app.state."""

    bridge: Any = None
    memory: Any = None
    model_router: Any = None
    api_key: str = ""
    start_time: float = 0.0
    ws_clients: List[WebSocket] = field(default_factory=list)


def make_auth_dependency(api_key: str):
    """Create an auth dependency bound to a specific API key."""

    async def verify_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
        if api_key and x_api_key != api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return True

    return verify_api_key


def verify_ws_token(websocket: WebSocket, api_key: str) -> bool:
    """Validate a WebSocket connection token (query param)."""
    if not api_key:
        return True
    token = websocket.query_params.get("token", "")
    return token == api_key
