"""M23 — DesktopPerception reads UIA elements from the window context.

Feature: m23-browser-generic-desktop-environment

The real awareness StateCache exposes UIA elements via `get_window().elements`
(each with a `bounding_rect`), not `get_uia_elements()`. This verifies
DesktopPerception now reads them and maps `bounding_rect` correctly, so the
Accessibility tier of Universal Perception is populated on the live path.
"""

from friday.perception.desktop import DesktopPerception


class _Elem:
    def __init__(self, name, control_type, rect, focused=False):
        self.name = name
        self.control_type = control_type
        self.bounding_rect = rect  # (x, y, w, h)
        self.focused = focused


class _Window:
    def __init__(self, elements):
        self.elements = elements


class _StateCacheWithWindowElements:
    """Mimics awareness.StateCache: UIA elements live on the window context."""

    def __init__(self, window):
        self._window = window

    def get_window(self):
        return self._window


def test_desktop_perception_reads_window_context_elements():
    # Validates: Requirements 1.1, 1.2 (UIA/Accessibility tier populated live)
    win = _Window([
        _Elem("Sign in", "Hyperlink", (100, 200, 80, 20), focused=False),
        _Elem("Search", "Edit", (10, 20, 300, 30), focused=True),
    ])
    perception = DesktopPerception(state_cache=_StateCacheWithWindowElements(win))

    elements = perception.get_ui_elements()
    assert len(elements) == 2

    by_text = {e.text: e for e in elements}
    assert "Sign in" in by_text and "Search" in by_text

    signin = by_text["Sign in"]
    assert signin.control_type == "Hyperlink"
    # bounding_rect must map onto the UIElement bbox (x, y, w, h).
    assert (signin.bbox.x, signin.bbox.y, signin.bbox.width, signin.bbox.height) == (100, 200, 80, 20)
    assert signin.bbox.center == (140, 210)

    # focused flag carried through
    assert by_text["Search"].focused is True


def test_desktop_perception_empty_without_state_cache():
    assert DesktopPerception().get_ui_elements() == []
