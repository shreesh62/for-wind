"""Command execution routes."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request

from friday.api.schemas.commands import CommandRequest, CommandResponse


def build_router(ctx, auth) -> APIRouter:
    """Build the commands router bound to app context + auth dependency."""
    router = APIRouter(prefix="/api", tags=["commands"])

    @router.post("/command", response_model=CommandResponse, dependencies=[Depends(auth)])
    async def execute_command(request: CommandRequest) -> CommandResponse:
        """Execute a command through JARVIS/FRIDAY routing.

        - JARVIS mode (questions): fast LLM response, no agent loop
        - FRIDAY mode (actions): perceive → plan → act → verify
        """
        if not ctx.bridge:
            return CommandResponse(ok=False, error="Bridge not initialized")

        start = time.perf_counter()
        try:
            result = ctx.bridge.process(
                command=request.text,
                wake_word=request.wake_word,
                context=request.metadata,
            )
            duration = (time.perf_counter() - start) * 1000

            verified = None
            if result.action_result is not None:
                verified = getattr(result.action_result, "verified", None)

            response = CommandResponse(
                ok=True,
                text=result.response,
                mode=result.mode.value,
                complexity=int(result.complexity),
                handled=result.handled,
                verified=verified,
                duration_ms=duration,
            )

            # Record to memory if available
            if ctx.memory:
                try:
                    ctx.memory.record_turn(
                        user_text=request.text,
                        assistant_response=result.response,
                        mode=result.mode.value,
                        complexity=int(result.complexity),
                        duration_ms=duration,
                    )
                except Exception:
                    pass

            # Broadcast to WebSocket clients
            await _broadcast(ctx, {"type": "command_completed", "data": response.model_dump()})

            return response

        except Exception as exc:
            return CommandResponse(
                ok=False,
                text="",
                error=str(exc),
                duration_ms=(time.perf_counter() - start) * 1000,
            )

    return router


async def _broadcast(ctx, message: dict) -> None:
    """Broadcast a message to all WebSocket clients."""
    disconnected = []
    for ws in ctx.ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in ctx.ws_clients:
            ctx.ws_clients.remove(ws)
