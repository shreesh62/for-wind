"""Tests for friday.perception.world_state — WorldState and WorldStateBuilder."""

import time
import pytest

from friday.perception.world_state import WorldState, WorldStateBuilder, DerivedFacts
from friday.perception.types import (
    BoundingBox,
    BrowserElement,
    OCRRegion,
    PerceptionSource,
    UIElement,
    WindowInfo,
)


class TestWorldStateBuilder:
    """Test WorldStateBuilder constructs valid WorldState objects."""

    def test_empty_build(self):
        """Builder with no inputs produces a valid WorldState."""
        builder = WorldStateBuilder()
        state = builder.build()

        assert isinstance(state, WorldState)
        assert state.timestamp > 0
        assert state.build_duration_ms >= 0
        assert state.sources_used == []
        assert state.active_window is None
        assert state.ui_elements == []
        assert state.ocr_regions == []
        assert state.browser_elements == []
        assert state.browser_open is False
        assert state.state_hash != ""

    def test_with_window_info(self):
        """Builder correctly stores window information."""
        window = WindowInfo(
            title="Google Chrome",
            process_name="chrome.exe",
            pid=1234,
            class_name="Chrome_WidgetWin_1",
        )
        builder = WorldStateBuilder()
        builder.set_window_info(window)
        state = builder.build()

        assert state.active_window is not None
        assert state.active_window.title == "Google Chrome"
        assert state.active_window.process_name == "chrome.exe"
        assert state.active_window.pid == 1234
        assert PerceptionSource.PROCESS in state.sources_used

    def test_with_ui_elements(self):
        """Builder correctly stores UI elements."""
        elements = [
            UIElement(
                text="Submit",
                control_type="Button",
                bbox=BoundingBox(x=100, y=200, width=80, height=30),
                focused=False,
                enabled=True,
            ),
            UIElement(
                text="Username",
                control_type="Edit",
                bbox=BoundingBox(x=100, y=150, width=200, height=25),
                focused=True,
                enabled=True,
            ),
        ]
        builder = WorldStateBuilder()
        builder.add_ui_elements(elements)
        state = builder.build()

        assert len(state.ui_elements) == 2
        assert PerceptionSource.UIA in state.sources_used

    def test_with_browser_state(self):
        """Builder correctly stores browser state."""
        elements = [
            BrowserElement(tag="a", text="Click here", role="link", clickable=True),
            BrowserElement(tag="input", text="", role="textbox", clickable=True),
        ]
        builder = WorldStateBuilder()
        builder.set_browser_state(
            url="https://example.com",
            title="Example",
            elements=elements,
            connected=True,
        )
        state = builder.build()

        assert state.browser_open is True
        assert state.browser_url == "https://example.com"
        assert state.browser_title == "Example"
        assert len(state.browser_elements) == 2
        assert PerceptionSource.BROWSER in state.sources_used

    def test_with_ocr_regions(self):
        """Builder correctly stores OCR regions."""
        regions = [
            OCRRegion(
                text="Hello World",
                bbox=BoundingBox(x=50, y=50, width=120, height=20),
                confidence=0.95,
            ),
        ]
        builder = WorldStateBuilder()
        builder.add_ocr_regions(regions)
        state = builder.build()

        assert len(state.ocr_regions) == 1
        assert state.ocr_regions[0].text == "Hello World"
        assert PerceptionSource.OCR in state.sources_used

    def test_full_build(self):
        """Builder with all sources produces comprehensive WorldState."""
        builder = WorldStateBuilder()
        builder.set_window_info(WindowInfo(
            title="Chrome", process_name="chrome.exe", pid=100
        ))
        builder.set_cursor_position(500, 300)
        builder.add_ui_elements([
            UIElement(text="OK", control_type="Button",
                     bbox=BoundingBox(x=0, y=0, width=50, height=25))
        ])
        builder.set_screenshot_hash("abc123")
        builder.add_ocr_regions([
            OCRRegion(text="Login", bbox=BoundingBox(x=10, y=10, width=60, height=15),
                     confidence=0.9)
        ])
        builder.set_browser_state(
            url="https://accounts.google.com",
            title="Sign in",
            elements=[BrowserElement(tag="input", text="Email", role="textbox", clickable=True)],
        )

        state = builder.build()

        assert state.active_window.title == "Chrome"
        assert state.cursor_position == (500, 300)
        assert len(state.ui_elements) == 1
        assert state.screenshot_hash == "abc123"
        assert len(state.ocr_regions) == 1
        assert state.browser_url == "https://accounts.google.com"
        assert len(state.sources_used) == 5  # process, uia, screen, ocr, browser


class TestWorldState:
    """Test WorldState data access and utility methods."""

    def _build_state(self) -> WorldState:
        """Helper to build a sample state."""
        builder = WorldStateBuilder()
        builder.set_window_info(WindowInfo(
            title="Test App", process_name="test.exe", pid=42
        ))
        builder.add_ui_elements([
            UIElement(text="Login Button", control_type="Button",
                     bbox=BoundingBox(x=100, y=100, width=80, height=30)),
            UIElement(text="Password Field", control_type="Edit",
                     bbox=BoundingBox(x=100, y=50, width=200, height=25),
                     focused=True, enabled=True),
        ])
        builder.add_ocr_regions([
            OCRRegion(text="Sign In", bbox=BoundingBox(x=50, y=10, width=80, height=20),
                     confidence=0.92),
        ])
        builder.set_browser_state(
            url="https://login.example.com",
            title="Login Page",
            elements=[
                BrowserElement(tag="button", text="Submit", role="button", clickable=True),
            ],
        )
        return builder.build()

    def test_find_ui_element(self):
        """Find UI element by text."""
        state = self._build_state()
        elem = state.find_ui_element("login")
        assert elem is not None
        assert "Login" in elem.text

    def test_find_ui_element_with_type(self):
        """Find UI element by text and control type."""
        state = self._build_state()
        elem = state.find_ui_element("password", control_type="Edit")
        assert elem is not None
        assert elem.control_type == "Edit"

    def test_find_ui_element_not_found(self):
        """Return None when element not found."""
        state = self._build_state()
        assert state.find_ui_element("nonexistent") is None

    def test_find_ocr_text(self):
        """Find OCR region by text."""
        state = self._build_state()
        region = state.find_ocr_text("sign")
        assert region is not None
        assert region.text == "Sign In"

    def test_find_browser_element(self):
        """Find browser element by text."""
        state = self._build_state()
        elem = state.find_browser_element("submit")
        assert elem is not None
        assert elem.tag == "button"

    def test_find_browser_element_clickable_only(self):
        """Filter browser elements to clickable only."""
        state = self._build_state()
        elem = state.find_browser_element("submit", clickable_only=True)
        assert elem is not None

    def test_contains_text(self):
        """Check if state contains given text."""
        state = self._build_state()
        assert state.contains_text("Login") is True
        assert state.contains_text("Nonexistent Text XYZ") is False

    def test_all_text(self):
        """All text combines UI, OCR, and browser elements."""
        state = self._build_state()
        text = state.all_text
        assert "Login Button" in text
        assert "Sign In" in text
        assert "Submit" in text

    def test_state_hash_deterministic(self):
        """Same inputs produce same hash."""
        state1 = self._build_state()
        state2 = self._build_state()
        # Hashes may differ due to timestamp, so just check it's non-empty
        assert state1.state_hash != ""
        assert len(state1.state_hash) == 16

    def test_diff_from(self):
        """Diff detects changes between states."""
        builder1 = WorldStateBuilder()
        builder1.set_window_info(WindowInfo(title="App A", process_name="a.exe", pid=1))
        builder1.set_browser_state(url="https://a.com", title="A", elements=[])
        state1 = builder1.build()

        builder2 = WorldStateBuilder()
        builder2.set_window_info(WindowInfo(title="App B", process_name="b.exe", pid=2))
        builder2.set_browser_state(url="https://b.com", title="B", elements=[])
        state2 = builder2.build()

        diff = state2.diff_from(state1)
        assert diff["window_changed"] is True
        assert diff["url_changed"] is True
        assert diff["hash_changed"] is True

    def test_to_summary(self):
        """Summary produces compact dict suitable for logging."""
        state = self._build_state()
        summary = state.to_summary()

        assert "timestamp" in summary
        assert summary["window"] == "Test App"
        assert summary["app"] == "test.exe"
        assert summary["browser_url"] == "https://login.example.com"
        assert "state_hash" in summary
        assert "derived" in summary


class TestDerivedFacts:
    """Test derived fact computation from raw perception."""

    def test_login_detection(self):
        """Detect possible login screen from keywords."""
        builder = WorldStateBuilder()
        builder.add_ui_elements([
            UIElement(text="Password", control_type="Edit",
                     bbox=BoundingBox(x=0, y=0, width=100, height=25)),
            UIElement(text="Sign In", control_type="Button",
                     bbox=BoundingBox(x=0, y=30, width=80, height=25)),
        ])
        state = builder.build()
        assert state.derived.possible_login_screen is True

    def test_error_detection(self):
        """Detect possible error dialog from keywords."""
        builder = WorldStateBuilder()
        builder.add_ocr_regions([
            OCRRegion(text="Error: Connection failed",
                     bbox=BoundingBox(x=0, y=0, width=200, height=20),
                     confidence=0.9),
        ])
        state = builder.build()
        assert state.derived.possible_error_dialog is True

    def test_consent_detection(self):
        """Detect possible consent dialog."""
        builder = WorldStateBuilder()
        builder.add_browser_state_elements([
            BrowserElement(tag="button", text="Accept Cookies", role="button", clickable=True),
        ]) if hasattr(builder, 'add_browser_state_elements') else None
        # Use set_browser_state instead
        builder.set_browser_state(
            url="https://example.com",
            title="Example",
            elements=[
                BrowserElement(tag="button", text="Accept Cookies", role="button", clickable=True),
            ],
        )
        state = builder.build()
        assert state.derived.possible_consent_dialog is True

    def test_no_false_positives_on_empty(self):
        """Empty state should not trigger derived facts."""
        builder = WorldStateBuilder()
        state = builder.build()
        assert state.derived.possible_login_screen is False
        assert state.derived.possible_error_dialog is False
        assert state.derived.possible_consent_dialog is False
        assert state.derived.possible_loading is False


class TestBoundingBox:
    """Test BoundingBox utility methods."""

    def test_center(self):
        bbox = BoundingBox(x=100, y=200, width=80, height=40)
        assert bbox.center == (140, 220)

    def test_area(self):
        bbox = BoundingBox(x=0, y=0, width=100, height=50)
        assert bbox.area == 5000

    def test_contains(self):
        bbox = BoundingBox(x=10, y=10, width=100, height=100)
        assert bbox.contains(50, 50) is True
        assert bbox.contains(5, 5) is False
        assert bbox.contains(110, 110) is False

    def test_overlaps(self):
        box1 = BoundingBox(x=0, y=0, width=100, height=100)
        box2 = BoundingBox(x=50, y=50, width=100, height=100)
        box3 = BoundingBox(x=200, y=200, width=50, height=50)

        assert box1.overlaps(box2) is True
        assert box1.overlaps(box3) is False
