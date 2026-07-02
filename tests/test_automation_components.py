from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from automation import browser_state_tracker as bst_module
from automation import devtools_bridge as bridge_module
from automation.browser_state_tracker import BrowserStateTracker
from awareness.event_dispatcher import EventDispatcher
from awareness.types import EventType


def test_devtools_bridge_summarize_collects_data() -> None:
    bridge = object.__new__(bridge_module.DevToolsBridge)

    async def fake_send(payload: Dict[str, Any]) -> Dict[str, Any]:
        method = payload["method"]
        if method == "Page.getNavigationHistory":
            return {
                "result": {
                    "currentIndex": 0,
                    "entries": [
                        {
                            "url": "https://example.com",
                            "title": "Example",
                        }
                    ],
                }
            }
        if method == "Performance.getMetrics":
            return {
                "result": {
                    "metrics": [
                        {
                            "name": "TaskDuration",
                            "value": 1.23,
                        }
                    ]
                }
            }
        if method == "DOM.getDocument":
            return {
                "result": {
                    "root": {
                        "nodeId": 42,
                    }
                }
            }
        if method == "DOM.getOuterHTML":
            return {
                "result": {
                    "outerHTML": "<html></html>",
                }
            }
        raise AssertionError(f"Unexpected method {method}")

    bridge._send = fake_send  # type: ignore[attr-defined]

    summary = asyncio.run(bridge_module.DevToolsBridge.summarize(bridge, include_dom=True))  # type: ignore[arg-type]

    assert summary["url"] == "https://example.com"
    assert summary["title"] == "Example"
    assert summary["metrics"] == [{"name": "TaskDuration", "value": 1.23}]
    assert summary["dom"] == "<html></html>"


def test_devtools_bridge_connect_picks_best_target(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyManager:
        remote_debug_port = 9222
        auto_launch = False

    bridge = bridge_module.DevToolsBridge(DummyManager())

    async def fake_list_targets() -> list[dict[str, Any]]:
        return [
            {
                "type": "page",
                "url": "about:blank",
                "title": "New Tab",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/blank",
            },
            {
                "type": "page",
                "url": "https://example.com/",
                "title": "Example Domain",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/example",
            },
            {
                "type": "background_page",
                "url": "chrome-extension://abc123/",
                "title": "Extension",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/ext",
            },
        ]

    chosen: dict[str, Any] = {}

    async def fake_ws_connect(url: str, *args: Any, **kwargs: Any) -> Any:
        chosen["url"] = url

        class DummySocket:
            async def close(self) -> None:
                return None

        return DummySocket()

    monkeypatch.setattr(bridge, "_list_targets", fake_list_targets)
    monkeypatch.setattr(bridge_module.websockets, "connect", fake_ws_connect)

    asyncio.run(bridge.connect())

    assert chosen["url"] == "ws://127.0.0.1:9222/devtools/page/example"


def test_browser_state_tracker_emits_events(monkeypatch: pytest.MonkeyPatch) -> None:
    events = []
    dispatcher = EventDispatcher()
    dispatcher.subscribe(events.append)

    class DummyManager:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - simple stub
            pass

    class DummyBridge:
        summaries: list[dict[str, Any]] = []

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "DummyBridge":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def summarize(self) -> dict[str, Any]:
            return self.summaries.pop(0) if self.summaries else {}

    monkeypatch.setattr(bst_module, "PlaywrightManager", DummyManager)
    monkeypatch.setattr(bst_module, "DevToolsBridge", DummyBridge)

    tracker = BrowserStateTracker(dispatcher)

    DummyBridge.summaries = [
        {"url": "https://example.com", "title": "Example"},
        {"url": "https://another.example", "title": "Example 2"},
    ]

    asyncio.run(tracker._poll_once())
    asyncio.run(tracker._poll_once())

    assert len(events) == 2
    assert events[0].event_type == EventType.BROWSER_DOM_UPDATE
    assert events[1].event_type == EventType.BROWSER_NAVIGATION
    assert events[1].payload["summary"]["url"] == "https://another.example"

    # Ensure third call with no summary emits nothing new
    asyncio.run(tracker._poll_once())
    assert len(events) == 2
