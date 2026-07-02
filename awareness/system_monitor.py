"""System monitoring utilities for Jarvis."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Optional

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore


@dataclass
class SystemSnapshot:
    cpu_percent: Optional[float]
    memory_percent: Optional[float]
    battery_percent: Optional[float]
    power_plugged: Optional[bool]

    def describe(self) -> str:
        segments = []
        if self.cpu_percent is not None:
            segments.append(f"CPU {self.cpu_percent:.0f}%")
        if self.memory_percent is not None:
            segments.append(f"RAM {self.memory_percent:.0f}%")
        if self.battery_percent is not None:
            batt = f"Battery {self.battery_percent:.0f}%"
            if self.power_plugged is not None:
                batt += " (plugged)" if self.power_plugged else " (on battery)"
            segments.append(batt)
        if not segments:
            return "System telemetry unavailable."
        return ", ".join(segments)

    def as_dict(self) -> dict:
        return {
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "battery_percent": self.battery_percent,
            "power_plugged": self.power_plugged,
            "description": self.describe(),
        }


class SystemMonitor:
    """Provides lightweight system metrics for prompt context and plugins."""

    def __init__(self) -> None:
        self.platform = platform.system()

    def snapshot(self) -> SystemSnapshot:
        if psutil is None:
            return SystemSnapshot(None, None, None, None)

        cpu_percent = psutil.cpu_percent(interval=0.2)
        memory = psutil.virtual_memory()
        battery_info = None
        if hasattr(psutil, "sensors_battery"):
            try:
                battery_info = psutil.sensors_battery()
            except Exception:  # pragma: no cover
                battery_info = None

        return SystemSnapshot(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent if memory else None,
            battery_percent=battery_info.percent if battery_info else None,
            power_plugged=battery_info.power_plugged if battery_info else None,
        )
