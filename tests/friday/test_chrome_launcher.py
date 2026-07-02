"""Tests for the Chrome launcher + real-Chrome connection mode (M2).

These do not launch a real browser in CI; they test the reachability check,
the launch-result contract, and that require_real_chrome changes behavior.
"""

from __future__ import annotations

import socket

import pytest

from friday.actions.chrome_launcher import (
    LaunchResult,
    cdp_reachable,
    ensure_chrome_debug,
)


class TestCdpReachable:
    def test_unreachable_port_returns_false(self):
        # Port 1 is privileged and not a CDP endpoint.
        assert cdp_reachable(port=1, timeout=0.5) is False

    def test_reachable_when_socket_open(self):
        # Open a throwaway server socket and check it reports reachable.
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            assert cdp_reachable(port=port, timeout=1.0) is True
        finally:
            srv.close()


class TestEnsureChromeDebug:
    def test_already_running_short_circuits(self, monkeypatch):
        monkeypatch.setattr(
            "friday.actions.chrome_launcher.cdp_reachable", lambda *a, **k: True
        )
        result = ensure_chrome_debug(port=9222)
        assert result.ok is True
        assert result.already_running is True
        assert result.launched is False

    def test_missing_chrome_returns_honest_failure(self, monkeypatch):
        monkeypatch.setattr(
            "friday.actions.chrome_launcher.cdp_reachable", lambda *a, **k: False
        )
        monkeypatch.setattr(
            "friday.actions.chrome_launcher._find_chrome_exe", lambda: None
        )
        result = ensure_chrome_debug(port=9222)
        assert result.ok is False
        assert "not found" in result.error.lower()


class TestConnectionModeContract:
    def test_controller_exposes_connection_mode(self):
        from friday.actions.browser_controller import BrowserController
        c = BrowserController()
        # Before start, no connection mode and not real chrome.
        assert c.connection_mode is None
        assert c.is_real_chrome is False

    def test_require_real_chrome_flag_stored(self):
        from friday.actions.browser_controller import BrowserController
        c = BrowserController(require_real_chrome=True)
        assert c._require_real_chrome is True


class TestTabAndViewportSurface:
    """Tab management + viewport API contract (ADR-046 hardening batch).

    These exercise the safe-fallback paths that run without a live browser
    loop, so no real Chrome/Playwright I/O occurs (FRIDAY_DRY_RUN also on).
    """

    def _controller(self):
        from friday.actions.browser_controller import BrowserController
        return BrowserController()

    def test_list_tabs_returns_empty_without_browser(self):
        c = self._controller()
        # No loop/context started -> safe empty list, never raises.
        assert c.list_tabs() == []

    def test_switch_tab_returns_error_without_browser(self):
        c = self._controller()
        res = c.switch_tab(0)
        assert res["ok"] is False
        assert "error" in res

    def test_viewport_size_defaults_without_browser(self):
        c = self._controller()
        vs = c.viewport_size()
        assert vs["width"] == 1280
        assert vs["height"] == 800
        # New field: device pixel ratio is always present for vision scaling.
        assert vs["device_pixel_ratio"] == 1.0

    def test_last_dialog_is_none_initially(self):
        c = self._controller()
        assert c.last_dialog() is None

    def test_new_methods_exist(self):
        c = self._controller()
        for name in ("list_tabs", "switch_tab", "last_dialog",
                     "_on_new_page", "_attach_dialog_handler"):
            assert hasattr(c, name), f"missing {name}"


class TestUploadDownloadContract:
    """upload_file / download_file safe-fallback contract (no live browser)."""

    def _controller(self):
        from friday.actions.browser_controller import BrowserController
        return BrowserController()

    def test_upload_missing_file_returns_error(self):
        c = self._controller()
        res = c.upload_file("C:\\definitely\\not\\here.txt")
        assert res["ok"] is False
        assert "not found" in res["error"]

    def test_download_unknown_index_returns_error(self):
        c = self._controller()
        res = c.download_file(99, elements=[{"index": 0, "text": "x"}])
        assert res["ok"] is False
        assert "no element index" in res["error"]

    def test_upload_download_methods_exist(self):
        c = self._controller()
        assert hasattr(c, "upload_file")
        assert hasattr(c, "download_file")
