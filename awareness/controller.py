"""Coordinator for awareness monitors and shared state."""

from __future__ import annotations

from typing import Iterable, Optional

from .event_dispatcher import EventDispatcher, Subscriber
from .process_watcher import ProcessWatcher, ProcessWatcherConfig, ProcessWatcherUnavailable
from .state_cache import StateCache
from .types import EventType, ProcessSummary, ScreenEvent, WindowContext
from .windows.uia_monitor import UIAutomationMonitor, UIAutomationConfig, UIAutomationUnavailable


class AwarenessController:
    """Starts awareness monitors and maintains a state cache."""

    def __init__(
        self,
        *,
        ui_config: Optional[UIAutomationConfig] = None,
        process_config: Optional[ProcessWatcherConfig] = None,
        enable_ui_monitor: bool = True,
        enable_process_watcher: bool = True,
    ) -> None:
        self.dispatcher = EventDispatcher()
        self.state_cache = StateCache()

        self._ui_monitor: Optional[UIAutomationMonitor] = None
        self._process_watcher: Optional[ProcessWatcher] = None

        self._ui_config = ui_config or UIAutomationConfig()
        self._process_config = process_config or ProcessWatcherConfig()
        self._enable_ui = enable_ui_monitor
        self._enable_process = enable_process_watcher

    def start(self) -> None:
        """Start monitors and prime cache listener."""

        # Cache listener should always be active.
        self.dispatcher.subscribe(self._cache_listener)

        if self._enable_ui:
            try:
                self._ui_monitor = UIAutomationMonitor(
                    config=self._ui_config,
                    event_callback=self.dispatcher.publish,
                )
                self._ui_monitor.start()
                try:
                    print("[✅] UI automation monitor started")
                except Exception:
                    pass
            except UIAutomationUnavailable as exc:
                self._ui_monitor = None
                try:
                    print(f"[⚠️] UI automation monitor unavailable: {exc}")
                except Exception:
                    pass

        if self._enable_process:
            try:
                self._process_watcher = ProcessWatcher(
                    config=self._process_config,
                    event_callback=self.dispatcher.publish,
                )
                self._process_watcher.start()
            except ProcessWatcherUnavailable as exc:
                self._process_watcher = None
                try:
                    print(f"[⚠️] Process watcher unavailable: {exc}")
                except Exception:
                    pass

    def stop(self) -> None:
        if self._ui_monitor:
            self._ui_monitor.stop()
            self._ui_monitor = None
        if self._process_watcher:
            self._process_watcher.stop()
            self._process_watcher = None

    def subscribe(self, callback: Subscriber, event_types: Optional[Iterable[EventType]] = None) -> None:
        """Allow external observers to receive awareness events."""

        self.dispatcher.subscribe(callback, event_types)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _cache_listener(self, event: ScreenEvent) -> None:
        self.state_cache.update_event(event)

        if event.event_type == EventType.ERROR and event.source == "ui_automation":
            payload = event.payload if isinstance(event.payload, dict) else {}
            message = payload.get("message") if isinstance(payload, dict) else None
            if isinstance(message, str) and message:
                try:
                    print(f"[⚠️] UI automation error: {message}")
                except Exception:
                    pass

        if event.event_type == EventType.UI_AUTOMATION_UPDATE:
            context = event.payload.get("context") if isinstance(event.payload, dict) else None
            if isinstance(context, WindowContext):
                self.state_cache.update_window(context)
        elif event.event_type in (EventType.PROCESS_STARTED, EventType.PROCESS_TERMINATED):
            payload = event.payload if isinstance(event.payload, dict) else {}
            summary_payload = payload.get("process") if isinstance(payload, dict) else None
            pid = payload.get("pid") if isinstance(payload, dict) else None
            summary = self._build_process_summary(summary_payload, pid)
            if summary:
                self.state_cache.update_process(summary)
        elif event.event_type in (EventType.BROWSER_NAVIGATION, EventType.BROWSER_DOM_UPDATE):
            payload = event.payload if isinstance(event.payload, dict) else {}
            summary = payload.get("summary") if isinstance(payload, dict) else None
            if isinstance(summary, dict) and summary:
                self.state_cache.update_browser_summary(summary)
        elif event.event_type == EventType.ERROR and event.source == "browser_tracker":
            payload = event.payload if isinstance(event.payload, dict) else {}
            message = payload.get("message") if isinstance(payload, dict) else None
            if isinstance(message, str) and message:
                self.state_cache.update_browser_error(message)

    @staticmethod
    def _build_process_summary(data: Optional[dict], pid: Optional[int]) -> Optional[ProcessSummary]:
        if not data and pid is None:
            return None
        target = data or {}
        resolved_pid = target.get("pid", pid)
        if resolved_pid is None:
            return None
        try:
            resolved_pid = int(resolved_pid)
        except (TypeError, ValueError):
            return None
        return ProcessSummary(
            pid=resolved_pid,
            name=target.get("name"),
            exe=target.get("exe"),
            create_time=target.get("create_time"),
        )
