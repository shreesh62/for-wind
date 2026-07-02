"""Unit tests for VisionAdapter — the lowest-priority coordinate fallback.

Task 6.2 — exercises VisionAdapter in `friday/actions/adapters/vision.py`.

SAFETY: These tests NEVER call a real vision model, perform real screen
capture, or open any window. Every pyautogui call is patched with a recording
fake via monkeypatch. FRIDAY_DRY_RUN=1 is also enforced by the test session
conftest. WorldState is built from in-memory OCR regions only.

Coverage:
- identity: name + priority (lowest among adapters)
- can_handle: OCR text match, explicit coordinates, no match
- resolve_element: OCR region match, coordinate fallback, unresolvable
- async action methods dispatch to mocked pyautogui and return ActionResult
- click point derivation from OCR center vs coordinate bbox
- focus_window always fails (cannot switch windows semantically)
- adapter failure surfaces as a failed ActionResult

Validates: Requirements 5.1, 13.1
"""

from __future__ import annotations

import asyncio

import pytest

import friday.actions.adapters.vision as vision_mod
from friday.actions.adapters.vision import VisionAdapter
from friday.actions.result import ActionResult, ActionStatus
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.types import BoundingBox, OCRRegion, PerceptionSource
from friday.perception.world_state import WorldStateBuilder


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class FakePyAutoGUI:
    """Records every pyautogui call instead of touching the real screen."""

    def __init__(self):
        self.calls = []

    def click(self, x, y):
        self.calls.append(("click", x, y))

    def doubleClick(self, x, y):
        self.calls.append(("doubleClick", x, y))

    def rightClick(self, x, y):
        self.calls.append(("rightClick", x, y))

    def write(self, text):
        self.calls.append(("write", text))

    def press(self, key):
        self.calls.append(("press", key))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", tuple(keys)))

    def scroll(self, amount, x=None, y=None):
        self.calls.append(("scroll", amount, x, y))

    def moveTo(self, x, y):
        self.calls.append(("moveTo", x, y))

    def drag(self, dx, dy, duration=0.0):
        self.calls.append(("drag", dx, dy, duration))


@pytest.fixture
def fake_gui(monkeypatch):
    """Patch the module-level pyautogui surface with a recording fake."""
    fake = FakePyAutoGUI()
    monkeypatch.setattr(vision_mod, "pyautogui", fake)
    return fake


def make_world(*regions: OCRRegion):
    """Build a WorldState containing only the given OCR regions."""
    builder = WorldStateBuilder()
    if regions:
        builder.add_ocr_regions(list(regions))
    return builder.build()


def ocr(text, x=100, y=200, w=40, h=20, confidence=0.9):
    return OCRRegion(
        text=text,
        bbox=BoundingBox(x=x, y=y, width=w, height=h),
        confidence=confidence,
    )


def coord_element(x=50, y=60):
    """A ResolvedElement representing a raw coordinate target."""
    return ResolvedElement(
        text=f"({x}, {y})",
        source=PerceptionSource.SCREEN,
        priority=10,
        confidence=1.0,
        clickable=False,
        bbox=(x, y, 1, 1),
        raw_element=None,
    )


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

class TestIdentity:
    def test_name_is_vision(self):
        assert VisionAdapter().name == "vision"

    def test_priority_is_lowest(self):
        # 30 is the documented lowest priority among all adapters
        # (browser 100, desktop 80, desktop_actions 60, vision 30).
        assert VisionAdapter().priority == 30


# ---------------------------------------------------------------------------
# can_handle
# ---------------------------------------------------------------------------

class TestCanHandle:
    def test_can_handle_when_ocr_text_matches(self):
        adapter = VisionAdapter()
        ws = make_world(ocr("Submit"))
        assert adapter.can_handle(Target(text="Submit"), ws) is True

    def test_can_handle_match_is_case_insensitive(self):
        adapter = VisionAdapter()
        ws = make_world(ocr("SUBMIT NOW"))
        assert adapter.can_handle(Target(text="submit"), ws) is True

    def test_can_handle_with_explicit_coordinates(self):
        adapter = VisionAdapter()
        ws = make_world()  # no OCR data
        assert adapter.can_handle(Target(coordinates=(10, 20)), ws) is True

    def test_cannot_handle_when_no_match_and_no_coordinates(self):
        adapter = VisionAdapter()
        ws = make_world(ocr("Cancel"))
        assert adapter.can_handle(Target(text="Submit"), ws) is False


# ---------------------------------------------------------------------------
# resolve_element
# ---------------------------------------------------------------------------

class TestResolveElement:
    def test_resolve_from_ocr_region(self):
        adapter = VisionAdapter()
        ws = make_world(ocr("Submit", x=100, y=200, w=40, h=20, confidence=0.8))
        element = adapter.resolve_element(Target(text="Submit"), ws)
        assert element is not None
        assert element.source == PerceptionSource.OCR
        assert element.priority == 30
        assert element.confidence == 0.8
        assert element.bbox == (100, 200, 40, 20)
        assert isinstance(element.raw_element, OCRRegion)

    def test_resolve_falls_back_to_coordinates(self):
        adapter = VisionAdapter()
        ws = make_world()  # no OCR match
        element = adapter.resolve_element(Target(coordinates=(15, 25)), ws)
        assert element is not None
        assert element.source == PerceptionSource.SCREEN
        assert element.bbox == (15, 25, 1, 1)
        assert element.raw_element is None

    def test_resolve_prefers_ocr_over_coordinates(self):
        adapter = VisionAdapter()
        ws = make_world(ocr("Submit", x=100, y=200))
        element = adapter.resolve_element(
            Target(text="Submit", coordinates=(15, 25)), ws
        )
        assert element is not None
        assert element.source == PerceptionSource.OCR

    def test_resolve_returns_none_when_unresolvable(self):
        adapter = VisionAdapter()
        ws = make_world(ocr("Cancel"))
        assert adapter.resolve_element(Target(text="Submit"), ws) is None


# ---------------------------------------------------------------------------
# Click point derivation
# ---------------------------------------------------------------------------

class TestClickPoint:
    def test_click_uses_ocr_region_center(self, fake_gui):
        adapter = VisionAdapter()
        ws = make_world(ocr("Submit", x=100, y=200, w=40, h=20))
        element = adapter.resolve_element(Target(text="Submit"), ws)
        res = asyncio.run(adapter.click(element))
        assert res.is_success
        # center = (100 + 40//2, 200 + 20//2) = (120, 210)
        assert ("click", 120, 210) in fake_gui.calls

    def test_click_uses_coordinate_bbox_center(self, fake_gui):
        adapter = VisionAdapter()
        element = coord_element(x=50, y=60)
        res = asyncio.run(adapter.click(element))
        assert res.is_success
        # bbox (50, 60, 1, 1) -> center (50 + 0, 60 + 0) = (50, 60)
        assert ("click", 50, 60) in fake_gui.calls


# ---------------------------------------------------------------------------
# Async action methods
# ---------------------------------------------------------------------------

class TestActionMethods:
    def test_click_returns_success_result(self, fake_gui):
        adapter = VisionAdapter()
        res = asyncio.run(adapter.click(coord_element()))
        assert isinstance(res, ActionResult)
        assert res.status == ActionStatus.SUCCESS
        assert res.action_type == "click"
        assert res.evidence.state_changed is True

    def test_double_click_dispatches(self, fake_gui):
        adapter = VisionAdapter()
        res = asyncio.run(adapter.double_click(coord_element(70, 80)))
        assert res.is_success
        assert ("doubleClick", 70, 80) in fake_gui.calls

    def test_right_click_dispatches(self, fake_gui):
        adapter = VisionAdapter()
        res = asyncio.run(adapter.right_click(coord_element(70, 80)))
        assert res.is_success
        assert ("rightClick", 70, 80) in fake_gui.calls

    def test_type_text_dispatches(self, fake_gui):
        adapter = VisionAdapter()
        res = asyncio.run(adapter.type_text("hello"))
        assert res.is_success
        assert ("write", "hello") in fake_gui.calls

    def test_press_key_dispatches(self, fake_gui):
        adapter = VisionAdapter()
        res = asyncio.run(adapter.press_key("enter"))
        assert res.is_success
        assert ("press", "enter") in fake_gui.calls

    def test_press_hotkey_dispatches(self, fake_gui):
        adapter = VisionAdapter()
        res = asyncio.run(adapter.press_hotkey(["ctrl", "s"]))
        assert res.is_success
        assert ("hotkey", ("ctrl", "s")) in fake_gui.calls
        assert res.target == "ctrl+s"

    def test_scroll_up_uses_positive_amount_with_element(self, fake_gui):
        adapter = VisionAdapter()
        element = coord_element(50, 60)
        res = asyncio.run(adapter.scroll("up", 3, element))
        assert res.is_success
        assert ("scroll", 3, 50, 60) in fake_gui.calls

    def test_scroll_down_uses_negative_amount_no_element(self, fake_gui):
        adapter = VisionAdapter()
        res = asyncio.run(adapter.scroll("down", 3))
        assert res.is_success
        assert ("scroll", -3, None, None) in fake_gui.calls

    def test_drag_moves_and_drags_between_elements(self, fake_gui):
        adapter = VisionAdapter()
        source = coord_element(10, 10)
        dest = coord_element(40, 50)
        res = asyncio.run(adapter.drag(source, dest))
        assert res.is_success
        assert ("moveTo", 10, 10) in fake_gui.calls
        # drag delta = dest - source = (30, 40)
        assert any(c[0] == "drag" and c[1] == 30 and c[2] == 40 for c in fake_gui.calls)


# ---------------------------------------------------------------------------
# focus_window
# ---------------------------------------------------------------------------

class TestFocusWindow:
    def test_focus_window_always_fails(self):
        adapter = VisionAdapter()
        res = asyncio.run(adapter.focus_window(Target(window_title="Notepad")))
        assert not res.is_success
        assert res.status == ActionStatus.FAILED
        assert res.error_category == "adapter_failed"
        assert res.repair_hints


# ---------------------------------------------------------------------------
# Failure surfacing
# ---------------------------------------------------------------------------

class TestFailureSurfacing:
    def test_click_on_element_without_position_fails_gracefully(self, fake_gui):
        adapter = VisionAdapter()
        bad = ResolvedElement(
            text="ghost",
            source=PerceptionSource.SCREEN,
            priority=10,
            confidence=1.0,
            clickable=False,
            bbox=None,
            raw_element=None,
        )
        res = asyncio.run(adapter.click(bad))
        assert not res.is_success
        assert res.error_category == "adapter_failed"
        assert res.error

    def test_backend_exception_surfaces_as_failed_result(self, monkeypatch):
        adapter = VisionAdapter()

        def boom(*args, **kwargs):
            raise RuntimeError("backend exploded")

        fake = FakePyAutoGUI()
        fake.click = boom
        monkeypatch.setattr(vision_mod, "pyautogui", fake)

        res = asyncio.run(adapter.click(coord_element()))
        assert not res.is_success
        assert res.error_category == "adapter_failed"
        assert "backend exploded" in res.error
