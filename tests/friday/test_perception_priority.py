"""Tests for friday.perception.priority — semantic-first resolution."""

import pytest

from friday.perception.types import (
    BoundingBox,
    BrowserElement,
    OCRRegion,
    PerceptionSource,
    UIElement,
    WindowInfo,
)
from friday.perception.world_state import WorldStateBuilder
from friday.perception.priority import (
    PerceptionResolver,
    ResolvedElement,
    SourcePriority,
)


def _bbox(x=0, y=0, w=50, h=25):
    return BoundingBox(x=x, y=y, width=w, height=h)


class TestPerceptionResolver:
    """Test semantic-first element resolution."""

    def setup_method(self):
        self.resolver = PerceptionResolver()

    def test_prefers_browser_dom_over_ocr(self):
        """When both DOM and OCR have a match, DOM wins."""
        builder = WorldStateBuilder()
        builder.set_browser_state(
            url="https://example.com",
            title="Example",
            elements=[
                BrowserElement(tag="button", text="Submit", role="button", clickable=True),
            ],
        )
        builder.add_ocr_regions([
            OCRRegion(text="Submit", bbox=_bbox(), confidence=0.9),
        ])
        state = builder.build()

        element = self.resolver.find_element(state, "Submit")

        assert element is not None
        assert element.source == PerceptionSource.BROWSER
        assert element.priority == int(SourcePriority.BROWSER_DOM)
        assert element.is_semantic is True

    def test_prefers_uia_over_ocr(self):
        """When both UIA and OCR have a match, UIA wins."""
        builder = WorldStateBuilder()
        builder.add_ui_elements([
            UIElement(text="OK", control_type="Button", bbox=_bbox()),
        ])
        builder.add_ocr_regions([
            OCRRegion(text="OK", bbox=_bbox(), confidence=0.9),
        ])
        state = builder.build()

        element = self.resolver.find_element(state, "OK")

        assert element is not None
        assert element.source == PerceptionSource.UIA
        assert element.is_semantic is True

    def test_prefers_browser_over_uia(self):
        """Browser DOM beats UIA when both present."""
        builder = WorldStateBuilder()
        builder.set_browser_state(
            url="https://x.com", title="X",
            elements=[BrowserElement(tag="a", text="Login", role="link", clickable=True)],
        )
        builder.add_ui_elements([
            UIElement(text="Login", control_type="Button", bbox=_bbox()),
        ])
        state = builder.build()

        element = self.resolver.find_element(state, "Login")
        assert element.source == PerceptionSource.BROWSER

    def test_falls_back_to_ocr_when_no_semantic(self):
        """OCR is used only when no semantic source has the element."""
        builder = WorldStateBuilder()
        builder.add_ocr_regions([
            OCRRegion(text="Status: Ready", bbox=_bbox(), confidence=0.85),
        ])
        state = builder.build()

        element = self.resolver.find_element(state, "Status")
        assert element is not None
        assert element.source == PerceptionSource.OCR
        assert element.is_semantic is False

    def test_clickable_only_excludes_ocr(self):
        """clickable_only should not return OCR (can't confirm clickability)."""
        builder = WorldStateBuilder()
        builder.add_ocr_regions([
            OCRRegion(text="Click here", bbox=_bbox(), confidence=0.9),
        ])
        state = builder.build()

        element = self.resolver.find_element(state, "Click here", clickable_only=True)
        assert element is None

    def test_no_match_returns_none(self):
        """No matching element returns None."""
        builder = WorldStateBuilder()
        builder.add_ui_elements([UIElement(text="Foo", control_type="Button", bbox=_bbox())])
        state = builder.build()

        assert self.resolver.find_element(state, "Nonexistent") is None

    def test_read_text_prefers_dom(self):
        """Reading text prefers DOM over UIA over OCR."""
        builder = WorldStateBuilder()
        builder.set_browser_state(
            url="https://x.com", title="X",
            elements=[BrowserElement(tag="p", text="DOM content here", role="text", clickable=False)],
        )
        builder.add_ocr_regions([
            OCRRegion(text="OCR content", bbox=_bbox(), confidence=0.8),
        ])
        state = builder.build()

        text = self.resolver.read_text(state)
        assert "DOM content" in text
        assert "OCR content" not in text

    def test_read_text_falls_back_to_ocr(self):
        """Reading text falls back to OCR when no semantic text."""
        builder = WorldStateBuilder()
        builder.add_ocr_regions([
            OCRRegion(text="Only OCR text", bbox=_bbox(), confidence=0.8),
        ])
        state = builder.build()

        text = self.resolver.read_text(state)
        assert "Only OCR text" in text

    def test_determine_page_type_login(self):
        """Page type detection uses semantic derived facts."""
        builder = WorldStateBuilder()
        builder.add_ui_elements([
            UIElement(text="Password", control_type="Edit", bbox=_bbox()),
            UIElement(text="Sign In", control_type="Button", bbox=_bbox()),
        ])
        state = builder.build()

        page_type = self.resolver.determine_page_type(state)
        assert page_type == "login"

    def test_determine_page_type_browser(self):
        """Browser page detected when browser open and no special facts."""
        builder = WorldStateBuilder()
        builder.set_browser_state(
            url="https://example.com", title="Example",
            elements=[BrowserElement(tag="div", text="content", role="text", clickable=False)],
        )
        state = builder.build()

        page_type = self.resolver.determine_page_type(state)
        assert page_type == "browser_page"

    def test_semantic_coverage_full(self):
        """Semantic coverage is 1.0 when only DOM/UIA present."""
        builder = WorldStateBuilder()
        builder.add_ui_elements([
            UIElement(text="A", control_type="Button", bbox=_bbox()),
            UIElement(text="B", control_type="Button", bbox=_bbox()),
        ])
        state = builder.build()

        quality = self.resolver.get_perception_quality(state)
        assert quality["semantic_coverage"] == 1.0
        assert quality["has_uia"] is True

    def test_semantic_coverage_mixed(self):
        """Semantic coverage reflects DOM/UIA vs OCR ratio."""
        builder = WorldStateBuilder()
        builder.add_ui_elements([
            UIElement(text="A", control_type="Button", bbox=_bbox()),
        ])
        builder.add_ocr_regions([
            OCRRegion(text="B", bbox=_bbox(), confidence=0.8),
        ])
        state = builder.build()

        quality = self.resolver.get_perception_quality(state)
        assert quality["semantic_coverage"] == 0.5

    def test_best_source_browser(self):
        """Best source is browser DOM when available."""
        builder = WorldStateBuilder()
        builder.set_browser_state(
            url="https://x.com", title="X",
            elements=[BrowserElement(tag="a", text="link", role="link", clickable=True)],
        )
        builder.add_ui_elements([UIElement(text="x", control_type="Button", bbox=_bbox())])
        state = builder.build()

        quality = self.resolver.get_perception_quality(state)
        assert quality["best_source"] == "BROWSER_DOM"

    def test_uia_clickable_control_detection(self):
        """UIA clickable controls are detected for clickable_only."""
        builder = WorldStateBuilder()
        builder.add_ui_elements([
            UIElement(text="Menu Item", control_type="MenuItem", bbox=_bbox()),
        ])
        state = builder.build()

        element = self.resolver.find_element(state, "Menu Item", clickable_only=True)
        assert element is not None
        assert element.clickable is True

    def test_uia_non_clickable_excluded(self):
        """Non-clickable UIA controls excluded from clickable_only."""
        builder = WorldStateBuilder()
        builder.add_ui_elements([
            UIElement(text="Label text", control_type="Text", bbox=_bbox()),
        ])
        state = builder.build()

        element = self.resolver.find_element(state, "Label text", clickable_only=True)
        assert element is None
