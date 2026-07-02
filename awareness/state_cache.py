"""Shared state cache for awareness data."""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Optional

from .types import ProcessSummary, ScreenEvent, WindowContext
from .snapshot import build_snapshot
from .world_state import WorldState, UIElement, OCRWord, BrowserElement

try:
    from .windows_accessibility import WindowsAccessibilityMonitor
except Exception:  # pragma: no cover
    WindowsAccessibilityMonitor = None  # type: ignore


class StateCache:
    """Thread-safe cache storing latest window context and process info."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._window_context: Optional[WindowContext] = None
        self._last_event: Optional[ScreenEvent] = None
        self._last_process: Optional[ProcessSummary] = None
        self._browser_summary: Optional[dict] = None
        self._browser_error: Optional[str] = None
        self._ocr_text: Optional[str] = None
        self._ocr_error: Optional[str] = None
        self._ocr_confidence: float | None = None
        self._ocr_word_boxes: list[dict[str, Any]] | None = None
        self._ocr_updated_at: float | None = None
        self._updated_at: float | None = None
        self._snapshot: dict | None = None
        self._win32_monitor = None

    def _get_win32_window_fallback_locked(self) -> dict | None:
        if self._window_context is not None:
            try:
                wc = self._window_context
                needs_pid = getattr(wc, "process_id", None) is None
                needs_proc = not (getattr(wc, "app_exe", None) or "").strip()
                needs_title = not (getattr(wc, "title", None) or "").strip()
                needs_bbox = True
                try:
                    for el in (getattr(wc, "elements", None) or []):
                        rect = getattr(el, "bounding_rect", None)
                        if rect:
                            needs_bbox = False
                            break
                except Exception:
                    needs_bbox = True

                if not (needs_pid or needs_proc or needs_title or needs_bbox):
                    return None
            except Exception:
                pass
        if WindowsAccessibilityMonitor is None:
            return None
        try:
            if self._win32_monitor is None:
                self._win32_monitor = WindowsAccessibilityMonitor()
        except Exception:
            return None
        try:
            snap = self._win32_monitor.get_foreground_window_snapshot()
        except Exception:
            snap = None
        if snap is None:
            return None
        try:
            title = (getattr(snap, "title", "") or "").strip() or None
            pid = getattr(snap, "pid", None)
            process = (getattr(snap, "process", "") or "").strip() or None
            bbox = getattr(snap, "bounding_rect", None)
            if not title and pid is None and not process and not bbox:
                return None
            return {"title": title, "pid": pid, "process": process, "bounding_rect": bbox}
        except Exception:
            return None

    def _rebuild_snapshot_locked(self, *, timestamp: float) -> None:
        win32_fallback = self._get_win32_window_fallback_locked()
        self._snapshot = build_snapshot(
            window=self._window_context,
            win32_window=win32_fallback,
            browser_summary=self._browser_summary,
            browser_error=self._browser_error,
            ocr_text=self._ocr_text,
            ocr_error=self._ocr_error,
            ocr_confidence=self._ocr_confidence,
            ocr_updated_at=self._ocr_updated_at,
            timestamp=timestamp,
            ocr_word_boxes=self._ocr_word_boxes,
        )

    def update_window(self, context: WindowContext) -> None:
        with self._lock:
            self._window_context = context
            now = time.time()
            self._updated_at = now
            self._rebuild_snapshot_locked(timestamp=now)

    def update_process(self, process: ProcessSummary) -> None:
        with self._lock:
            self._last_process = process
            now = time.time()
            self._updated_at = now
            self._rebuild_snapshot_locked(timestamp=now)

    def update_event(self, event: ScreenEvent) -> None:
        with self._lock:
            self._last_event = event
            now = time.time()
            self._updated_at = now
            self._rebuild_snapshot_locked(timestamp=now)

    def update_browser_summary(self, summary: dict) -> None:
        with self._lock:
            self._browser_summary = summary
            self._browser_error = None
            now = time.time()
            self._updated_at = now
            self._rebuild_snapshot_locked(timestamp=now)

    def update_browser_error(self, message: str) -> None:
        with self._lock:
            self._browser_error = message
            now = time.time()
            self._updated_at = now
            self._rebuild_snapshot_locked(timestamp=now)

    def update_ocr_result(
        self,
        text: str,
        confidence: float | None = None,
        *,
        word_boxes: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._lock:
            self._ocr_text = text
            self._ocr_error = None
            self._ocr_confidence = confidence
            self._ocr_word_boxes = word_boxes
            now = time.time()
            self._ocr_updated_at = now
            self._updated_at = now
            self._rebuild_snapshot_locked(timestamp=now)

    def update_ocr_error(
        self,
        message: str,
        confidence: float | None = None,
        *,
        word_boxes: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._lock:
            self._ocr_error = message
            self._ocr_text = None
            self._ocr_confidence = confidence
            self._ocr_word_boxes = word_boxes
            now = time.time()
            self._ocr_updated_at = now
            self._updated_at = now
            self._rebuild_snapshot_locked(timestamp=now)

    def get_snapshot(self) -> dict:
        with self._lock:
            snap = self._snapshot
            if not isinstance(snap, dict) or not snap:
                now = time.time()
                win32_fallback = self._get_win32_window_fallback_locked()
                snap = build_snapshot(
                    window=self._window_context,
                    win32_window=win32_fallback,
                    browser_summary=self._browser_summary,
                    browser_error=self._browser_error,
                    ocr_text=self._ocr_text,
                    ocr_error=self._ocr_error,
                    ocr_confidence=self._ocr_confidence,
                    ocr_updated_at=self._ocr_updated_at,
                    timestamp=now,
                    ocr_word_boxes=self._ocr_word_boxes,
                )

            result = copy.deepcopy(snap)
            meta = result.get("meta")
            if isinstance(meta, dict):
                now = time.time()
                ts = meta.get("timestamp")
                if isinstance(ts, (int, float)):
                    meta["poll_age_ms"] = int(max(0.0, (now - float(ts)) * 1000.0))
            return result

    def get_window(self) -> Optional[WindowContext]:
        with self._lock:
            return self._window_context

    def get_last_event(self) -> Optional[ScreenEvent]:
        with self._lock:
            return self._last_event

    def get_last_process(self) -> Optional[ProcessSummary]:
        with self._lock:
            return self._last_process

    def get_browser_summary(self) -> Optional[dict]:
        with self._lock:
            return self._browser_summary

    def get_browser_error(self) -> Optional[str]:
        with self._lock:
            return self._browser_error

    def get_ocr_text(self) -> Optional[str]:
        with self._lock:
            return self._ocr_text

    def get_ocr_error(self) -> Optional[str]:
        with self._lock:
            return self._ocr_error

    def get_ocr_confidence(self) -> float | None:
        with self._lock:
            return self._ocr_confidence

    def ocr_last_updated(self) -> float | None:
        with self._lock:
            return self._ocr_updated_at

    def last_updated(self) -> float | None:
        with self._lock:
            return self._updated_at

    def build_world_state(self) -> WorldState:
        """Build a complete WorldState from all cached perception data.
        
        This is the authoritative method for constructing the unified world model.
        All perception sources (UIA, OCR, browser, window) are merged here.
        """
        with self._lock:
            import time
            
            # Desktop perception
            active_window_title = ""
            active_app = ""
            cursor_position = (0, 0)
            focused_element = None
            ui_elements = []
            
            if self._window_context:
                active_window_title = self._window_context.title or ""
                active_app = self._window_context.app_exe or ""
                
                # Convert WindowContext elements to UIElement
                for elem in (self._window_context.elements or []):
                    if not elem:
                        continue
                    ui_elem = UIElement(
                        text=elem.name or "",
                        control_type=elem.control_type or "Unknown",
                        bounding_box=elem.bounding_rect or (0, 0, 0, 0),
                        focused=elem.focused or False,
                        enabled=True,  # UIA doesn't always provide this
                        confidence=0.95,  # High confidence for UIA data
                    )
                    ui_elements.append(ui_elem)
                    
                    if elem.focused:
                        focused_element = ui_elem
            
            # Fallback: try Win32 monitor if window context is incomplete
            if not active_window_title or not active_app:
                win32_fallback = self._get_win32_window_fallback_locked()
                if win32_fallback:
                    active_window_title = win32_fallback.get("title") or active_window_title
                    active_app = win32_fallback.get("process") or active_app
            
            # Visual perception (OCR)
            ocr_words = []
            if self._ocr_word_boxes:
                for box_dict in self._ocr_word_boxes:
                    if not isinstance(box_dict, dict):
                        continue
                    text = box_dict.get("text", "")
                    bbox = box_dict.get("bounding_rect")
                    conf = box_dict.get("confidence", 0.0)
                    
                    if text and bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                        ocr_words.append(OCRWord(
                            text=text,
                            bbox=tuple(bbox),
                            confidence=float(conf) if conf else 0.0,
                        ))
            
            # Screenshot hash (for change detection)
            screenshot_hash = ""
            try:
                if self._snapshot and isinstance(self._snapshot, dict):
                    meta = self._snapshot.get("meta", {})
                    if isinstance(meta, dict):
                        screenshot_hash = str(meta.get("screenshot_hash", ""))
            except Exception:
                pass
            
            # Browser perception
            browser_open = False
            browser_url = None
            browser_title = None
            browser_elements = []
            
            if self._browser_summary and isinstance(self._browser_summary, dict):
                browser_open = True
                browser_url = self._browser_summary.get("url")
                browser_title = self._browser_summary.get("title")
                
                # Parse DOM if available (simplified - real implementation would parse HTML)
                dom = self._browser_summary.get("dom")
                if isinstance(dom, str) and dom:
                    # Extract clickable elements from DOM hints
                    # This is a placeholder - real implementation would parse DOM properly
                    hints = self._browser_summary.get("hints", {})
                    if isinstance(hints, dict):
                        if hints.get("has_login"):
                            browser_elements.append(BrowserElement(
                                tag="button",
                                text="Login",
                                role="button",
                                clickable=True,
                            ))
                        if hints.get("has_form"):
                            browser_elements.append(BrowserElement(
                                tag="form",
                                text="Form",
                                role="form",
                                clickable=False,
                            ))
            
            # Cursor position (would need to be tracked separately)
            try:
                import pyautogui
                cursor_position = pyautogui.position()
            except Exception:
                cursor_position = (0, 0)
            
            # Build WorldState
            world = WorldState(
                timestamp=time.time(),
                active_window_title=active_window_title,
                active_app=active_app,
                cursor_position=cursor_position,
                focused_element=focused_element,
                ui_elements=ui_elements,
                screenshot_hash=screenshot_hash,
                ocr_words=ocr_words,
                browser_open=browser_open,
                browser_url=browser_url,
                browser_title=browser_title,
                browser_elements=browser_elements,
            )
            
            return world
