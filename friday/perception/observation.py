"""Ch 12 — Observation: the uniform record every sensor must produce."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Tuple

from friday.events.event import FrozenDict
from friday.perception.types import PerceptionSource


# Generic (application-agnostic) affordance inference from an object's semantic
# type. No browser/app/site logic (Axiom 15) — a "button" affords click anywhere.
_AFFORDANCE_BY_TYPE = {
    "button": ("click",),
    "link": ("click", "navigate"),
    "hyperlink": ("click", "navigate"),
    "menuitem": ("click",),
    "tab": ("click",),
    "tabitem": ("click",),
    "checkbox": ("toggle", "click"),
    "radiobutton": ("select", "click"),
    "textbox": ("type", "focus"),
    "edit": ("type", "focus"),
    "input": ("type", "focus"),
    "textarea": ("type", "focus"),
    "combobox": ("select", "type"),
    "listitem": ("select", "click"),
    "slider": ("adjust",),
    "scrollbar": ("scroll",),
    "document": ("scroll", "read"),
    "text": ("read",),
    "window": ("focus",),
}

# Sensor label -> PerceptionSource (application-agnostic).
_SENSOR_TO_SOURCE = {
    "dom": PerceptionSource.BROWSER,
    "browser": PerceptionSource.BROWSER,
    "uia": PerceptionSource.UIA,
    "ocr": PerceptionSource.OCR,
    "vision": PerceptionSource.VISION,
    "screen": PerceptionSource.SCREEN,
    "process": PerceptionSource.PROCESS,
}


@dataclass(frozen=True)
class Observation:
    """A single sensor reading — the uniform semantic World Object (Ch 12).

    Every observation carries confidence, freshness (A2.1 decay), evidence
    (raw-signal provenance), source, a bounding region, and possible affordances,
    so reasoning layers can act on it without knowing which sensor produced it and
    without any application-specific structure.
    """

    sensor: str  # "screen", "ocr", "dom", "uia", "clipboard", ...
    environment: str  # "browser", "desktop", "system"
    object_type: str  # "window", "button", "text", "url", ...
    attributes: FrozenDict = field(default_factory=FrozenDict)
    confidence: float = 1.0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    bbox: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h) if visual
    # A2.1 freshness: when set, freshness decays with age (half-life seconds).
    ttl_seconds: Optional[float] = None
    # Explicit affordances (producers MAY set them); otherwise inferred generically
    # from object_type via inferred_affordances().
    affordances: Tuple[str, ...] = ()

    def object_key(self) -> str:
        """Stable identity of the observed object, used for fusion."""
        name = self.attributes.get("name") or self.attributes.get("text") or ""
        return f"{self.environment}:{self.object_type}:{name}"

    @property
    def source(self) -> PerceptionSource:
        """The perception source this observation came from (semantic, not raw)."""
        return _SENSOR_TO_SOURCE.get((self.sensor or "").lower(), PerceptionSource.SCREEN)

    @property
    def evidence(self) -> FrozenDict:
        """Raw-signal provenance for this observation (the 'why' behind it)."""
        return FrozenDict({
            "sensor": self.sensor,
            "source": self.source.value,
            "confidence": self.confidence,
            "observation_id": self.id,
            "observed_at": self.timestamp,
        })

    def freshness(self, now: Optional[float] = None) -> float:
        """A2.1 freshness in [0,1]; 0.5 ** (age / ttl). 1.0 when no ttl is set.

        Non-increasing with age so a stale observation is downgraded, never
        silently trusted.
        """
        if self.ttl_seconds is None or self.ttl_seconds <= 0:
            return 1.0
        now = time.time() if now is None else now
        age = max(0.0, now - self.timestamp)
        return 0.5 ** (age / self.ttl_seconds)

    def inferred_affordances(self) -> Tuple[str, ...]:
        """Possible interaction verbs — explicit if provided, else inferred
        generically from object_type (no application-specific logic)."""
        if self.affordances:
            return self.affordances
        return _AFFORDANCE_BY_TYPE.get((self.object_type or "").lower(), ())
