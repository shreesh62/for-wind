"""Tests for friday.api — FastAPI backend."""

import tempfile
import pytest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from friday.api.app import create_friday_api
from friday.bridge import FridayBridge, BridgeResult
from friday.memory import FridayMemory
from friday.router.classifier import RequestMode, ComplexityLevel


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def mock_bridge():
    """Create a mock bridge that returns predictable results."""
    bridge = MagicMock(spec=FridayBridge)
    bridge.process.return_value = BridgeResult(
        response="Hello! I'm FRIDAY.",
        mode=RequestMode.JARVIS,
        complexity=ComplexityLevel.SIMPLE_QUESTION,
        handled=True,
    )
    return bridge


@pytest.fixture
def mock_memory(tmp_dir):
    return FridayMemory(data_dir=tmp_dir)


@pytest.fixture
def client(mock_bridge, mock_memory):
    """Create test client with mocked dependencies."""
    app = create_friday_api(
        bridge=mock_bridge,
        memory=mock_memory,
        api_key="test-key-123",
    )
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-key-123"}


class TestHealthEndpoint:
    """Test /api/health (no auth required)."""

    def test_health_returns_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "uptime" in data


class TestCommandEndpoint:
    """Test POST /api/command."""

    def test_command_requires_auth(self, client):
        response = client.post("/api/command", json={"text": "hello"})
        assert response.status_code == 401

    def test_command_executes_with_auth(self, client, auth_headers, mock_bridge):
        response = client.post(
            "/api/command",
            json={"text": "What is Python?"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["text"] == "Hello! I'm FRIDAY."
        assert data["mode"] == "jarvis"
        assert data["complexity"] == 0
        mock_bridge.process.assert_called_once()

    def test_command_with_wake_word(self, client, auth_headers, mock_bridge):
        response = client.post(
            "/api/command",
            json={"text": "send Om hello", "wake_word": "friday"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        # Verify wake_word was passed to bridge
        call_kwargs = mock_bridge.process.call_args
        assert call_kwargs[1]["wake_word"] == "friday" or call_kwargs[0][1] == "friday"

    def test_command_returns_duration(self, client, auth_headers):
        response = client.post(
            "/api/command",
            json={"text": "hello"},
            headers=auth_headers,
        )
        data = response.json()
        assert "duration_ms" in data
        assert data["duration_ms"] >= 0


class TestStatusEndpoint:
    """Test GET /api/status."""

    def test_status_requires_auth(self, client):
        response = client.get("/api/status")
        assert response.status_code == 401

    def test_status_returns_info(self, client, auth_headers):
        response = client.get("/api/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["online"] is True
        assert "uptime_seconds" in data
        assert "memory_stats" in data

    def test_status_shows_active_goal(self, client, auth_headers, mock_memory):
        mock_memory.set_active_goal("Research laptops", steps=5)
        response = client.get("/api/status", headers=auth_headers)
        data = response.json()
        assert data["active_goal"] == "Research laptops"
        assert data["mode"] == "active"


class TestMemoryEndpoints:
    """Test /api/memory/* endpoints."""

    def test_memory_search(self, client, auth_headers, mock_memory):
        # Add some data
        mock_memory.record_turn("Open Chrome", "Chrome opened", mode="friday")

        response = client.post(
            "/api/memory/search",
            json={"query": "chrome", "top_k": 5},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    def test_memory_recent(self, client, auth_headers, mock_memory):
        mock_memory.record_turn("Hello", "Hi!", mode="jarvis")
        mock_memory.record_turn("Open app", "Done", mode="friday")

        response = client.get(
            "/api/memory/recent?limit=5",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "episodes" in data
        assert len(data["episodes"]) == 2


class TestModelsEndpoint:
    """Test GET /api/models."""

    def test_models_without_router(self, client, auth_headers):
        response = client.get("/api/models", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "models" in data

    def test_models_with_router(self, auth_headers, mock_bridge, tmp_dir):
        from friday.models.router import ModelRouter, ModelCapability, ModelInfo as MInfo

        router = ModelRouter()

        class FakeProvider:
            name = "test_provider"
            available = True
            models = [MInfo(
                provider="test_provider",
                model_id="test-model",
                capabilities=[ModelCapability.REASONING],
                priority=5,
            )]

        router.register_provider(FakeProvider())

        app = create_friday_api(
            bridge=mock_bridge,
            memory=FridayMemory(data_dir=tmp_dir),
            model_router=router,
            api_key="test-key-123",
        )
        client = TestClient(app)

        response = client.get("/api/models", headers=auth_headers)
        data = response.json()
        assert "test_provider" in data["providers"]
        assert any(m["model_id"] == "test-model" for m in data["models"])


class TestWebSocket:
    """Test WebSocket endpoint."""

    def test_ws_requires_token(self, client):
        with pytest.raises(Exception):
            with client.websocket_connect("/api/ws"):
                pass

    def test_ws_ping_pong(self, client):
        with client.websocket_connect("/api/ws?token=test-key-123") as ws:
            ws.send_json({"type": "ping"})
            response = ws.receive_json()
            assert response["type"] == "pong"

    def test_ws_command_execution(self, client, mock_bridge):
        with client.websocket_connect("/api/ws?token=test-key-123") as ws:
            ws.send_json({"type": "command", "text": "What is Python?"})
            response = ws.receive_json()
            assert response["type"] == "command_response"
            assert response["data"]["ok"] is True
