"""Ch 21 — Event System: thread-safe publish/subscribe bus.

Subscriptions use fnmatch patterns, e.g. "goal.*" matches "goal.created".
Handlers are invoked synchronously in the publishing thread; a failing
handler never prevents other handlers from running.
"""

from __future__ import annotations

import fnmatch
import logging
import threading
import uuid
from typing import Callable, Dict, List, Tuple

from friday.events.event import Event

logger = logging.getLogger(__name__)

Handler = Callable[[Event], None]


class EventBus:
    """Thread-safe pattern-matching event bus."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: Dict[str, Tuple[str, Handler]] = {}
        self._error_count = 0

    def subscribe(self, pattern: str, handler: Handler) -> str:
        subscription_id = str(uuid.uuid4())
        with self._lock:
            self._subscriptions[subscription_id] = (pattern, handler)
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        with self._lock:
            return self._subscriptions.pop(subscription_id, None) is not None

    def route(self, event: Event) -> List[Handler]:
        """Return handlers whose pattern matches the event type."""
        with self._lock:
            return [
                handler
                for pattern, handler in self._subscriptions.values()
                if fnmatch.fnmatch(event.event_type, pattern)
            ]

    def publish(self, event: Event) -> int:
        """Deliver the event to all matching handlers. Returns delivery count."""
        delivered = 0
        for handler in self.route(event):
            try:
                handler(event)
                delivered += 1
            except Exception:  # noqa: BLE001 - a bad handler must not break the bus
                with self._lock:
                    self._error_count += 1
                logger.exception("Event handler failed for %s", event.event_type)
        return delivered

    @property
    def subscription_count(self) -> int:
        with self._lock:
            return len(self._subscriptions)

    @property
    def error_count(self) -> int:
        with self._lock:
            return self._error_count
