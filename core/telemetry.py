"""Lightweight telemetry logger for Jarvis."""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, List, Optional


class TelemetryLogger:
    """Collects structured events and optionally persists them."""

    def __init__(self, buffer_size: int = 200, file_path: Optional[str] = None) -> None:
        self._events: Deque[dict] = deque(maxlen=buffer_size)
        self._counts: Dict[str, int] = defaultdict(int)
        self._file_path = Path(file_path) if file_path else None
        if self._file_path:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event_type: str, payload: Optional[dict] = None) -> None:
        entry = {
            "type": event_type,
            "timestamp": time.time(),
            "payload": payload or {},
        }
        self._events.appendleft(entry)
        self._counts[event_type] += 1
        if self._file_path:
            with self._file_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")

    def snapshot(self, limit: int = 10) -> dict:
        return {
            "counts": dict(self._counts),
            "recent": list(self._events)[:limit],
        }

    def recent_events(self, limit: int = 10) -> List[dict]:
        return list(self._events)[:limit]
