"""Tests for friday.actions.browser — DOM-first browser actions."""

from unittest.mock import MagicMock
import pytest

from friday.actions.browser import BrowserActions
from friday.actions.result import ActionStatus
from friday.perception.types import BoundingBox, BrowserElement, OCRRegion
from friday.perception.world_state import WorldStateBuilder


def _bbox():
    return BoundingBox(x=0, y=0, width=50, height=25)


class TestBrowserActions:
    """Test DOM-first browser actuators."""

    def test_unavailable_without_automation(self):
        browser = BrowserActions(automation_services=None)
        assert browser.available is False

        result = browser.navigate("https://google.com")
        assert result.is_success is False
        assert result.error_category == "no_automation"

    def test_navigate_success(self):
        mock_auto = MagicMock()
        mock_auto.navigate_to.return_value = "Navigated"

        browser = BrowserActions(automation_services=mock_auto)
        result = browser.navigate("google.com")

        assert result.is_success is True
        assert result.evidence.url_changed is True
        assert "https://google.com" in result.target

    def test_navigate_normalizes_url(self):
        mock_auto = MagicMock()
        mock_auto.navigate_to.return_value = "ok"

        browser = BrowserActions(automation_services=mock_auto)
        result = browser.navigate("example.com")

        # Should add https://
        assert result.target == "https://example.com"

    def test_navigate_error(self):
        mock_auto = MagicMock()
        mock_auto.navigate_to.side_effect = RuntimeError("Connection failed")

        browser = BrowserActions(automation_services=mock_auto)
        result = browser.navigate("https://x.com")

        assert result.is_success is False
        assert "retry_navigation" in result.repair_hints

    def test_click_via_dom(self):
        """Clicking a DOM element succeeds."""
        mock_auto = MagicMock()
        browser = BrowserActions(automation_services=mock_auto)

        builder = WorldStateBuilder()
        builder.set_browser_state(
            url="https://x.com", title="X",
            elements=[BrowserElement(tag="button", text="Submit", role="button", clickable=True)],
        )
        state = builder.build()

        result = browser.click_element("Submit", world_state=state)

        assert result.is_success is True
        assert result.evidence.raw.get("semantic") is True

    def test_click_blocked_when_only_ocr(self):
        """Clicking is blocked when element only found via OCR."""
        mock_auto = MagicMock()
        browser = BrowserActions(automation_services=mock_auto)

        builder = WorldStateBuilder()
        builder.add_ocr_regions([
            OCRRegion(text="Submit", bbox=_bbox(), confidence=0.9),
        ])
        state = builder.build()

        result = browser.click_element("Submit", world_state=state)

        # OCR-only element → blocked (unreliable to click)
        assert result.status == ActionStatus.BLOCKED
        assert "wait_for_dom" in result.repair_hints

    def test_type_text(self):
        mock_auto = MagicMock()
        browser = BrowserActions(automation_services=mock_auto)

        result = browser.type_text("hello world", field_hint="search")

        assert result.is_success is True
        assert result.evidence.text_appeared == "hello world"

    def test_read_page_text_prefers_dom(self):
        mock_auto = MagicMock()
        browser = BrowserActions(automation_services=mock_auto)

        builder = WorldStateBuilder()
        builder.set_browser_state(
            url="https://x.com", title="X",
            elements=[BrowserElement(tag="p", text="DOM page content", role="text", clickable=False)],
        )
        state = builder.build()

        text = browser.read_page_text(state)
        assert "DOM page content" in text

    def test_get_page_state(self):
        mock_auto = MagicMock()
        browser = BrowserActions(automation_services=mock_auto)

        builder = WorldStateBuilder()
        builder.set_browser_state(
            url="https://accounts.google.com", title="Sign in",
            elements=[BrowserElement(tag="input", text="Password", role="textbox", clickable=True)],
        )
        state = builder.build()

        page_state = browser.get_page_state(state)
        assert page_state == "login"
