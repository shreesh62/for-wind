"""Ch 21 — Event System: append-only EventStore with replay and checkpoints.

Storage is a JSON-lines file: one deterministic-serialized Event per line.
Checkpoints are JSON files pairing arbitrary state with a logical time.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

from friday.events.event import Event


class EventStore:
    """Append-only durable event log."""

    def __init__(self, path: str) -> None:
        self._path = Path(os.path.expanduser(path))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._append_count = 0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def append_count(self) -> int:
        with self._lock:
            return self._append_count

    def append(self, event: Event) -> None:
        line = json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":"))
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            self._append_count += 1

    def replay(self, from_logical_time: int = 0) -> Iterator[Event]:
        """Yield stored events with logical_time > from_logical_time, in order."""
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                event = Event.from_dict(json.loads(raw))
                if event.logical_time > from_logical_time:
                    yield event

    def checkpoint(self, state: Dict[str, Any], at_logical_time: int) -> str:
        """Persist a state snapshot; returns the checkpoint file path."""
        checkpoint_path = self._path.with_suffix(
            f".checkpoint.{at_logical_time}.{int(time.time() * 1000)}.json"
        )
        payload = {"logical_time": at_logical_time, "state": state}
        with self._lock:
            checkpoint_path.write_text(
                json.dumps(payload, sort_keys=True), encoding="utf-8"
            )
        return str(checkpoint_path)

    def load_checkpoint(self, path: str) -> Tuple[Dict[str, Any], int]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return payload["state"], int(payload["logical_time"])

    def replay_from_checkpoint(
        self, checkpoint_path: str
    ) -> Tuple[Dict[str, Any], Iterator[Event]]:
        state, logical_time = self.load_checkpoint(checkpoint_path)
        return state, self.replay(from_logical_time=logical_time)

    def latest_checkpoint(self) -> Optional[str]:
        checkpoints = sorted(
            self._path.parent.glob(self._path.stem + ".checkpoint.*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        return str(checkpoints[-1]) if checkpoints else None
