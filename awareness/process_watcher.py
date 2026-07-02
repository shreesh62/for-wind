"""Process watcher emitting awareness events for process lifecycle changes."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    psutil = None  # type: ignore

from .types import EventType, ProcessSummary, ScreenEvent


class ProcessWatcherUnavailable(RuntimeError):
    """Raised when psutil is unavailable for process monitoring."""


@dataclass(slots=True)
class ProcessWatcherConfig:
    polling_interval: float = 2.0
    track_exe: bool = True
    track_create_time: bool = True


class ProcessWatcher:
    """Background watcher that reports process start/termination events."""

    def __init__(
        self,
        *,
        config: ProcessWatcherConfig | None = None,
        event_callback: Callable[[ScreenEvent], None] | None = None,
    ) -> None:
        if psutil is None:
            raise ProcessWatcherUnavailable("psutil is required for process watching.")

        self.config = config or ProcessWatcherConfig()
        self._callback = event_callback
        self._known: Dict[int, ProcessSummary] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll_processes()
            except Exception as exc:  # pragma: no cover
                self._emit_event(EventType.ERROR, {"message": str(exc)})
            # RUNTIME STABILIZATION: Ensure minimum 200ms sleep to prevent CPU spikes
            sleep_time = max(0.2, self.config.polling_interval)
            self._stop_event.wait(sleep_time)

    def _poll_processes(self) -> None:
        current: Dict[int, ProcessSummary] = {}
        attrs = ["pid", "name"]
        if self.config.track_exe:
            attrs.append("exe")
        if self.config.track_create_time:
            attrs.append("create_time")

        for proc in psutil.process_iter(attrs):  # type: ignore[arg-type]
            try:
                info = proc.info  # type: ignore[attr-defined]
                summary = ProcessSummary(
                    pid=info.get("pid"),
                    name=info.get("name"),
                    exe=info.get("exe"),
                    create_time=info.get("create_time"),
                )
                if summary.pid is None:
                    continue
                current[summary.pid] = summary
                if summary.pid not in self._known:
                    self._emit_event(EventType.PROCESS_STARTED, {"process": summary.as_dict()})
            except (psutil.NoSuchProcess, psutil.AccessDenied):  # pragma: no cover
                continue

        terminated = set(self._known.keys()) - set(current.keys())
        for pid in terminated:
            summary = self._known.get(pid)
            payload = {"pid": pid}
            if summary:
                payload["process"] = summary.as_dict()
            self._emit_event(EventType.PROCESS_TERMINATED, payload)

        self._known = current

    def _emit_event(self, event_type: EventType, payload: Dict[str, object]) -> None:
        if not self._callback:
            return
        event = ScreenEvent(
            event_type=event_type,
            source="process_watcher",
            payload=payload,
            timestamp=time.time(),
        )
        self._callback(event)
