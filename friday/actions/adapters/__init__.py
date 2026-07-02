"""Adapter layer — environment-specific execution backends for primitives."""

from friday.actions.adapters.base import AdapterProtocol
from friday.actions.adapters.browser import BrowserAdapter
from friday.actions.adapters.desktop import DesktopAdapter
from friday.actions.adapters.desktop_actions import DesktopActionsAdapter
from friday.actions.adapters.vision import VisionAdapter
from friday.actions.adapters.resolver import AdapterResolver

__all__ = [
    "AdapterProtocol",
    "BrowserAdapter",
    "DesktopAdapter",
    "DesktopActionsAdapter",
    "VisionAdapter",
    "AdapterResolver",
]
