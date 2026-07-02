"""Lightweight reasoning helpers to determine execution routes for commands."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from capabilities import CapabilityRegistry

try:  # Optional awareness dependency
    from awareness.state_cache import StateCache
except ImportError:  # pragma: no cover
    StateCache = None  # type: ignore

_AUTOMATION_KEYWORDS = (
    "screenshot",
    "screen capture",
    "capture screen",
    "capture the screen",
    "capture screenshot",
    "capture a screenshot",
    "take screenshot",
    "take a screenshot",
    "focus",
    "type",
    "click",
    "double click",
    "tap",
    "double tap",
    "press",
    "hit",
    "select",
    "scroll",
    "page down",
    "page up",
    "ocr",
    "read screen",
    "scan screen",
    "browser",
    "tab",
    "chrome",
    "open",
    "go to",
    "visit",
    "take me to",
    "navigate",
    "launch",
    "start",
    "play",
    "spotify",
    "youtube",
    "netflix",
    "app",
)

_NON_AUTOMATION_CAPABILITIES = {
    "qa_general",
    "self_describe",
    "personal_memory",
    "weather_check",
    "maps_distance",
    "maps_travel_time",
    "news_brief",
}


@dataclass(slots=True)
class ReasoningOutcome:
    """Represents a lightweight reasoning decision for a command."""

    route: str
    capability: Optional[str] = None
    justification: str = ""


def reason_about_command(
    command: str,
    registry: CapabilityRegistry,
    *,
    awareness_state: "StateCache | None" = None,
) -> ReasoningOutcome:
    """Produce a simple execution plan for the given natural-language command."""
    
    # COGNITIVE_MODE: Use cognitive loop as primary execution path
    cognitive_mode = os.getenv("COGNITIVE_MODE", "0") == "1"
    
    normalized = command.lower().strip()
    capability_key, _ = registry.match_intent(normalized)

    context_bits: list[str] = []
    if awareness_state is not None:
        window = awareness_state.get_window()
        if window and window.title:
            context_bits.append(f"Active window: {window.title}")
        browser = getattr(awareness_state, "get_browser_summary", lambda: None)()
        if browser and browser.get("title"):
            context_bits.append(f"Browser tab: {browser.get('title')}")

    if capability_key and registry.is_available(capability_key):
        if capability_key in _NON_AUTOMATION_CAPABILITIES:
            notes = [f"Capability '{capability_key}' available."] + context_bits
            return ReasoningOutcome("capability", capability=capability_key, justification=" | ".join(notes))
        notes = [f"Capability '{capability_key}' is automation-like; using planner."] + context_bits
        return ReasoningOutcome("automation", capability=capability_key, justification=" | ".join(notes))

    if any(keyword in normalized for keyword in _AUTOMATION_KEYWORDS):
        notes = ["Keywords suggest desktop/browser automation."] + context_bits
        # In cognitive mode, route automation through cognitive loop
        if cognitive_mode:
            notes.append("[COGNITIVE_MODE: Using cognitive loop]")
        return ReasoningOutcome("automation", capability=None, justification=" | ".join(notes))

    # In cognitive mode, try cognitive loop for most commands before falling back to LLM
    if cognitive_mode:
        # Check if command looks like it could be automated
        action_verbs = ["open", "close", "start", "stop", "send", "message", "search", "find", "get"]
        if any(verb in normalized for verb in action_verbs):
            notes = ["[COGNITIVE_MODE: Attempting cognitive execution]"] + context_bits
            return ReasoningOutcome("automation", capability=None, justification=" | ".join(notes))
    
    notes = ["Falling back to conversational response."] + context_bits
    return ReasoningOutcome("llm", capability=None, justification=" | ".join(notes))
