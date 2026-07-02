"""Error response schemas."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response shape.

    FastAPI returns errors as {"detail": "..."} by default.
    This documents that contract for frontend consumers.
    """

    detail: str = Field(..., description="Human-readable error message")
    code: Optional[str] = Field(None, description="Machine-readable error code")
    context: Dict[str, Any] = Field(default_factory=dict)
