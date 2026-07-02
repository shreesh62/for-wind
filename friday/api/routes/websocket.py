"""WebSocket route — real-time event stream."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from friday.api.dependencies import verify_ws_token


def build_router(ctx) -> APIRouter:
    """Build the WebSocket router."""
    router = APIRouter(tags=["websocket"])

    @router.websocket("/api/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """Real-time event stream.

        Auth: ?token=<API_KEY> query param.

        Client → Server messages:
            {"type": "command", "text": "...", "wake_word": null}
            {"type": "ping"}

        Server → Client messages:
            {"type": "command_response", "data": {...}}
            {"type": "command_completed", "data": {...}}
            {"type": "notification", "data": {...}}
            {"type": "pong"}
        """
        if not verify_ws_token(websocket, ctx.api_key):
            await websocket.close(code=4001, reason="Invalid token")
            return

        await websocket.accept()
        ctx.ws_clients.append(websocket)

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "command":
                    text = data.get("text", "")
                    wake_word = data.get("wake_word")
                    if ctx.bridge and text:
                        result = ctx.bridge.process(text, wake_word=wake_word)
                        await websocket.send_json({
                            "type": "command_response",
                            "data": {
                                "ok": True,
                                "text": result.response,
                                "mode": result.mode.value,
                                "complexity": int(result.complexity),
                            },
                        })

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

        except WebSocketDisconnect:
            pass
        finally:
            if websocket in ctx.ws_clients:
                ctx.ws_clients.remove(websocket)

    return router
