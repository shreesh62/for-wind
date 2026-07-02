"""Tests for screenshot evidence + captcha/block detection.

Covers the two issues the owner reported:
1. Chrome opened on a captcha page and kept spawning the same tab.
2. No visual evidence existed to detect the stuck state.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from friday.verification.screenshot_evidence import (
    ScreenshotResult,
    blocked_reason,
    capture_screenshot,
    is_blocked_page,
)
from friday.verification.evidence_law import (
    EvidenceKind,
    ExecutionEvidence,
)


class TestBlockDetection:
    def test_google_unusual_traffic_is_blocked(self):
        text = "Our systems have detected unusual traffic from your computer network."
        assert is_blocked_page(text) is True

    def test_recaptcha_is_blocked(self):
        assert is_blocked_page("Please complete the reCAPTCHA to continue") is True

    def test_cloudflare_is_blocked(self):
        assert is_blocked_page("Checking your browser before accessing the site") is True

    def test_im_not_a_robot_is_blocked(self):
        assert is_blocked_page("Verify you are human. I'm not a robot.") is True

    def test_real_content_is_not_blocked(self):
        text = "The best laptops under 80k include the Acer Swift and Lenovo IdeaPad..."
        assert is_blocked_page(text) is False

    def test_empty_is_not_blocked(self):
        assert is_blocked_page("") is False

    def test_blocked_reason_names_signal(self):
        reason = blocked_reason("unusual traffic detected")
        assert "unusual traffic" in reason

    def test_url_can_trigger_block(self):
        assert is_blocked_page("", url="https://www.google.com/sorry/index") is False
        assert is_blocked_page("captcha", url="https://x.com") is True


class TestScreenshotCapture:
    def test_capture_with_fake_screen(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FRIDAY_EVIDENCE_DIR", str(tmp_path))

        class _FakeShot:
            def save(self, path):
                with open(path, "wb") as f:
                    f.write(b"\x89PNG\r\n" + b"0" * 200)

        class _FakeCapture:
            def grab(self):
                return _FakeShot()

        result = capture_screenshot(label="unit_test", screen_capture=_FakeCapture())
        assert result.is_real is True
        assert result.size > 0
        assert os.path.exists(result.path)

    def test_capture_failure_returns_not_real(self):
        class _NullCapture:
            def grab(self):
                return None

        result = capture_screenshot(label="x", screen_capture=_NullCapture())
        assert result.is_real is False
        assert result.size == 0


class TestScreenshotAsEvidence:
    def test_screenshot_artifact_is_real_with_size(self):
        ev = ExecutionEvidence()
        ev.add_screenshot("/tmp/x.png", 1024, "after_read")
        arts = ev.of_kind(EvidenceKind.SCREENSHOT)
        assert len(arts) == 1
        assert arts[0].is_real

    def test_zero_byte_screenshot_not_recorded(self):
        ev = ExecutionEvidence()
        ev.add_screenshot("/tmp/x.png", 0, "empty")
        assert ev.has(EvidenceKind.SCREENSHOT) is False
