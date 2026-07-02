"""Sample status monitor plugin."""

from __future__ import annotations

from typing import Optional

from core.capability_dispatcher import DispatchContext
from awareness.system_monitor import SystemMonitor


def handle_system_status(context: DispatchContext, capability: dict) -> str:
    del capability  # unused
    monitor = SystemMonitor()
    snapshot = monitor.snapshot()
    return snapshot.describe()
