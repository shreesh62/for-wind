"""Shared types and dataclasses for the awareness subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

BoundingRect = Tuple[int, int, int, int]


class EventType(str, Enum):
    """Enumeration of high-level awareness events."""

    WINDOW_FOCUS_CHANGED = "window_focus_changed"
    WINDOW_CLOSED = "window_closed"
    UI_AUTOMATION_UPDATE = "ui_automation_update"
    PROCESS_STARTED = "process_started"
    PROCESS_TERMINATED = "process_terminated"
    BROWSER_NAVIGATION = "browser_navigation"
    BROWSER_DOM_UPDATE = "browser_dom_update"
    SCREEN_CAPTURED = "screen_captured"
    ERROR = "error"


@dataclass(slots=True)
class UIElementSnapshot:
    """Lightweight representation of a UI element on screen."""

    name: Optional[str] = None
    control_type: Optional[str] = None
    automation_id: Optional[str] = None
    bounding_rect: Optional[BoundingRect] = None
    value: Optional[str] = None
    enabled: Optional[bool] = None
    focused: Optional[bool] = None
    states: Dict[str, bool] = field(default_factory=dict)


@dataclass(slots=True)
class ProcessSummary:
    """Minimal information about a running process."""

    pid: int
    name: Optional[str]
    exe: Optional[str]
    create_time: Optional[float] = None

    def as_dict(self) -> Dict[str, object]:
        return {
            "pid": self.pid,
            "name": self.name,
            "exe": self.exe,
            "create_time": self.create_time,
        }


@dataclass(slots=True)
class WindowContext:
    """Describes the current foreground window and its key elements."""

    title: Optional[str]
    app_exe: Optional[str]
    handle: Optional[int]
    process_id: Optional[int]
    elements: List[UIElementSnapshot] = field(default_factory=list)
    timestamp: float | None = None


@dataclass(slots=True)
class ScreenEvent:
    """Structured event emitted by awareness components."""

    event_type: EventType
    source: str
    payload: Dict[str, object] = field(default_factory=dict)
    timestamp: float | None = None
