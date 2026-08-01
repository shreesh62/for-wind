"""FastAPI remote control server for Jarvis."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import ipaddress
from collections import deque
from pathlib import Path
from typing import Optional

# /open is a narrow-purpose endpoint: it may enqueue "open <url>" and nothing
# else. Its inputs are interpolated into a natural-language command that an LLM
# planner then acts on, so an unvalidated value could smuggle extra instructions
# ("example.com and then delete my documents") into the planner. These patterns
# keep the endpoint's authority equal to its name.
_URL_RE = re.compile(
    r"^(?:https?://)?"                          # optional scheme
    r"(?:"
    r"localhost"                                # localhost
    r"|\d{1,3}(?:\.\d{1,3}){3}"                 # IPv4 literal
    r"|[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"    # first host label
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*"  # more labels
    r"\.[A-Za-z]{2,}"                           # TLD
    r")"
    r"(?::\d{1,5})?"                            # optional port
    r"(?:[/?#][^\s]*)?$"                        # optional path/query/fragment
)
_BROWSER_ALLOWLIST = frozenset({"chrome", "edge", "firefox", "brave", "default"})

try:  # pragma: no cover - optional dependency
    from fastapi import FastAPI, HTTPException, Depends, Header, Request
    from pydantic import BaseModel
    import uvicorn
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore
    HTTPException = None  # type: ignore
    Request = None  # type: ignore
    BaseModel = object  # type: ignore
    uvicorn = None  # type: ignore


class RemoteServerUnavailable(RuntimeError):
    """Raised when FastAPI or uvicorn are not installed."""


class CommandRequest(BaseModel):  # type: ignore[misc, assignment]
    text: str


class PersonaRequest(BaseModel):  # type: ignore[misc, assignment]
    persona: str


class OpenRequest(BaseModel):  # type: ignore[misc, assignment]
    url: str
    browser: str | None = None


class ScreenshotRequest(BaseModel):  # type: ignore[misc, assignment]
    path: str | None = None
    x: int | None = None
    y: int | None = None
    w: int | None = None
    h: int | None = None


class OcrRequest(BaseModel):  # type: ignore[misc, assignment]
    x: int
    y: int
    w: int
    h: int


class ExecuteRequest(BaseModel):  # type: ignore[misc, assignment]
    text: str
    metadata: dict | None = None
    speak: bool | None = None


def create_app(
    command_queue,
    status_provider=None,
    api_key: str | None = None,
    persona_setter=None,
    execute_handler=None,
) -> "FastAPI":  # type: ignore[return-type]
    if FastAPI is None or HTTPException is None:
        raise RemoteServerUnavailable(
            "FastAPI/uvicorn not installed. Run 'pip install fastapi uvicorn'."
        )

    app = FastAPI(title="Jarvis Remote Control", version="0.1.0")

    try:  # optional static files
        from fastapi.responses import FileResponse  # type: ignore
        from fastapi.staticfiles import StaticFiles  # type: ignore
    except ImportError:  # pragma: no cover
        FileResponse = None  # type: ignore
        StaticFiles = None  # type: ignore

    audit_path = os.getenv("REMOTE_AUDIT_LOG", "").strip()

    allowed_ips_raw = (
        os.getenv("REMOTE_ALLOWED_IPS", "").strip()
        or os.getenv("REMOTE_IP_ALLOWLIST", "").strip()
    )
    allowed_networks = []
    if allowed_ips_raw:
        for item in [p.strip() for p in allowed_ips_raw.split(",") if p.strip()]:
            try:
                allowed_networks.append(ipaddress.ip_network(item, strict=False))
            except Exception:
                pass

    rate_limit_per_minute_raw = os.getenv("REMOTE_RATE_LIMIT_PER_MINUTE", "0").strip()
    try:
        rate_limit_per_minute = int(rate_limit_per_minute_raw)
    except Exception:
        rate_limit_per_minute = 0
    _rate_window_seconds = 60.0
    _rate_buckets: dict[str, deque[float]] = {}

    def _client_ip(request: Request) -> str:
        try:
            return (request.client.host or "").strip() if request.client else ""
        except Exception:
            return ""

    def _audit(request: Request, *, ok: bool, event: str, detail: str = "") -> None:
        if not audit_path:
            return
        ip = _client_ip(request)
        rec = {
            "ts": time.time(),
            "ip": ip,
            "method": getattr(request, "method", ""),
            "path": str(getattr(request, "url", "") or ""),
            "event": event,
            "ok": bool(ok),
            "detail": (detail or "")[:300],
        }
        try:
            with open(audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            return

    def _enforce_allowlist(request: Request) -> None:
        if not allowed_networks:
            return
        ip = _client_ip(request)
        try:
            addr = ipaddress.ip_address(ip)
        except Exception:
            raise HTTPException(status_code=403, detail="Forbidden")
        for net in allowed_networks:
            try:
                if addr in net:
                    return
            except Exception:
                continue
        raise HTTPException(status_code=403, detail="Forbidden")

    def _enforce_rate_limit(request: Request) -> None:
        if rate_limit_per_minute <= 0:
            return
        ip = _client_ip(request) or "unknown"
        now = time.time()
        bucket = _rate_buckets.get(ip)
        if bucket is None:
            bucket = deque()
            _rate_buckets[ip] = bucket
        cutoff = now - _rate_window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= rate_limit_per_minute:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        bucket.append(now)

    def _check_auth(provided: Optional[str]) -> None:
        if api_key and provided != api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

    def auth_dependency(
        request: Request,
        api_key_header: Optional[str] = Header(default=None, alias="X-API-Key"),  # type: ignore
        x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),  # type: ignore
        api_key_query: Optional[str] = None,
    ) -> None:
        try:
            _enforce_allowlist(request)
            provided = api_key_header or x_api_key or api_key_query
            _check_auth(provided)
        except HTTPException as exc:
            _audit(request, ok=False, event="auth", detail=str(exc.detail))
            raise

    def execute_dependency(
        request: Request,
        _: None = Depends(auth_dependency),
    ) -> None:
        try:
            _enforce_rate_limit(request)
        except HTTPException as exc:
            _audit(request, ok=False, event="rate_limit", detail=str(exc.detail))
            raise

    if StaticFiles and FileResponse:
        ui_path = Path(__file__).resolve().parent / "static"
        app.mount("/static", StaticFiles(directory=str(ui_path)), name="static")

        @app.get("/", include_in_schema=False)
        async def index(_: None = Depends(auth_dependency)):
            return FileResponse(ui_path / "index.html")

    @app.get("/health")
    async def health(_: None = Depends(auth_dependency)) -> dict:
        return {"status": "ok"}

    @app.get("/status")
    async def status(_: None = Depends(auth_dependency)) -> dict:
        if status_provider is None:
            return {"status": "unavailable"}
        try:
            payload = status_provider()
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=500, detail=str(exc))
        if not isinstance(payload, dict):
            raise HTTPException(status_code=500, detail="Status provider returned invalid data")
        return payload

    @app.post("/commands")
    async def enqueue_command(payload: CommandRequest, _: None = Depends(auth_dependency)) -> dict:
        text = payload.text.strip()
        if not text:
            raise HTTPException(status_code=422, detail="Command text cannot be empty.")
        command_queue.put(text)
        return {"queued": True, "text": text}

    @app.post("/persona")
    async def set_persona(payload: PersonaRequest, _: None = Depends(auth_dependency)) -> dict:
        if persona_setter is None:
            raise HTTPException(status_code=503, detail="Persona control unavailable.")
        persona = payload.persona.strip().lower()
        if not persona:
            raise HTTPException(status_code=422, detail="Persona value cannot be empty.")
        try:
            persona_setter(persona)
        except ValueError as exc:  # type: ignore[catching-non-exception]
            raise HTTPException(status_code=400, detail=str(exc))
        return {"updated": True, "persona": persona}

    @app.post("/open")
    async def open_website(payload: OpenRequest, _: None = Depends(auth_dependency)) -> dict:
        url = (payload.url or "").strip()
        if not url:
            raise HTTPException(status_code=422, detail="URL cannot be empty.")
        # Both values are interpolated into a natural-language command for the LLM
        # planner, so they are validated as a URL and a known browser rather than
        # accepted as free text. Otherwise this endpoint would grant arbitrary
        # planner instructions under the name "open a website".
        if len(url) > 2048 or not _URL_RE.match(url):
            raise HTTPException(status_code=422, detail="Not a valid URL.")
        text = f"open {url}"
        if payload.browser:
            browser = payload.browser.strip().lower()
            if browser not in _BROWSER_ALLOWLIST:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unsupported browser. Choose one of: {sorted(_BROWSER_ALLOWLIST)}",
                )
            text += f" in {browser}"
        command_queue.put(text)
        return {"queued": True, "text": text}

    @app.post("/screenshot")
    async def take_screenshot(payload: ScreenshotRequest, _: None = Depends(auth_dependency)) -> dict:
        # If region provided, enqueue a region capture; else full screenshot
        if all(v is not None for v in (payload.x, payload.y, payload.w, payload.h)):
            text = f"screenshot region {payload.x} {payload.y} {payload.w} {payload.h}"
        else:
            text = "take screenshot"
        command_queue.put(text)
        return {"queued": True, "text": text}

    @app.post("/reload")
    async def reload(_: None = Depends(auth_dependency)) -> dict:
        text = "reload page"
        command_queue.put(text)
        return {"queued": True, "text": text}

    @app.post("/ocr")
    async def ocr(payload: OcrRequest, _: None = Depends(auth_dependency)) -> dict:
        text = f"ocr region {payload.x} {payload.y} {payload.w} {payload.h}"
        command_queue.put(text)
        return {"queued": True, "text": text}

    @app.post("/execute")
    async def execute(payload: ExecuteRequest, request: Request, _: None = Depends(execute_dependency)) -> dict:
        if execute_handler is None:
            raise HTTPException(status_code=503, detail="Execute handler unavailable.")
        text = (payload.text or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="Command text cannot be empty.")
        metadata = payload.metadata or {}
        if payload.speak is not None:
            try:
                metadata["speak"] = bool(payload.speak)
            except Exception:
                metadata["speak"] = payload.speak
        try:
            result = execute_handler(text, metadata)
        except TypeError:
            # Backward compatibility for handlers that only accept text.
            result = execute_handler(text)
        try:
            _audit(request, ok=True, event="execute", detail=text)
        except Exception:
            pass
        return result

    return app


class RemoteServer:
    """Wrapper that runs FastAPI + uvicorn in a background thread."""

    def __init__(
        self,
        command_queue,
        host: str = "127.0.0.1",
        port: int = 8801,
        status_provider=None,
        api_key: str | None = None,
        persona_setter=None,
        execute_handler=None,
    ) -> None:
        if FastAPI is None or uvicorn is None:
            raise RemoteServerUnavailable(
                "FastAPI/uvicorn not installed. Run 'pip install fastapi uvicorn'."
            )

        self.command_queue = command_queue
        self.host = host
        self.port = port
        self.status_provider = status_provider
        self.api_key = api_key
        self.persona_setter = persona_setter
        self.app = create_app(
            command_queue,
            status_provider=status_provider,
            api_key=api_key,
            persona_setter=persona_setter,
            execute_handler=execute_handler,
        )
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        self.server = uvicorn.Server(config)
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(target=self.server.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self.server:
            self.server.should_exit = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
