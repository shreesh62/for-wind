from __future__ import annotations

from collections import deque
from typing import List

import pytest

from awareness.event_dispatcher import EventDispatcher
from awareness.state_cache import StateCache
from awareness.types import EventType, ProcessSummary, ScreenEvent, WindowContext


@pytest.fixture()
def dispatcher() -> EventDispatcher:
    return EventDispatcher()


def build_event(event_type: EventType, payload: dict | None = None) -> ScreenEvent:
    return ScreenEvent(event_type=event_type, source="test", payload=payload or {}, timestamp=123.0)


def test_event_dispatcher_global_and_specific_subscribers(dispatcher: EventDispatcher) -> None:
    global_events: List[ScreenEvent] = []
    focused_events: List[ScreenEvent] = []

    dispatcher.subscribe(global_events.append)
    dispatcher.subscribe(focused_events.append, [EventType.WINDOW_FOCUS_CHANGED])

    focus_event = build_event(EventType.WINDOW_FOCUS_CHANGED)
    browser_event = build_event(EventType.BROWSER_NAVIGATION)

    dispatcher.publish(focus_event)
    dispatcher.publish(browser_event)

    assert global_events == [focus_event, browser_event]
    assert focused_events == [focus_event]


def test_event_dispatcher_unsubscribe(dispatcher: EventDispatcher) -> None:
    events: deque[ScreenEvent] = deque()

    dispatcher.subscribe(events.append)
    dispatcher.unsubscribe(events.append)

    dispatcher.publish(build_event(EventType.ERROR))

    assert not events


def test_state_cache_updates_and_reads() -> None:
    cache = StateCache()

    window = WindowContext(title="Test", app_exe="app.exe", handle=123, process_id=456)
    cache.update_window(window)

    process = ProcessSummary(pid=99, name="python.exe", exe="python.exe")
    cache.update_process(process)

    event = build_event(EventType.BROWSER_NAVIGATION, {"url": "https://example.com"})
    cache.update_event(event)

    assert cache.get_window() == window
    assert cache.get_last_process() == process
    assert cache.get_last_event() == event
