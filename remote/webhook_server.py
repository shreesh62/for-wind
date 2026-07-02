import hmac
import hashlib
import os
import time
import json
from collections import deque
from typing import Optional
from pathlib import Path
import sys

from typing import Any

import requests

try:
    from fastapi import FastAPI, Header, HTTPException, Request  # type: ignore
    from pydantic import BaseModel  # type: ignore
    import uvicorn  # type: ignore
except Exception:
    FastAPI = None  # type: ignore
    BaseModel = object  # type: ignore

try:
    # Allow running as a script: add project root to sys.path
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except Exception:
    pass

from dotenv import load_dotenv

load_dotenv()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
REMOTE_SERVER_URL = os.getenv("REMOTE_SERVER_URL", "http://127.0.0.1:8801").rstrip("/")
REMOTE_API_KEY = os.getenv("REMOTE_API_KEY", "")
WEBHOOK_SPEAK = os.getenv("WEBHOOK_SPEAK", "").strip().lower() in ("1", "true", "yes")

WEBHOOK_AUDIT_LOG = os.getenv("WEBHOOK_AUDIT_LOG", "").strip()
_rate_limit_raw = os.getenv("WEBHOOK_RATE_LIMIT_PER_MINUTE", os.getenv("REMOTE_RATE_LIMIT_PER_MINUTE", "0")).strip()
try:
    WEBHOOK_RATE_LIMIT_PER_MINUTE = int(_rate_limit_raw)
except Exception:
    WEBHOOK_RATE_LIMIT_PER_MINUTE = 0

_replay_window_raw = os.getenv("WEBHOOK_REPLAY_WINDOW_SEC", "0").strip()
try:
    WEBHOOK_REPLAY_WINDOW_SEC = int(_replay_window_raw)
except Exception:
    WEBHOOK_REPLAY_WINDOW_SEC = 0

_seen_signatures: deque[tuple[float, str]] = deque()
_rate_bucket: deque[float] = deque()


class WebhookPayload(BaseModel):  # type: ignore[misc]
    text: str


def hmac_match(body: bytes, signature: str, secret: str) -> bool:
    if not signature:
        return False
    if signature.startswith("sha256="):
        signature = signature.split("=", 1)[1]
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(mac, signature)
    except Exception:
        return mac == signature


def _audit(event: str, *, ok: bool, detail: str = "") -> None:
    if not WEBHOOK_AUDIT_LOG:
        return
    rec = {
        "ts": time.time(),
        "event": event,
        "ok": bool(ok),
        "detail": (detail or "")[:300],
    }
    try:
        with open(WEBHOOK_AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        return


def _enforce_rate_limit() -> None:
    if WEBHOOK_RATE_LIMIT_PER_MINUTE <= 0:
        return
    now = time.time()
    cutoff = now - 60.0
    while _rate_bucket and _rate_bucket[0] < cutoff:
        _rate_bucket.popleft()
    if len(_rate_bucket) >= WEBHOOK_RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _rate_bucket.append(now)


def _enforce_replay_protection(signature: str) -> None:
    if WEBHOOK_REPLAY_WINDOW_SEC <= 0:
        return
    now = time.time()
    cutoff = now - float(WEBHOOK_REPLAY_WINDOW_SEC)
    while _seen_signatures and _seen_signatures[0][0] < cutoff:
        _seen_signatures.popleft()
    sig = (signature or "").strip()
    if not sig:
        return
    for _, s in _seen_signatures:
        if s == sig:
            raise HTTPException(status_code=409, detail="Replay detected")
    _seen_signatures.append((now, sig))


last_response: Optional[str] = None
last_error: Optional[str] = None


def _call_execute(text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if not REMOTE_API_KEY:
        return {"ok": False, "error": "REMOTE_API_KEY is not configured."}
    headers = {"Content-Type": "application/json", "X-API-Key": REMOTE_API_KEY}
    payload: dict[str, Any] = {"text": text, "metadata": metadata or {"source": "webhook"}}
    if WEBHOOK_SPEAK:
        payload["speak"] = True
    resp = requests.post(f"{REMOTE_SERVER_URL}/execute", json=payload, headers=headers, timeout=60)
    try:
        data = resp.json()
    except Exception:
        return {"ok": False, "error": f"Non-JSON response ({resp.status_code})."}
    if resp.status_code != 200:
        if isinstance(data, dict):
            return {"ok": False, "error": data.get("detail") or data.get("error") or f"HTTP {resp.status_code}"}
        return {"ok": False, "error": f"HTTP {resp.status_code}"}
    if not isinstance(data, dict):
        return {"ok": False, "error": "Invalid response from /execute"}
    return data


def create_app() -> "FastAPI":  # type: ignore[return-type]
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Run: pip install fastapi uvicorn")
    app = FastAPI(title="Jarvis Webhook", version="0.1.0")

    @app.post("/webhook")
    async def webhook(payload: WebhookPayload, request: Request, x_signature: str = Header(default="")) -> dict:
        if not WEBHOOK_SECRET:
            raise HTTPException(status_code=503, detail="Webhook secret not configured.")
        _enforce_rate_limit()
        # Verify HMAC against exact raw body bytes
        body_bytes = await request.body()
        if not hmac_match(body_bytes, x_signature or "", WEBHOOK_SECRET):
            _audit("auth", ok=False, detail="Invalid signature")
            raise HTTPException(status_code=401, detail="Invalid signature.")
        _enforce_replay_protection(x_signature or "")
        global last_response, last_error
        try:
            result = _call_execute(payload.text, {"source": "webhook"})
            if not result.get("ok"):
                last_error = result.get("error")
                _audit("execute", ok=False, detail=str(last_error))
                return {"ok": False, "error": last_error}
            last_response = (result.get("text") or "") if isinstance(result.get("text"), str) else str(result.get("text"))
            last_error = None
            _audit("execute", ok=True, detail=payload.text)
            return {"ok": True, "response": last_response, "screenshot_path": result.get("screenshot_path")}
        except Exception as e:
            last_error = str(e)
            _audit("execute", ok=False, detail=str(e))
            return {"ok": False, "error": str(e)}

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/status")
    async def status() -> dict:
        return {
            "ok": True,
            "has_secret": bool(WEBHOOK_SECRET),
            "has_remote_api_key": bool(REMOTE_API_KEY),
            "remote_url": REMOTE_SERVER_URL,
            "last_response": last_response,
            "last_error": last_error,
        }

    return app


def main() -> None:
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8811)


if __name__ == "__main__":
    main()
