import importlib

from fastapi.testclient import TestClient


def test_execute_requires_auth():
    mod = importlib.import_module("server.app")

    class DummyQueue:
        def put(self, item):
            pass

    def handler(_text, _metadata=None):
        return {"ok": True, "text": "hi", "handled": True, "screenshot_path": None, "meta": {}}

    app = mod.create_app(DummyQueue(), status_provider=lambda: {}, api_key="secret", persona_setter=None, execute_handler=handler)
    client = TestClient(app)

    r = client.post("/execute", json={"text": "ping"})
    assert r.status_code == 401


def test_execute_calls_handler_and_passes_metadata():
    mod = importlib.import_module("server.app")

    class DummyQueue:
        def put(self, item):
            pass

    seen = {}

    def handler(text, metadata=None):
        seen["text"] = text
        seen["metadata"] = metadata
        return {"ok": True, "text": "ok", "handled": True, "screenshot_path": None, "meta": {"source": (metadata or {}).get("source")}}

    app = mod.create_app(DummyQueue(), status_provider=lambda: {}, api_key="key", persona_setter=None, execute_handler=handler)
    client = TestClient(app)

    r = client.post(
        "/execute",
        headers={"X-API-Key": "key"},
        json={"text": "take screenshot", "metadata": {"source": "telegram", "user_id": 1}},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert seen.get("text") == "take screenshot"
    assert isinstance(seen.get("metadata"), dict)
    assert seen["metadata"].get("source") == "telegram"


def test_execute_allows_speak_flag_and_merges_into_metadata():
    mod = importlib.import_module("server.app")

    class DummyQueue:
        def put(self, item):
            pass

    seen = {}

    def handler(text, metadata=None):
        seen["text"] = text
        seen["metadata"] = metadata
        return {"ok": True, "text": "ok", "handled": True, "screenshot_path": None, "meta": {}}

    app = mod.create_app(DummyQueue(), status_provider=lambda: {}, api_key="key", persona_setter=None, execute_handler=handler)
    client = TestClient(app)

    r = client.post(
        "/execute",
        headers={"X-API-Key": "key"},
        json={"text": "hello", "metadata": {"source": "remote"}, "speak": True},
    )
    assert r.status_code == 200
    assert seen.get("text") == "hello"
    assert isinstance(seen.get("metadata"), dict)
    assert seen["metadata"].get("source") == "remote"
    assert seen["metadata"].get("speak") is True


def test_execute_unavailable_without_handler():
    mod = importlib.import_module("server.app")

    class DummyQueue:
        def put(self, item):
            pass

    app = mod.create_app(DummyQueue(), status_provider=lambda: {}, api_key="key", persona_setter=None)
    client = TestClient(app)

    r = client.post("/execute", headers={"X-API-Key": "key"}, json={"text": "ping"})
    assert r.status_code == 503
