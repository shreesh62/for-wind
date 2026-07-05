"""Ch 20 — EchoRuntime: demo runtime proving plug-in isolation.

Imports ONLY from friday.events and friday.kernel.contracts. Zero
knowledge of the operator, executor, browser, or any other subsystem.
"""

from __future__ import annotations

from typing import Any, Dict, List

from friday.events.event import Event, make_event
from friday.kernel.contracts.runtime import RuntimeContract


class EchoRuntime(RuntimeContract):
    """Echoes ticks and responds to echo.request events."""

    def __init__(self) -> None:
        self._kernel: Any = None
        self._tick_count = 0
        self._echoed = 0
        self._alive = True

    @property
    def name(self) -> str:
        return "echo"

    def initialize(self, kernel: Any) -> None:
        self._kernel = kernel

    def tick(self, logical_time: int) -> None:
        self._tick_count += 1

    def observe(self) -> List[Dict[str, Any]]:
        return [{"runtime": self.name, "ticks": self._tick_count}]

    def receive(self, event: Event) -> None:
        if event.event_type == "echo.request":
            self._echoed += 1
            self.publish(
                make_event(
                    event_type="echo.response",
                    source=self.name,
                    logical_time=event.logical_time + 1,
                    payload={"echo": dict(event.payload)},
                    correlation_id=event.correlation_id,
                    parent_id=event.id,
                )
            )

    def publish(self, event: Event) -> None:
        if self._kernel is not None:
            self._kernel.publish_event(event)

    def checkpoint(self) -> Dict[str, Any]:
        return {"tick_count": self._tick_count, "echoed": self._echoed}

    def restore(self, state: Dict[str, Any]) -> None:
        self._tick_count = int(state.get("tick_count", 0))
        self._echoed = int(state.get("echoed", 0))

    def shutdown(self) -> None:
        self._alive = False

    def health(self) -> Dict[str, Any]:
        return {
            "status": "ok" if self._alive else "stopped",
            "ticks": self._tick_count,
            "echoed": self._echoed,
        }
