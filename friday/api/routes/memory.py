"""Memory access routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from friday.api.schemas.memory import (
    MemoryEntrySchema,
    MemoryEpisodeSchema,
    MemorySearchRequest,
    MemorySearchResponse,
    RecentMemoryResponse,
    RememberFactRequest,
)


def build_router(ctx, auth) -> APIRouter:
    """Build the memory router."""
    router = APIRouter(prefix="/api/memory", tags=["memory"])

    @router.post("/search", response_model=MemorySearchResponse, dependencies=[Depends(auth)])
    async def search_memory(request: MemorySearchRequest) -> MemorySearchResponse:
        """Search memory across tiers by query."""
        if not ctx.memory:
            raise HTTPException(status_code=503, detail="Memory not initialized")

        results = []

        if request.tier in (None, "episodic"):
            for ep in ctx.memory.episodic.recall(request.query, top_k=request.top_k):
                results.append(MemoryEntrySchema(
                    content=f"User: {ep.user_text}\nAssistant: {ep.assistant_response}",
                    tier="episodic",
                    timestamp=ep.timestamp,
                    tags=[ep.mode],
                    metadata={"action_type": ep.action_type, "success": ep.action_success},
                ))

        if request.tier in (None, "semantic"):
            for fact in ctx.memory.semantic.search(request.query, top_k=request.top_k):
                results.append(MemoryEntrySchema(
                    content=fact.content,
                    tier="semantic",
                    timestamp=fact.timestamp,
                    tags=[fact.category],
                    metadata={"confidence": fact.confidence},
                ))

        if request.tier in (None, "procedural"):
            for entry in ctx.memory.procedural._store.retrieve(request.query, top_k=request.top_k):
                results.append(MemoryEntrySchema(
                    content=entry.content,
                    tier="procedural",
                    timestamp=entry.timestamp,
                    tags=entry.tags,
                    metadata=entry.metadata,
                ))

        return MemorySearchResponse(results=results[:request.top_k])

    @router.get("/recent", response_model=RecentMemoryResponse, dependencies=[Depends(auth)])
    async def recent_memory(limit: int = 10) -> RecentMemoryResponse:
        """Get recent interaction history."""
        if not ctx.memory:
            raise HTTPException(status_code=503, detail="Memory not initialized")

        episodes = [
            MemoryEpisodeSchema(
                user=ep.user_text,
                assistant=ep.assistant_response,
                mode=ep.mode,
                timestamp=ep.timestamp,
                success=ep.action_success,
            )
            for ep in ctx.memory.episodic.recent(limit=limit)
        ]
        return RecentMemoryResponse(episodes=episodes)

    @router.post("/remember", dependencies=[Depends(auth)])
    async def remember_fact(request: RememberFactRequest):
        """Store a durable fact in semantic memory."""
        if not ctx.memory:
            raise HTTPException(status_code=503, detail="Memory not initialized")
        ctx.memory.remember_fact(request.content, category=request.category)
        return {"ok": True, "stored": request.content}

    return router
