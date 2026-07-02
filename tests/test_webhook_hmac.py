import os
import json
import hmac
import hashlib

import importlib

from fastapi.testclient import TestClient


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def build_client(secret: str):
    # Ensure env is set before import so module picks up secret
    os.environ["WEBHOOK_SECRET"] = secret
    os.environ["REMOTE_API_KEY"] = "test_remote_key"
    os.environ["REMOTE_SERVER_URL"] = "http://127.0.0.1:8801"
    mod = importlib.import_module("remote.webhook_server")
    importlib.reload(mod)

    class DummyResp:
        def __init__(self, status_code: int = 200, payload=None):
            self.status_code = status_code
            self._payload = payload if payload is not None else {"ok": True, "text": "pong", "screenshot_path": None}

        def json(self):
            return self._payload

    def fake_post(*_args, **_kwargs):
        return DummyResp()

    mod.requests.post = fake_post  # type: ignore[attr-defined]
    app = mod.create_app()
    return TestClient(app), mod


def test_health_and_hmac_ok():
    client, mod = build_client("testsecret")

    # Health
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("ok") is True

    # HMAC signed request
    body = b'{"text":"what\'s the weather in Thane"}'
    headers = {"X-Signature": sign("testsecret", body), "Content-Type": "application/json"}
    r = client.post("/webhook", data=body, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    # We don't assert exact wording; just that it returns a response or an error key
    assert data.get("ok") in (True, False)
    if data.get("ok") is True:
        assert data.get("response") == "pong"


def test_hmac_invalid_rejected():
    client, mod = build_client("secretA")
    body = json.dumps({"text": "ping"}).encode("utf-8")
    headers = {"X-Signature": sign("wrong", body), "Content-Type": "application/json"}
    r = client.post("/webhook", data=body, headers=headers)
    assert r.status_code == 401
