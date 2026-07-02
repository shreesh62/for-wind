"""WorldState schema for the perception API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorldStateSchema(BaseModel):
    """Serialized WorldState — the perception snapshot.

    Mirrors WorldState.to_summary(). The planner reasons on this,
    never on raw pixels (ADR-014).
    """

    timestamp: float
    window: Optional[str] = Field(None, description="Active window title")
    app: Optional[str] = Field(None, description="Active process name")
    cursor: List[int] = Field(default_factory=lambda: [0, 0])
    focused: Optional[str] = Field(None, description="Focused element text")
    ui_elements: int = Field(0, description="Count of UIA elements detected")
    ocr_regions: int = Field(0, description="Count of OCR text regions")
    browser_url: Optional[str] = None
    browser_title: Optional[str] = None
    browser_elements: int = Field(0, description="Count of DOM elements")
    derived: Dict[str, bool] = Field(
        default_factory=dict, description="Derived facts (login, error, loading, modal)"
    )
    state_hash: str = Field("", description="Hash for change detection")
    sources: List[str] = Field(
        default_factory=list, description="Perception sources used (process/uia/ocr/browser/screen)"
    )
    semantic_coverage: float = Field(
        0.0, description="Fraction of perception that is semantic vs visual (0-1)"
    )
