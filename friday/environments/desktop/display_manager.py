"""Ch 30 — multi-monitor geometry, DPI, and coordinate scaling.

The DisplayManager is the single source of truth for converting between
*logical* coordinates (as expressed by plans / targets) and *physical*
pixels (what the OS actually addresses). This is critical so the Motor
System lands clicks correctly under any DPI/scale — the same class of
device-pixel-ratio bug the browser viewport fix solved.

Under ``FRIDAY_DRY_RUN=1`` (or when ``win32`` is unavailable) monitor
enumeration is mocked: a single 1920x1080 primary monitor at scale 1.0 is
provided so the 854 existing tests stay green with no real OS access. A
monitor list may also be injected at construction for deterministic tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from friday.perception.types import BoundingBox


@dataclass(frozen=True)
class Monitor:
    """A single display device and its geometry.

    ``bounds`` and ``work_area`` are expressed in physical pixels;
    ``work_area`` excludes system chrome such as the taskbar.
    """

    index: int
    bounds: BoundingBox          # physical pixel bounds
    work_area: BoundingBox       # excludes taskbar
    dpi: int                     # e.g. 96, 120, 144
    scale: float                 # dpi / 96.0
    is_primary: bool


def _default_monitor() -> Monitor:
    """The mocked single 1920x1080 primary monitor used under DRY_RUN."""
    bounds = BoundingBox(x=0, y=0, width=1920, height=1080)
    # Reserve a nominal 40px taskbar at the bottom for the work area.
    work_area = BoundingBox(x=0, y=0, width=1920, height=1040)
    return Monitor(
        index=0,
        bounds=bounds,
        work_area=work_area,
        dpi=96,
        scale=1.0,
        is_primary=True,
    )


def _is_dry_run() -> bool:
    return os.environ.get("FRIDAY_DRY_RUN", "0") == "1"


class DisplayManager:
    """Ch 30 — multi-monitor, DPI, and coordinate scaling."""

    def __init__(self, monitors: Optional[List[Monitor]] = None) -> None:
        if monitors is not None:
            self._monitors: List[Monitor] = list(monitors)
        else:
            self._monitors = self._enumerate()

    # --- enumeration -----------------------------------------------------

    def _enumerate(self) -> List[Monitor]:
        """Enumerate physical monitors, falling back to a mock.

        Under DRY_RUN or when win32 is unavailable, returns a single default
        1920x1080 primary monitor at scale 1.0. Never raises.
        """
        if _is_dry_run():
            return [_default_monitor()]
        try:  # pragma: no cover - real OS path, not exercised under DRY_RUN
            import win32api  # type: ignore
            import win32con  # type: ignore

            monitors: List[Monitor] = []
            for idx, handle in enumerate(win32api.EnumDisplayMonitors()):
                info = win32api.GetMonitorInfo(handle[0])
                mx1, my1, mx2, my2 = info["Monitor"]
                wx1, wy1, wx2, wy2 = info["Work"]
                is_primary = bool(info["Flags"] & win32con.MONITORINFOF_PRIMARY)
                bounds = BoundingBox(
                    x=mx1, y=my1, width=mx2 - mx1, height=my2 - my1
                )
                work_area = BoundingBox(
                    x=wx1, y=wy1, width=wx2 - wx1, height=wy2 - wy1
                )
                monitors.append(
                    Monitor(
                        index=idx,
                        bounds=bounds,
                        work_area=work_area,
                        dpi=96,
                        scale=1.0,
                        is_primary=is_primary,
                    )
                )
            if monitors:
                return monitors
        except Exception:
            pass
        return [_default_monitor()]

    # --- queries ---------------------------------------------------------

    def monitors(self) -> List[Monitor]:
        """All known monitors."""
        return list(self._monitors)

    def primary(self) -> Monitor:
        """The primary monitor (first flagged primary, else the first one)."""
        for monitor in self._monitors:
            if monitor.is_primary:
                return monitor
        return self._monitors[0]

    def monitor_at(self, x: int, y: int) -> Optional[Monitor]:
        """Resolve the owning monitor for a physical point via bounds containment."""
        for monitor in self._monitors:
            if monitor.bounds.contains(x, y):
                return monitor
        return None

    # --- coordinate transforms -------------------------------------------

    def _resolve(self, x: int, y: int, monitor: Optional[Monitor]) -> Monitor:
        if monitor is not None:
            return monitor
        found = self.monitor_at(x, y)
        if found is not None:
            return found
        return self.primary()

    def to_physical(
        self, x: int, y: int, monitor: Optional[Monitor] = None
    ) -> Tuple[int, int]:
        """Convert a logical point to physical pixels.

        Scaling is applied relative to the owning monitor's origin: the
        offset from the monitor origin is multiplied by ``monitor.scale``.
        """
        mon = self._resolve(x, y, monitor)
        ox, oy = mon.bounds.x, mon.bounds.y
        px = ox + int(round((x - ox) * mon.scale))
        py = oy + int(round((y - oy) * mon.scale))
        return (px, py)

    def to_logical(
        self, x: int, y: int, monitor: Optional[Monitor] = None
    ) -> Tuple[int, int]:
        """Convert a physical point to logical coordinates.

        Inverse of :meth:`to_physical`: the offset from the monitor origin is
        divided by ``monitor.scale``. Round-trip
        ``to_logical(to_physical(x, y, m), m)`` equals ``(x, y)`` within ±1px.
        """
        mon = self._resolve(x, y, monitor)
        ox, oy = mon.bounds.x, mon.bounds.y
        lx = ox + int(round((x - ox) / mon.scale))
        ly = oy + int(round((y - oy) / mon.scale))
        return (lx, ly)
