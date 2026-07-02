"""Simple event dispatcher that funnels awareness events to subscribers."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Callable, DefaultDict, Iterable

from .types import EventType, ScreenEvent

Subscriber = Callable[[ScreenEvent], None]


class EventDispatcher:
    """Thread-safe pub/sub dispatcher for awareness events."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: DefaultDict[EventType, list[Subscriber]] = defaultdict(list)
        self._global_subscribers: list[Subscriber] = []

    def subscribe(self, callback: Subscriber, event_types: Iterable[EventType] | None = None) -> None:
        with self._lock:
            if event_types is None:
                self._global_subscribers.append(callback)
            else:
                for event_type in event_types:
                    self._subscribers[event_type].append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        with self._lock:
            self._global_subscribers = [cb for cb in self._global_subscribers if cb != callback]
            for event_type, callbacks in self._subscribers.items():
                self._subscribers[event_type] = [cb for cb in callbacks if cb != callback]

    def publish(self, event: ScreenEvent) -> None:
        with self._lock:
            targets = list(self._global_subscribers)
            targets.extend(self._subscribers.get(event.event_type, []))
        for callback in targets:
            try:
                callback(event)
            except Exception:
                continue
