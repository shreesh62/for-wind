"""Tests for the WorldState API endpoint and perceive_as_dict."""

import tempfile
from unittest.mock import MagicMock
import pytest

from fastapi.testclient import TestClient

from friday.api.app import create_friday_api
from friday.bridge import FridayBridge
from friday.core import FridayEngine
from friday.perception.types import BoundingBox, BrowserElement, UIElement, WindowInfo
from friday.perception.world_state import WorldStateBuilder


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestPerceiveAsDict:
    """Test the engine's perceive_as_dict method."""

    def test_returns_dict_with_semantic_coverage(self):
        engine = FridayEngine()

        # Stub perceive to return a controlled state
        builder = WorldStateBuilder()
        builder.set_window_info(WindowInfo(title="Chrome", process_name="chrome.exe", pid=1))
        builder.add_ui_elements([
            UIElement(text="OK", control_type="Button", bbox=BoundingBox(0, 0, 50, 25)),
        ])
        builder.set_browser_state(
            url="https://x.com", title="X",
            elements=[BrowserElement(tag="a", text="Home", role="link", clickable=True)],
        )
        state = builder.build()
        engine.perceive = lambda: state

        result = engine.perceive_as_dict()

        assert "semantic_coverage" in result
        assert result["window"] == "Chrome"
        assert result["browser_url"] == "https://x.com"
        assert isinstance(result["cursor"], list)
        assert result["semantic_coverage"] == 1.0  # All DOM/UIA, no OCR


class TestWorldStateEndpoint:
    """Test GET /api/worldstate."""

    def _client(self, engine_perceive=None):
        bridge = FridayBridge()
        if engine_perceive:
            bridge.engine.perceive = engine_perceive
        app = create_friday_api(bridge=bridge, api_key="k")
        return TestClient(app)

    def test_requires_auth(self):
        client = self._client()
        r = client.get("/api/worldstate")
        assert r.status_code == 401

    def test_returns_worldstate(self):
        builder = WorldStateBuilder()
        builder.set_window_info(WindowInfo(title="Notepad", process_name="notepad.exe", pid=2))
        state = builder.build()

        client = self._client(engine_perceive=lambda: state)
        r = client.get("/api/worldstate", headers={"X-API-Key": "k"})

        assert r.status_code == 200
        data = r.json()
        assert data["window"] == "Notepad"
        assert data["app"] == "notepad.exe"
        assert "state_hash" in data
        assert "semantic_coverage" in data
        assert "derived" in data

    def test_worldstate_schema_fields(self):
        builder = WorldStateBuilder()
        state = builder.build()
        client = self._client(engine_perceive=lambda: state)

        r = client.get("/api/worldstate", headers={"X-API-Key": "k"})
        data = r.json()

        # All documented WorldStateSchema fields present
        for field in ["timestamp", "window", "app", "cursor", "focused",
                      "ui_elements", "ocr_regions", "browser_url", "browser_title",
                      "browser_elements", "derived", "state_hash", "sources",
                      "semantic_coverage"]:
            assert field in data

    def test_perception_failure_returns_500(self):
        def failing_perceive():
            raise RuntimeError("perception broke")

        client = self._client(engine_perceive=failing_perceive)
        r = client.get("/api/worldstate", headers={"X-API-Key": "k"})
        assert r.status_code == 500
