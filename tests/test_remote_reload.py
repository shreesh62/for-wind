import importlib
from fastapi.testclient import TestClient


def test_remote_reload_enqueues_command():
    mod = importlib.import_module("server.app")

    class DummyQueue:
        def __init__(self):
            self.items = []
        def put(self, item):
            self.items.append(item)

    q = DummyQueue()
    app = mod.create_app(q, status_provider=lambda: {}, api_key="key", persona_setter=None)
    client = TestClient(app)

    r = client.post("/reload", headers={"X-API-Key": "key"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("queued") is True
    assert data.get("text") == "reload page"
    assert q.items and q.items[-1] == "reload page"


def test_remote_reload_requires_auth():
    mod = importlib.import_module("server.app")

    class DummyQueue:
        def put(self, item):
            pass

    q = DummyQueue()
    app = mod.create_app(q, status_provider=lambda: {}, api_key="secret", persona_setter=None)
    client = TestClient(app)

    r = client.post("/reload")
    assert r.status_code == 401
