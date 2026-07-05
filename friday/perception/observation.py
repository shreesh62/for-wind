"""Ch 12 — Observation: the uniform record every sensor must produce."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Tuple

from friday.events.event import FrozenDict


@dataclass(frozen=True)
class Observation:
    """A single sensor reading, uniform across all sensors."""

    sensor: str  # "screen", "ocr", "dom", "uia", "clipboard", ...
    environment: str  # "browser", "desktop", "system"
    object_type: str  # "window", "button", "text", "url", ...
    attributes: FrozenDict = field(default_factory=FrozenDict)
    confidence: float = 1.0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    bbox: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h) if visual

    def object_key(self) -> str:
        """Stable identity of the observed object, used for fusion."""
        name = self.attributes.get("name") or self.attributes.get("text") or ""
        return f"{self.environment}:{self.object_type}:{name}"
