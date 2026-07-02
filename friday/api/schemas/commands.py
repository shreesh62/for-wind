"""Command execution schemas."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CommandRequest(BaseModel):
    """Request to execute a command via JARVIS/FRIDAY routing."""

    text: str = Field(..., description="The command or question text", min_length=1)
    wake_word: Optional[str] = Field(
        None, description="Detected wake word: 'jarvis' (assistant) or 'friday' (agent)"
    )
    speak: bool = Field(False, description="Whether to speak the response via TTS")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Optional context metadata"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"text": "What is Python?"},
                {"text": "Open Chrome and search for laptops", "wake_word": "friday"},
            ]
        }
    }


class CommandResponse(BaseModel):
    """Response from command execution."""

    ok: bool = Field(..., description="Whether the command was handled without error")
    text: str = Field("", description="The response text to show/speak to the user")
    mode: str = Field("jarvis", description="Which mode handled it: 'jarvis' or 'friday'")
    complexity: int = Field(0, description="Complexity level 0-3 (0=question, 3=complex goal)")
    handled: bool = Field(True, description="Whether the request produced a response")
    verified: Optional[bool] = Field(
        None, description="For FRIDAY actions: whether the outcome was verified by evidence"
    )
    duration_ms: float = Field(0.0, description="Processing time in milliseconds")
    error: Optional[str] = Field(None, description="Error message if ok is false")
