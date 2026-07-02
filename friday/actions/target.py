from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Target:
    """Semantic description of what a primitive acts on.

    Callers describe WHAT, not WHERE. The resolver uses these
    fields in priority order to find the element.
    """

    text: str = ""                          # Visible text / label
    role: str = ""                          # ARIA role or UIA control type
    selector: str = ""                      # CSS selector (browser only)
    automation_id: str = ""                 # UIA AutomationId (desktop only)
    window_title: str = ""                  # For switch_window
    coordinates: Optional[Tuple[int, int]] = None  # Absolute fallback (x, y)
    index: int = 0                          # Disambiguation: nth match

    def __post_init__(self):
        if not any([self.text, self.role, self.selector,
                    self.automation_id, self.window_title,
                    self.coordinates]):
            raise ValueError("Target must have at least one identifying field")

    @property
    def has_semantic_hint(self) -> bool:
        """Whether the target has any semantic (non-coordinate) identifier."""
        return bool(self.text or self.role or self.selector or self.automation_id)
