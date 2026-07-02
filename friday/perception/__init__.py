"""Perception layer - unified world state from multiple sources.

Sources:
- Screen capture (MSS)
- OCR (Tesseract)
- Vision (CLIP / multimodal models)
- Desktop understanding (Windows UI Automation)
- Browser understanding (DevTools / Playwright)

Output: WorldState object - single source of perception truth.
"""

from friday.perception.world_state import WorldState, WorldStateBuilder
from friday.perception.types import (
    UIElement,
    OCRRegion,
    BrowserElement,
    ScreenRegion,
    PerceptionSource,
)
from friday.perception.priority import (
    PerceptionResolver,
    ResolvedElement,
    SourcePriority,
)
from friday.perception.vision import VisionPerception, VisionAnalysis

__all__ = [
    "WorldState",
    "WorldStateBuilder",
    "UIElement",
    "OCRRegion",
    "BrowserElement",
    "ScreenRegion",
    "PerceptionSource",
    "PerceptionResolver",
    "ResolvedElement",
    "SourcePriority",
    "VisionPerception",
    "VisionAnalysis",
]
