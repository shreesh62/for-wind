"""Ch 17/20 — CheckpointManager: save/restore kernel state via the EventStore."""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional, Tuple

from friday.events.store import EventStore


class CheckpointManager:
    """Coordinates state snapshots against the append-only event log."""

    def __init__(
        self,
        store: EventStore,
        state_provider: Callable[[], Dict[str, Any]],
        auto_checkpoint_every: int = 0,
    ) -> None:
        self._store = store
        self._state_provider = state_provider
        self._auto_every = auto_checkpoint_every
        self._lock = threading.RLock()
        self._events_since_checkpoint = 0
        self._last_checkpoint_path: Optional[str] = None

    @property
    def last_checkpoint_path(self) -> Optional[str]:
        with self._lock:
            return self._last_checkpoint_path

    def save(self, at_logical_time: int) -> str:
        with self._lock:
            path = self._store.checkpoint(self._state_provider(), at_logical_time)
            self._last_checkpoint_path = path
            self._events_since_checkpoint = 0
            return path

    def load(self, path: str) -> Tuple[Dict[str, Any], int]:
        return self._store.load_checkpoint(path)

    def notify_event(self, at_logical_time: int) -> Optional[str]:
        """Record an event; auto-checkpoint when the threshold is reached."""
        with self._lock:
            self._events_since_checkpoint += 1
            if self._auto_every and self._events_since_checkpoint >= self._auto_every:
                return self.save(at_logical_time)
        return None
