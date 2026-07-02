"""Windows UI Automation monitor for continuous screen awareness."""

from __future__ import annotations

import platform
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Optional

try:
    import uiautomation as auto
except ImportError:  # pragma: no cover - optional dependency
    auto = None  # type: ignore

from ..types import EventType, ScreenEvent, UIElementSnapshot, WindowContext


class UIAutomationUnavailable(RuntimeError):
    """Raised when UI Automation is requested on unsupported systems."""


@dataclass(slots=True)
class UIAutomationConfig:
    """Configuration for polling frequency and tree depth."""

    polling_interval: float = 0.8
    max_depth: int = 12
    include_offscreen: bool = False


class UIAutomationMonitor:
    """Continuously tracks the foreground window using Windows UI Automation."""

    def __init__(
        self,
        *,
        config: UIAutomationConfig | None = None,
        event_callback: Callable[[ScreenEvent], None] | None = None,
    ) -> None:
        if platform.system() != "Windows" or auto is None:
            raise UIAutomationUnavailable(
                "Windows UI Automation requires the 'uiautomation' package on Windows."
            )

        self.config = config or UIAutomationConfig()
        self._callback = event_callback
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_window_handle: Optional[int] = None
        self._last_no_control_warning: float = 0.0
        self._last_no_root_warning: float = 0.0
        self._last_init_warning: float = 0.0
        self._last_com_warning: float = 0.0
        self._last_emit: float = 0.0

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
        def _loop() -> None:
            while not self._stop_event.is_set():
                try:
                    self._poll_foreground_window()
                except Exception as exc:  # pragma: no cover - defensive
                    msg = f"{type(exc).__name__}: {exc}"
                    low = msg.lower()
                    if "unable to invoke any of the" in low and "subbscribers" in low:
                        now = time.time()
                        if now - self._last_com_warning > 10.0:
                            self._emit_event(EventType.ERROR, {"message": msg})
                            self._last_com_warning = now
                        self._stop_event.wait(max(self.config.polling_interval, 1.5))
                        continue
                    self._emit_event(EventType.ERROR, {"message": msg})
                # RUNTIME STABILIZATION: Ensure minimum 200ms sleep to prevent CPU spikes
                sleep_time = max(0.2, self.config.polling_interval)
                self._stop_event.wait(sleep_time)

        initializer = getattr(auto, "UIAutomationInitializerInThread", None)
        ctx = None
        try:
            if callable(initializer):
                ctx = initializer()
        except Exception as exc:
            if time.time() - self._last_init_warning > 5.0:
                self._emit_event(EventType.ERROR, {"message": f"UIAutomationInitializerInThread failed: {type(exc).__name__}: {exc}"})
                self._last_init_warning = time.time()
            ctx = None

        if ctx is not None and hasattr(ctx, "__enter__") and hasattr(ctx, "__exit__"):
            try:
                with ctx:
                    _loop()
                return
            except Exception as exc:
                if time.time() - self._last_init_warning > 5.0:
                    self._emit_event(EventType.ERROR, {"message": f"UIAutomation thread init context failed: {type(exc).__name__}: {exc}"})
                    self._last_init_warning = time.time()

                try:
                    _loop()
                except Exception:
                    pass
                return

        _loop()

    def _poll_foreground_window(self) -> None:
        control = None
        try:
            fg = getattr(auto, "GetForegroundControl", None)
            if callable(fg):
                control = fg()
        except Exception:
            control = None
        if control is None:
            try:
                control = auto.GetFocusedControl()
            except Exception:
                control = None
        if control is None:
            if time.time() - self._last_no_control_warning > 3.0:
                self._emit_event(EventType.ERROR, {"message": "UI automation could not resolve a foreground/focused control."})
                self._last_no_control_warning = time.time()
            return

        root = None
        try:
            if hasattr(control, "GetTopLevelControl"):
                root = control.GetTopLevelControl()
            elif hasattr(control, "GetTopWindowControl"):
                root = control.GetTopWindowControl()
        except Exception:
            root = None
        if root is None:
            try:
                if getattr(control, "NativeWindowHandle", None) is not None:
                    root = control
            except Exception:
                root = None
        if root is None:
            root = control
        if root is None:
            if time.time() - self._last_no_root_warning > 3.0:
                self._emit_event(EventType.ERROR, {"message": "UI automation could not resolve a top-level control."})
                self._last_no_root_warning = time.time()
            return

        window_handle = getattr(root, "NativeWindowHandle", None)
        if window_handle != self._last_window_handle:
            self._emit_event(
                EventType.WINDOW_FOCUS_CHANGED,
                {
                    "handle": window_handle,
                    "name": getattr(root, "Name", None),
                    "class": getattr(root, "ClassName", None),
                },
            )
            self._last_window_handle = window_handle

        window_context = self._build_window_context(root)
        self._emit_event(EventType.UI_AUTOMATION_UPDATE, {"context": window_context})

    def _build_window_context(self, root: "auto.Control") -> WindowContext:
        elements = list(self._gather_elements(root, depth=self.config.max_depth))
        root_pid = getattr(root, "ProcessId", None)
        root_handle = getattr(root, "NativeWindowHandle", None)
        if root_pid:
            try:
                desktop = auto.GetRootControl()
            except Exception:
                desktop = None
            if desktop is not None:
                try:
                    children = list(desktop.GetChildren())
                except Exception:
                    children = []
                for top in children:
                    if top is None:
                        continue
                    try:
                        if getattr(top, "ProcessId", None) != root_pid:
                            continue
                        if getattr(top, "NativeWindowHandle", None) == root_handle:
                            continue
                    except Exception:
                        continue

                    rect = self._safe_rect(getattr(top, "BoundingRectangle", None))
                    if not rect:
                        continue
                    if rect[2] <= rect[0] or rect[3] <= rect[1]:
                        continue

                    extra_depth = min(self.config.max_depth, 6)
                    elements.extend(list(self._gather_elements(top, depth=extra_depth)))
        return WindowContext(
            title=getattr(root, "Name", None),
            app_exe=getattr(root, "ProcessName", None),
            handle=getattr(root, "NativeWindowHandle", None),
            process_id=getattr(root, "ProcessId", None),
            elements=elements,
            timestamp=time.time(),
        )

    def _gather_elements(
        self,
        control: "auto.Control",
        depth: int,
    ) -> Iterable[UIElementSnapshot]:
        if depth < 0:
            return []

        snapshot = UIElementSnapshot(
            name=getattr(control, "Name", None),
            control_type=getattr(control, "ControlTypeName", None),
            automation_id=getattr(control, "AutomationId", None),
            bounding_rect=self._safe_rect(getattr(control, "BoundingRectangle", None)),
            value=getattr(control, "Value", None),
            enabled=getattr(control, "IsEnabled", None),
            focused=getattr(control, "IsFocused", None),
            states=self._extract_states(control),
        )
        yield snapshot

        if depth == 0:
            return

        for child in control.GetChildren():
            if self.config.include_offscreen:
                yield from self._gather_elements(child, depth - 1)
                continue

            try:
                if not child.IsOffscreen:
                    yield from self._gather_elements(child, depth - 1)
                    continue
            except Exception:
                pass

            rect = self._safe_rect(getattr(child, "BoundingRectangle", None))
            if rect and rect[2] > rect[0] and rect[3] > rect[1]:
                yield from self._gather_elements(child, depth - 1)

    @staticmethod
    def _safe_rect(rect) -> Optional[tuple[int, int, int, int]]:
        if rect is None:
            return None
        try:
            return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        except Exception:
            return None

    @staticmethod
    def _extract_states(control: "auto.Control") -> Dict[str, bool]:
        states: Dict[str, bool] = {}
        for attr in ("IsOffscreen", "IsEnabled", "IsVisible", "IsSelected"):
            value = getattr(control, attr, None)
            if value is not None:
                states[attr] = bool(value)
        return states

    def _emit_event(self, event_type: EventType, payload: Dict[str, object]) -> None:
        if not self._callback:
            return
        
        # RUNTIME STABILIZATION: Throttle UIA events to 400ms minimum
        now = time.time()
        if now - self._last_emit < 0.4:
            return
        self._last_emit = now
        
        # COM ERROR CRASH GUARD: Wrap callback to prevent training crashes
        try:
            event = ScreenEvent(
                event_type=event_type,
                source="ui_automation",
                payload=payload,
                timestamp=now,
            )
            self._callback(event)
        except Exception:
            # Silently ignore callback errors to prevent crashes
            # Training mode must never crash due to UI Automation errors
            return
