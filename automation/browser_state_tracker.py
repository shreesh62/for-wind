"""Browser state tracker emitting awareness events via DevToolsBridge."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Optional

from awareness.types import EventType, ScreenEvent
from awareness.event_dispatcher import EventDispatcher

from .devtools_bridge import DevToolsBridge, DevToolsConnectionError
from .playwright_manager import PlaywrightManager


class BrowserStateTracker:
    """Polls Chrome via DevTools to emit navigation and DOM summaries."""

    def __init__(
        self,
        dispatcher: EventDispatcher,
        *,
        poll_interval: float = 2.0,
        remote_debug_port: int = 9222,
        use_chrome_profile: bool = True,
        chrome_profile: str = "Default",
        headless: bool = False,
        auto_launch: bool = False,
        state_cache: "object | None" = None,
    ) -> None:
        self.dispatcher = dispatcher
        self.poll_interval = poll_interval
        if not auto_launch:
            auto_launch = os.getenv("AUTO_LAUNCH_CHROME", "").strip().lower() in ("1", "true", "yes")
        self._manager = PlaywrightManager(
            "browser-tracker",
            headless=headless,
            use_chrome_profile=use_chrome_profile,
            chrome_profile=chrome_profile,
            remote_debug_port=remote_debug_port,
            auto_launch=auto_launch,
        )
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_summary: dict | None = None
        self._tick: int = 0
        self._state_cache = state_cache
        self._bridge: DevToolsBridge | None = None
        self._dom_every_n = max(1, int(os.getenv("BROWSER_TRACKER_DOM_EVERY_N", "6") or "6"))
        self._retry_delay = 2.0
        self._failure_start_time: Optional[float] = None
        self._suspended = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        try:
            if self._bridge is not None:
                try:
                    asyncio.run(self._bridge.close())
                except Exception:
                    pass
        finally:
            self._bridge = None
        try:
            if getattr(self, "_manager", None) is not None:
                self._manager.close()
        except Exception:
            pass

    def _thread_main(self) -> None:
        asyncio.run(self._run_loop())

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                # Check if suspended
                if self._suspended:
                    await asyncio.sleep(10.0)
                    continue
                
                await self._poll_once()
                
                # Reset on success
                self._retry_delay = 2.0
                self._failure_start_time = None
                
            except DevToolsConnectionError as exc:
                try:
                    if self._bridge is not None:
                        await self._bridge.close()
                except Exception:
                    pass
                self._bridge = None
                
                # Track failure duration
                if self._failure_start_time is None:
                    self._failure_start_time = time.time()
                
                failure_duration = time.time() - self._failure_start_time
                
                # Suspend if unreachable for 60s
                if failure_duration >= 60.0:
                    if not self._suspended:
                        self._suspended = True
                        self._emit_event(
                            EventType.ERROR,
                            {"message": "Browser tracker suspended: DevTools unreachable for 60s"},
                        )
                    try:
                        self._state_cache.update_browser(None)
                    except Exception:
                        pass
                    await asyncio.sleep(10.0)
                    continue
                
                # Exponential backoff (max 30s)
                self._retry_delay = min(30.0, self._retry_delay * 2)
                await asyncio.sleep(self._retry_delay)
                
                # Emit error (throttled)
                self._emit_event(
                    EventType.ERROR,
                    {"message": f"Browser tracker: {exc}"},
                )
                if self._state_cache:
                    try:
                        self._state_cache.update_browser_error(str(exc))
                    except Exception:
                        pass
                
            except Exception as exc:
                self._emit_event(
                    EventType.ERROR,
                    {"message": f"Browser tracker unexpected error: {exc}"},
                )
                await asyncio.sleep(self.poll_interval)

    async def _poll_once(self) -> None:
        if self._bridge is None:
            self._bridge = DevToolsBridge(self._manager)
            # Support test doubles that don't implement connect().
            connect = getattr(self._bridge, "connect", None)
            if callable(connect):
                await connect()
            else:
                enter = getattr(self._bridge, "__aenter__", None)
                if callable(enter):
                    await enter()

        # Include DOM snapshot only every N ticks to keep overhead low
        self._tick = (self._tick + 1) % self._dom_every_n
        include_dom = self._tick == 0

        try:
            summary = await self._bridge.summarize(include_dom=include_dom)
        except TypeError:
            summary = await self._bridge.summarize()

        # Derive simple hints from DOM when available
        hints: dict = {}
        dom: str | None = summary.get("dom") if summary else None
        if isinstance(dom, str) and dom:
            low = dom.lower()
            hints["has_login"] = any(k in low for k in ("signin", "sign in", "login", "log in"))
            hints["has_form"] = "<form" in low
            hints["has_consent"] = "consent" in low or "accept all" in low or "i agree" in low
            hints["has_error_modal"] = any(k in low for k in ("aria-role=dialog", "role=dialog", "modal"))
        if hints and isinstance(summary, dict):
            summary["hints"] = hints
        if not summary:
            return

        event_type = EventType.BROWSER_DOM_UPDATE
        if self._last_summary and summary.get("url") != self._last_summary.get("url"):
            event_type = EventType.BROWSER_NAVIGATION

        self._last_summary = summary
        self._emit_event(event_type, {"summary": summary})
        if self._state_cache:
            try:
                self._state_cache.update_browser_summary(summary)
            except Exception:
                pass

    def _emit_event(self, event_type: EventType, payload: dict) -> None:
        event = ScreenEvent(
            event_type=event_type,
            source="browser_tracker",
            payload=payload,
            timestamp=time.time(),
        )
        self.dispatcher.publish(event)
