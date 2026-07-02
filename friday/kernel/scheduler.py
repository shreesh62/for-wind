"""Ch 17/20 — CognitiveScheduler: adaptive tick loop in a daemon thread."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)


class CognitiveScheduler:
    """Runs a tick callback continuously in a daemon thread.

    The interval adapts: it shrinks while work is happening and grows
    (up to max_interval) while idle, so an idle kernel is cheap.
    """

    def __init__(
        self,
        on_tick: Callable[[], bool],
        min_interval: float = 0.005,
        max_interval: float = 0.25,
    ) -> None:
        self._on_tick = on_tick
        self._min_interval = min_interval
        self._max_interval = max_interval
        self._interval = min_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tick_errors = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def tick_errors(self) -> int:
        return self._tick_errors

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="friday-kernel-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                had_work = self._on_tick()
            except Exception:  # noqa: BLE001 - the loop must survive tick failures
                self._tick_errors += 1
                logger.exception("Kernel tick failed")
                had_work = False
            if had_work:
                self._interval = self._min_interval
            else:
                self._interval = min(self._interval * 1.5, self._max_interval)
            self._stop.wait(self._interval)
