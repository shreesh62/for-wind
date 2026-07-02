"""Perception/WorldState request schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PerceiveRequest(BaseModel):
    """Request a fresh perception snapshot."""

    include_ocr: bool = Field(False, description="Run OCR (slower; needs Tesseract)")
    include_vision: bool = Field(False, description="Run vision model analysis (slower)")
