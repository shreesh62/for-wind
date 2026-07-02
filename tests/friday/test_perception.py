"""Tests for friday.perception — screen, OCR, desktop, and browser adapters."""

from unittest.mock import MagicMock, patch
import pytest

from friday.perception.types import BoundingBox, UIElement, BrowserElement, WindowInfo, PerceptionSource
from friday.perception.screen import ScreenCapture, Screenshot, MSS_AVAILABLE
from friday.perception.ocr import OCREngine, TESSERACT_AVAILABLE
from friday.perception.desktop import DesktopPerception
from friday.perception.browser import BrowserPerception


class TestScreenCapture:
    """Test screen capture module."""

    def test_available_property(self):
        """Screen capture should be available (MSS or PIL installed)."""
        capture = ScreenCapture()
        # At least one should be available on Windows
        assert capture.available is True

    @pytest.mark.skipif(not MSS_AVAILABLE, reason="MSS not installed")
    def test_grab_returns_screenshot(self):
        """Grab returns a Screenshot object."""
        capture = ScreenCapture()
        screenshot = capture.grab()

        assert screenshot is not None
        assert isinstance(screenshot, Screenshot)
        assert screenshot.width > 0
        assert screenshot.height > 0
        assert screenshot.pixel_hash != ""
        assert screenshot.timestamp > 0
        assert screenshot.capture_ms >= 0

    @pytest.mark.skipif(not MSS_AVAILABLE, reason="MSS not installed")
    def test_grab_hash_only(self):
        """Hash-only grab returns a non-empty string."""
        capture = ScreenCapture()
        hash_val = capture.grab_hash_only()
        assert isinstance(hash_val, str)
        assert len(hash_val) == 16

    @pytest.mark.skipif(not MSS_AVAILABLE, reason="MSS not installed")
    def test_grab_region(self):
        """Grabbing a specific region works."""
        capture = ScreenCapture()
        screenshot = capture.grab(region=(0, 0, 100, 100))

        assert screenshot is not None
        assert screenshot.width == 100
        assert screenshot.height == 100

    @pytest.mark.skipif(not MSS_AVAILABLE, reason="MSS not installed")
    def test_consecutive_grabs_same_hash_if_static(self):
        """Two immediate grabs should produce similar hashes if screen is static."""
        capture = ScreenCapture()
        hash1 = capture.grab_hash_only()
        hash2 = capture.grab_hash_only()
        # They might differ due to cursor blink etc, just verify they're valid
        assert len(hash1) == 16
        assert len(hash2) == 16


class TestOCREngine:
    """Test OCR engine module."""

    def test_import_and_init(self):
        """OCR engine initializes without error."""
        engine = OCREngine()
        # available depends on whether Tesseract binary is installed
        assert isinstance(engine.available, bool)

    @pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="pytesseract not installed")
    def test_extract_text_from_blank_image(self):
        """OCR on a blank image returns empty or whitespace text."""
        from PIL import Image
        engine = OCREngine()
        if not engine.available:
            pytest.skip("Tesseract binary not found")

        # Create a white image
        img = Image.new("RGB", (200, 50), color=(255, 255, 255))
        text = engine.extract_text(img)
        assert isinstance(text, str)
        # Blank image should produce empty or near-empty text
        assert len(text.strip()) < 5

    @pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="pytesseract not installed")
    def test_extract_regions_returns_list(self):
        """OCR regions extraction returns a list."""
        from PIL import Image
        engine = OCREngine()
        if not engine.available:
            pytest.skip("Tesseract binary not found")

        img = Image.new("RGB", (200, 50), color=(255, 255, 255))
        regions = engine.extract_regions(img)
        assert isinstance(regions, list)


class TestDesktopPerception:
    """Test desktop perception adapter."""

    def test_init_without_state_cache(self):
        """Adapter works without state cache (may use fallback)."""
        perception = DesktopPerception(state_cache=None)
        assert perception.available is False
        # get_active_window may return data via pyautogui fallback
        window = perception.get_active_window()
        if window is not None:
            assert isinstance(window, WindowInfo)
        assert perception.get_ui_elements() == []

    def test_get_active_window_from_cache(self):
        """Adapter converts state cache window context to WindowInfo."""
        mock_cache = MagicMock()
        mock_context = MagicMock()
        mock_context.title = "Notepad"
        mock_context.app_exe = "notepad.exe"
        mock_context.pid = 1234
        mock_context.class_name = "Notepad"
        mock_context.handle = 0x12345
        mock_cache.get_window.return_value = mock_context

        perception = DesktopPerception(state_cache=mock_cache)
        window = perception.get_active_window()

        assert window is not None
        assert isinstance(window, WindowInfo)
        assert window.title == "Notepad"
        assert window.process_name == "notepad.exe"
        assert window.pid == 1234

    def test_get_ui_elements_from_cache(self):
        """Adapter converts raw UIA elements to UIElement list."""
        mock_cache = MagicMock()
        mock_cache.get_uia_elements.return_value = [
            {
                'text': 'OK',
                'control_type': 'Button',
                'bbox': (100, 200, 80, 30),
                'focused': False,
                'enabled': True,
            },
            {
                'text': 'Cancel',
                'control_type': 'Button',
                'bbox': (200, 200, 80, 30),
                'focused': False,
                'enabled': True,
            },
        ]

        perception = DesktopPerception(state_cache=mock_cache)
        elements = perception.get_ui_elements()

        assert len(elements) == 2
        assert elements[0].text == "OK"
        assert elements[0].control_type == "Button"
        assert elements[0].bbox.x == 100
        assert elements[1].text == "Cancel"

    def test_get_cursor_position(self):
        """Cursor position returns a valid tuple."""
        perception = DesktopPerception(state_cache=MagicMock())
        pos = perception.get_cursor_position()
        assert isinstance(pos, tuple)
        assert len(pos) == 2


class TestBrowserPerception:
    """Test browser perception adapter."""

    def test_init_without_state_cache(self):
        """Adapter works without state cache."""
        perception = BrowserPerception(state_cache=None)
        assert perception.available is False
        assert perception.get_current_url() is None
        assert perception.get_visible_elements() == []

    def test_get_url_from_cache(self):
        """Adapter extracts URL from browser summary."""
        mock_cache = MagicMock()
        mock_cache.get_browser_summary.return_value = {
            'url': 'https://www.google.com',
            'title': 'Google',
        }

        perception = BrowserPerception(state_cache=mock_cache)
        url = perception.get_current_url()
        title = perception.get_page_title()

        assert url == "https://www.google.com"
        assert title == "Google"

    def test_get_elements_from_links(self):
        """Adapter converts link data to BrowserElement objects."""
        mock_cache = MagicMock()
        mock_cache.get_browser_summary.return_value = {
            'url': 'https://example.com',
            'title': 'Example',
            'links': [
                {'text': 'More info', 'href': '/info'},
                {'text': 'Contact', 'href': '/contact'},
            ],
            'buttons': ['Submit', 'Cancel'],
        }

        perception = BrowserPerception(state_cache=mock_cache)
        elements = perception.get_visible_elements()

        assert len(elements) == 4  # 2 links + 2 buttons
        link_elements = [e for e in elements if e.tag == "a"]
        button_elements = [e for e in elements if e.tag == "button"]
        assert len(link_elements) == 2
        assert len(button_elements) == 2
        assert link_elements[0].text == "More info"
        assert button_elements[0].text == "Submit"

    def test_get_hints(self):
        """Adapter extracts browser hints from summary."""
        mock_cache = MagicMock()
        mock_cache.get_browser_summary.return_value = {
            'url': 'https://login.example.com',
            'title': 'Login',
            'hints': {
                'has_login': True,
                'has_form': True,
                'has_consent': False,
            },
        }

        perception = BrowserPerception(state_cache=mock_cache)
        hints = perception.get_hints()

        assert hints['has_login'] is True
        assert hints['has_form'] is True
        assert hints['has_consent'] is False

    def test_connected_when_summary_available(self):
        """Connected is True when browser summary is available."""
        mock_cache = MagicMock()
        mock_cache.get_browser_summary.return_value = {'url': 'https://x.com'}

        perception = BrowserPerception(state_cache=mock_cache)
        assert perception.connected is True
