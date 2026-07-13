"""Real-socket integration test for the browserless research fetch path.

Unlike the M16 unit/property tests (which mock the httpx layer entirely), this
test exercises the REAL network transport: it stands up a localhost HTTP server
and lets `web_search.gather` perform genuine `httpx` GETs over a real socket —
real HTTP request/response encoding, real 200/403 handling, real HTML->text
extraction on real response bytes, real evidence + belief production.

This closes part of the M18-audit "weak real-use coverage" gap in a hermetic,
CI-safe way: no external network (loopback only), no browser, no mocks of the
product code under test. The search step is supplied (search backend is an
external dependency); everything downstream of it runs for real.
"""

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import friday.capabilities.web_search as web_search
from friday.capabilities.web_search import SearchHit
from friday.verification.evidence_law import EvidenceKind, ExecutionEvidence


# --------------------------------------------------------------------------- #
# A tiny localhost server: /ok returns real HTML (with a <script> to strip),
# /forbidden returns 403 (best-effort skip path).
# --------------------------------------------------------------------------- #

_OK_HTML = (
    "<html><head><title>T</title>"
    "<script>window.x = 'SHOULD_NOT_LEAK';</script>"
    "<style>body{color:red}</style></head>"
    "<body><h1>Renewable Energy</h1>"
    "<p>Solar and wind are leading sources in 2024.</p></body></html>"
)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib API name
        if self.path.startswith("/ok"):
            body = _OK_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"forbidden")

    def log_message(self, *args):  # silence test server logging
        return


@pytest.fixture()
def local_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()
        server.server_close()


def test_gather_fetches_real_localhost_pages(local_server, monkeypatch):
    """gather performs real httpx GETs: 200 page text is extracted (scripts
    stripped) and recorded; a 403 page is skipped; beliefs carry the source URL.
    """
    port = local_server
    ok_url = f"http://127.0.0.1:{port}/ok"
    forbidden_url = f"http://127.0.0.1:{port}/forbidden"

    # Real network path requires dry-run OFF (conftest forces it on).
    monkeypatch.setenv("FRIDAY_DRY_RUN", "0")

    # Supply the search step (external backend); everything downstream is real.
    def _fake_search(query, *, timeout=10.0, max_results=10):
        return web_search.SearchOutcome(
            hits=[
                SearchHit(url=ok_url, snippet="real snippet about energy", title="OK"),
                SearchHit(url=forbidden_url, snippet="", title="Forbidden"),
            ],
            ok=True,
            host_used="localhost-test",
        )

    monkeypatch.setattr(web_search, "http_search", _fake_search)

    evidence = ExecutionEvidence()
    result = web_search.gather("renewable energy", evidence, max_sources=3)

    gathered = evidence.of_kind(EvidenceKind.GATHERED_INFO)
    sources = evidence.of_kind(EvidenceKind.SOURCE_URL)
    gathered_sources = {a.source for a in gathered}

    # The real 200 page was fetched and its text extracted (from a real socket).
    assert any("Solar and wind" in a.detail for a in gathered), \
        "real page body text should be recorded as gathered info"
    assert ok_url in gathered_sources
    # Untrusted content: <script>/<style> contents never leak into gathered text.
    assert all("SHOULD_NOT_LEAK" not in (a.detail or "") for a in gathered)
    assert all("color:red" not in (a.detail or "") for a in gathered)

    # The snippet was recorded, and both result URLs are recorded as sources.
    assert any("real snippet about energy" in a.detail for a in gathered)
    assert {ok_url, forbidden_url}.issubset({a.detail for a in sources})

    # The 403 page produced no page-body gathered-info entry (skipped gracefully).
    assert not any(a.source == forbidden_url for a in gathered)

    # Beliefs were produced from real findings, provenance carries the source URL.
    assert result.beliefs, "expected at least one belief from real findings"
    all_supporting = {
        url
        for b in result.beliefs
        for url in b.provenance.supporting_observations
    }
    assert ok_url in all_supporting
