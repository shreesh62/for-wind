"""Tests for new modular API routes (remember, tasks)."""

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
    bridge = MagicMock(spec=FridayBridge)
    bridge.process.return_value = BridgeResult(
        response="ok", mode=RequestMode.JARVIS,
        complexity=ComplexityLevel.SIMPLE_QUESTION, handled=True,
    )
    return bridge


@pytest.fixture
def client(mock_bridge, tmp_dir):
    memory = FridayMemory(data_dir=tmp_dir)
    app = create_friday_api(bridge=mock_bridge, memory=memory, api_key="k")
    return TestClient(app)


@pytest.fixture
def headers():
    return {"X-API-Key": "k"}


class TestRememberEndpoint:
    def test_remember_requires_auth(self, client):
        r = client.post("/api/memory/remember", json={"content": "test fact"})
        assert r.status_code == 401

    def test_remember_stores_fact(self, client, headers):
        r = client.post(
            "/api/memory/remember",
            json={"content": "Shreesh prefers DOM", "category": "preference"},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_remembered_fact_searchable(self, client, headers):
        client.post(
            "/api/memory/remember",
            json={"content": "FRIDAY uses NVIDIA NIM", "category": "general"},
            headers=headers,
        )
        r = client.post(
            "/api/memory/search",
            json={"query": "NVIDIA", "tier": "semantic"},
            headers=headers,
        )
        assert r.status_code == 200
        results = r.json()["results"]
        assert any("NVIDIA" in res["content"] for res in results)


class TestTasksEndpoint:
    def test_tasks_requires_auth(self, client):
        r = client.get("/api/tasks/current")
        assert r.status_code == 401

    def test_tasks_idle_when_no_goal(self, client, headers):
        r = client.get("/api/tasks/current", headers=headers)
        assert r.status_code == 200
        assert r.json()["active"] is False

    def test_tasks_active_with_goal(self, client, headers, tmp_dir):
        # Set a goal via the memory the client uses
        ctx = client.app.state.ctx
        ctx.memory.set_active_goal("Research laptops", steps=5)
        ctx.memory.update_goal_progress(2)

        r = client.get("/api/tasks/current", headers=headers)
        data = r.json()
        assert data["active"] is True
        assert data["task"]["goal"] == "Research laptops"
        assert data["task"]["total_steps"] == 5
        assert data["task"]["completed_steps"] == 2
        assert abs(data["task"]["progress"] - 0.4) < 0.01


class TestSchemaContracts:
    """Verify schemas serialize as documented."""

    def test_command_response_shape(self, client, headers):
        r = client.post("/api/command", json={"text": "hi"}, headers=headers)
        data = r.json()
        # Documented contract fields
        for field in ["ok", "text", "mode", "complexity", "handled", "verified", "duration_ms", "error"]:
            assert field in data

    def test_status_response_shape(self, client, headers):
        r = client.get("/api/status", headers=headers)
        data = r.json()
        for field in ["online", "mode", "active_goal", "uptime_seconds", "memory_stats", "model_stats"]:
            assert field in data
