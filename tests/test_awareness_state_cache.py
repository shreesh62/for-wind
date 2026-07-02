import asyncio

from types import SimpleNamespace


def test_browser_state_tracker_updates_state_cache(monkeypatch):
    # Lazy import to ensure module-level objects are patchable
    import automation.browser_state_tracker as bst

    class FakeBridge:
        def __init__(self, manager):
            self.manager = manager
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def summarize(self, include_dom: bool = False):
            # include DOM so hints are produced
            return {
                "url": "https://example.com",
                "title": "Example",
                "dom": "<html><form>Sign in</form><div role=dialog></div></html>",
            }

    # Patch DevToolsBridge used inside the tracker
    monkeypatch.setattr(bst, "DevToolsBridge", lambda manager: FakeBridge(manager))

    # Minimal dispatcher and state cache fakes
    events = []
    class DummyDispatcher:
        def publish(self, event):
            events.append(event)

    class DummyStateCache:
        def __init__(self):
            self.summary = None
            self.error = None
        def update_browser_summary(self, s: dict):
            self.summary = s
        def update_browser_error(self, e: str):
            self.error = e

    tracker = bst.BrowserStateTracker(
        dispatcher=DummyDispatcher(),
        headless=True,
        state_cache=DummyStateCache(),
    )

    # Run a single poll iteration
    asyncio.run(tracker._poll_once())

    # Verify state cache updated with summary and hints
    assert tracker._last_summary is not None
    assert isinstance(tracker._last_summary.get("url"), str)
    assert "hints" in tracker._last_summary
    assert tracker._last_summary["hints"].get("has_login") is True
    assert tracker._last_summary["hints"].get("has_form") is True
    # Ensure an event was emitted
    assert len(events) >= 1
