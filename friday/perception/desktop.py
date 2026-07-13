"""Desktop perception adapter — bridges Windows UIA to FRIDAY types.

Connects the existing awareness/state_cache and awareness/windows/uia_monitor
to the new WorldStateBuilder by converting their outputs to UIElement and
WindowInfo objects.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from friday.perception.types import BoundingBox, UIElement, WindowInfo, PerceptionSource


class DesktopPerception:
    """Adapts Windows desktop state into FRIDAY perception types.

    This bridges the existing awareness subsystem (state_cache, UIA monitor)
    to the new WorldState architecture without rewriting the working code.

    Usage:
        perception = DesktopPerception(state_cache=awareness_controller.state_cache)
        window = perception.get_active_window()
        elements = perception.get_ui_elements()
        cursor = perception.get_cursor_position()
    """

    def __init__(self, state_cache=None) -> None:
        """Initialize with optional state cache from awareness controller.

        Args:
            state_cache: The existing awareness.state_cache.StateCache instance
        """
        self._state_cache = state_cache

    @property
    def available(self) -> bool:
        """Whether desktop perception is available."""
        return self._state_cache is not None

    def get_active_window(self) -> Optional[WindowInfo]:
        """Get the currently active/foreground window.

        Returns:
            WindowInfo or None if unavailable
        """
        if not self._state_cache:
            return self._get_window_fallback()

        try:
            context = self._state_cache.get_window()
            if not context:
                return self._get_window_fallback()

            return WindowInfo(
                title=getattr(context, 'title', '') or '',
                process_name=getattr(context, 'app_exe', '') or '',
                pid=getattr(context, 'pid', 0) or 0,
                class_name=getattr(context, 'class_name', '') or '',
                handle=getattr(context, 'handle', 0) or 0,
                is_foreground=True,
                source=PerceptionSource.PROCESS,
            )
        except Exception:
            return self._get_window_fallback()

    def get_ui_elements(self) -> List[UIElement]:
        """Get visible UI elements from the UIA monitor.

        Returns:
            List of UIElement objects
        """
        if not self._state_cache:
            return []

        try:
            # The state cache may provide UIA elements via get_uia_elements(); the
            # real awareness StateCache instead exposes them on the current window
            # context (`get_window().elements`, each carrying a `bounding_rect`).
            # Read whichever is available so the Accessibility tier is actually
            # populated on the live path.
            raw_elements = None
            if hasattr(self._state_cache, 'get_uia_elements'):
                raw_elements = self._state_cache.get_uia_elements()
            elif hasattr(self._state_cache, '_uia_elements'):
                raw_elements = self._state_cache._uia_elements

            if not raw_elements and hasattr(self._state_cache, 'get_window'):
                window = self._state_cache.get_window()
                raw_elements = getattr(window, 'elements', None) if window else None

            if not raw_elements:
                return []

            elements: List[UIElement] = []
            for raw in raw_elements:
                elem = self._convert_uia_element(raw)
                if elem:
                    elements.append(elem)
            return elements
        except Exception:
            return []

    def get_cursor_position(self) -> Tuple[int, int]:
        """Get current cursor position.

        Returns:
            (x, y) tuple
        """
        try:
            import pyautogui
            pos = pyautogui.position()
            return (pos.x, pos.y)
        except Exception:
            return (0, 0)

    def get_focused_element(self) -> Optional[UIElement]:
        """Get the currently focused UI element.

        Returns:
            UIElement or None
        """
        elements = self.get_ui_elements()
        for elem in elements:
            if elem.focused:
                return elem
        return None

    def _convert_uia_element(self, raw) -> Optional[UIElement]:
        """Convert a raw UIA element to our UIElement type.

        Handles various formats that the existing UIA monitor might produce.
        """
        try:
            # Handle dict format
            if isinstance(raw, dict):
                text = raw.get('text', '') or raw.get('name', '') or ''
                control_type = raw.get('control_type', '') or raw.get('type', '') or ''
                bbox_data = (raw.get('bbox', None) or raw.get('bounding_box', None)
                             or raw.get('bounding_rect', None))

                if bbox_data and len(bbox_data) == 4:
                    bbox = BoundingBox(
                        x=int(bbox_data[0]),
                        y=int(bbox_data[1]),
                        width=int(bbox_data[2]),
                        height=int(bbox_data[3]),
                    )
                else:
                    bbox = BoundingBox(x=0, y=0, width=0, height=0)

                return UIElement(
                    text=text,
                    control_type=control_type,
                    bbox=bbox,
                    focused=bool(raw.get('focused', False)),
                    enabled=bool(raw.get('enabled', True)),
                    automation_id=raw.get('automation_id', '') or '',
                    class_name=raw.get('class_name', '') or '',
                    confidence=1.0,
                    source=PerceptionSource.UIA,
                )

            # Handle object format (dataclass or namedtuple)
            if hasattr(raw, 'text') or hasattr(raw, 'name'):
                text = getattr(raw, 'text', '') or getattr(raw, 'name', '') or ''
                control_type = getattr(raw, 'control_type', '') or getattr(raw, 'type', '') or ''

                bbox_data = (getattr(raw, 'bounding_box', None) or getattr(raw, 'bbox', None)
                             or getattr(raw, 'bounding_rect', None))
                if bbox_data and len(bbox_data) == 4:
                    bbox = BoundingBox(
                        x=int(bbox_data[0]),
                        y=int(bbox_data[1]),
                        width=int(bbox_data[2]),
                        height=int(bbox_data[3]),
                    )
                else:
                    bbox = BoundingBox(x=0, y=0, width=0, height=0)

                return UIElement(
                    text=text,
                    control_type=control_type,
                    bbox=bbox,
                    focused=bool(getattr(raw, 'focused', False)),
                    enabled=bool(getattr(raw, 'enabled', True)),
                    automation_id=getattr(raw, 'automation_id', '') or '',
                    class_name=getattr(raw, 'class_name', '') or '',
                    confidence=1.0,
                    source=PerceptionSource.UIA,
                )

            return None
        except Exception:
            return None

    def _get_window_fallback(self) -> Optional[WindowInfo]:
        """Fallback: get window info directly via pyautogui/win32."""
        try:
            import pyautogui
            active = pyautogui.getActiveWindow()
            if active:
                return WindowInfo(
                    title=active.title or '',
                    process_name='',
                    pid=0,
                    handle=0,
                    is_foreground=True,
                    source=PerceptionSource.PROCESS,
                )
        except Exception:
            pass
        return None
