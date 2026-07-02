"""Core perception types used across the perception layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class PerceptionSource(str, Enum):
    """Identifies the source of a perception signal."""

    UIA = "uia"
    OCR = "ocr"
    VISION = "vision"
    BROWSER = "browser"
    SCREEN = "screen"
    PROCESS = "process"


@dataclass(frozen=True)
class BoundingBox:
    """Screen-space bounding box (x, y, width, height)."""

    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def area(self) -> int:
        return self.width * self.height

    def contains(self, px: int, py: int) -> bool:
        return (self.x <= px < self.x + self.width and
                self.y <= py < self.y + self.height)

    def overlaps(self, other: "BoundingBox") -> bool:
        return not (
            self.x + self.width <= other.x or
            other.x + other.width <= self.x or
            self.y + self.height <= other.y or
            other.y + other.height <= self.y
        )


@dataclass
class UIElement:
    """A UI element detected via Windows UI Automation."""

    text: str
    control_type: str
    bbox: BoundingBox
    focused: bool = False
    enabled: bool = True
    automation_id: str = ""
    class_name: str = ""
    confidence: float = 1.0
    source: PerceptionSource = PerceptionSource.UIA


@dataclass
class OCRRegion:
    """A text region detected via OCR."""

    text: str
    bbox: BoundingBox
    confidence: float
    language: str = "en"
    source: PerceptionSource = PerceptionSource.OCR


@dataclass
class BrowserElement:
    """A DOM element in the active browser tab."""

    tag: str
    text: str
    role: str
    clickable: bool
    visible: bool = True
    bbox: Optional[BoundingBox] = None
    attributes: dict = field(default_factory=dict)
    selector: str = ""
    source: PerceptionSource = PerceptionSource.BROWSER


@dataclass
class ScreenRegion:
    """A region of interest on the screen."""

    bbox: BoundingBox
    pixel_hash: str = ""
    description: str = ""
    source: PerceptionSource = PerceptionSource.SCREEN


@dataclass
class WindowInfo:
    """Information about the active/focused window."""

    title: str
    process_name: str
    pid: int
    class_name: str = ""
    handle: int = 0
    is_foreground: bool = True
    source: PerceptionSource = PerceptionSource.PROCESS
