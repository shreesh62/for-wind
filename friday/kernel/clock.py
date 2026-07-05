"""Ch 20 — Cognitive Kernel: Lamport logical clock paired with wall time."""

from __future__ import annotations

import threading
import time
from typing import Dict, Tuple


class CognitiveClock:
    """Monotonic logical clock (Lamport) with wall-time pairing."""

    def __init__(self, initial: int = 0) -> None:
        self._lock = threading.RLock()
        self._t = int(initial)

    def tick(self) -> int:
        with self._lock:
            self._t += 1
            return self._t

    def now(self) -> Tuple[int, float]:
        with self._lock:
            return self._t, time.time()

    def update(self, received: int) -> int:
        """Lamport merge with a logical time received from elsewhere."""
        with self._lock:
            self._t = max(self._t, int(received)) + 1
            return self._t

    def serialize(self) -> Dict[str, float]:
        with self._lock:
            return {"logical": self._t, "wall": time.time()}

    def restore(self, state: Dict[str, float]) -> None:
        with self._lock:
            self._t = int(state["logical"])
