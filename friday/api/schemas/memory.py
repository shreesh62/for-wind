"""Memory access schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MemorySearchRequest(BaseModel):
    """Request to search memory."""

    query: str = Field(..., description="Search query", min_length=1)
    top_k: int = Field(5, ge=1, le=50, description="Max results to return")
    tier: Optional[str] = Field(
        None, description="Limit to a tier: 'episodic', 'procedural', 'semantic', or null for all"
    )


class MemoryEntrySchema(BaseModel):
    """A memory entry in search results."""

    content: str
    tier: str
    timestamp: float
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemorySearchResponse(BaseModel):
    """Memory search results."""

    results: List[MemoryEntrySchema] = Field(default_factory=list)


class MemoryEpisodeSchema(BaseModel):
    """An interaction episode."""

    user: str
    assistant: str
    mode: str
    timestamp: float
    success: Optional[bool] = None


class RecentMemoryResponse(BaseModel):
    """Recent interaction history."""

    episodes: List[MemoryEpisodeSchema] = Field(default_factory=list)


class RememberFactRequest(BaseModel):
    """Request to store a durable fact in semantic memory."""

    content: str = Field(..., description="The fact to remember", min_length=1)
    category: str = Field("general", description="Category: general, user, app, site, preference")
