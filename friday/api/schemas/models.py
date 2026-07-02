"""Model router schemas."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ModelInfoSchema(BaseModel):
    """Information about an available model."""

    provider: str
    model_id: str
    capabilities: List[str]
    priority: int


class ModelsResponse(BaseModel):
    """Available models and usage stats."""

    providers: List[str] = Field(default_factory=list)
    models: List[ModelInfoSchema] = Field(default_factory=list)
    usage: Dict[str, Any] = Field(default_factory=dict)
