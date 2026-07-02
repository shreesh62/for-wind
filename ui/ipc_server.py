"""WebSocket-based IPC bridge between Jarvis core and desktop UI."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Set

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError:  # pragma: no cover - optional dependency
    websockets = None  # type: ignore[assignment]
    WebSocketServerProtocol = Any  # type: ignore[assignment]


MessageHandler = Callable[[Dict[str, Any]], Awaitable[None] | None]


class WebsocketUnavailable(RuntimeError):
    """Raised when WebSocket support is requested but library is missing."""


@dataclass
class UIEvent:
    """Represents a message destined for the UI layer."""

    type: str
    payload: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({"type": self.type, "payload": self.payload})


class UISocketServer:
    """Lightweight WebSocket server for two-way UI communication."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8800) -> None:
        if websockets is None:
            raise WebsocketUnavailable(
                "websockets package not installed. Run 'pip install websockets' to enable UI bridge."
            )

        self.host = host
        self.port = port
        self._server: Optional[websockets.server.Serve] = None
        self._clients: Set[WebSocketServerProtocol] = set()
        self._handlers: Set[MessageHandler] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        last_exc: Exception | None = None
        for port in range(self.port, self.port + 10):
            try:
                self._server = await websockets.serve(self._handle_client, self.host, port)
                self.port = port
                return
            except OSError as exc:
                last_exc = exc
                continue
        if last_exc:
            raise last_exc

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------
    async def broadcast(self, event: UIEvent) -> None:
        """Send an event to all connected UI clients."""

        if not self._clients:
            return
        message = event.to_json()
        await asyncio.gather(*(client.send(message) for client in self._clients), return_exceptions=True)

    def register_handler(self, handler: MessageHandler) -> None:
        """Register a callback for inbound messages from UI."""

        self._handlers.add(handler)

    def unregister_handler(self, handler: MessageHandler) -> None:
        self._handlers.discard(handler)

    # ------------------------------------------------------------------
    # Internal plumbing
    # ------------------------------------------------------------------
    async def _handle_client(
        self,
        websocket: WebSocketServerProtocol,
        path: str | None = None,
    ) -> None:
        self._clients.add(websocket)
        try:
            async for raw in websocket:
                payload = self._parse_json(raw)
                if payload is None:
                    continue
                await self._dispatch(payload)
        finally:
            self._clients.discard(websocket)

    async def _dispatch(self, payload: Dict[str, Any]) -> None:
        for handler in list(self._handlers):
            result = handler(payload)
            if asyncio.iscoroutine(result):
                await result

    @staticmethod
    def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return None
        return None
