"""M16 — Research Competence: unit tests (P5, P6, P11, P12).

Request-shape + fallback order (P5), best-effort page-fetch skip (P6), browser-path
parity + unchanged defaults (P11), and backward-compatible signatures (P12).

All HTTP is MOCKED via a spy httpx patched onto ``friday.capabilities.web_search``.
No test performs a live network call. Non-dry-run paths patch ``FRIDAY_DRY_RUN`` and
a spy client together so no real request is ever issued.
"""

from __future__ import annotations

import inspect
import os
from unittest import mock

import pytest

import friday.capabilities.web_search as web_search
from friday.capabilities.research import ResearchResult, research
from friday.verification.evidence_law import EvidenceKind, ExecutionEvidence


# --------------------------------------------------------------------------- #
# Fake httpx (spy)
# --------------------------------------------------------------------------- #


class _Resp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _SpyClient:
    def __init__(self, handler):
        self._handler = handler
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self._handler("POST", url, kw)

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self._handler("GET", url, kw)


class _SpyHttpx:
    def __init__(self, handler):
        self._handler = handler
        self.clients = []

    def Client(self, *a, **kw):
        c = _SpyClient(self._handler)
        self.clients.append(c)
        return c

    def calls(self):
        return [c for client in self.clients for c in client.calls]


def _mk_results_html(hits):
    blocks = []
    for href, snippet, title in hits:
        b = f'<div class="result"><a class="result__a" href="{href}">{title}</a>'
        if snippet:
            b += f'<div class="result__snippet">{snippet}</div>'
        b += "</div>"
        blocks.append(b)
    return "<html><body>" + "".join(blocks) + "</body></html>"


_SEARCH_HTML = _mk_results_html([
    ("https://one.example.com/a", "first snippet", "One"),
    ("https://two.example.com/b", "second snippet", "Two"),
])


class _EnvHttpxPatch:
    def __init__(self, spy, dry_run="0"):
        self._p1 = mock.patch.object(web_search, "httpx", spy)
        self._p2 = mock.patch.dict(os.environ, {"FRIDAY_DRY_RUN": dry_run})

    def __enter__(self):
        self._p1.start()
        self._p2.start()
        return self

    def __exit__(self, *a):
        self._p2.stop()
        self._p1.stop()
        return False


# --------------------------------------------------------------------------- #
# Property 5 — request shape + fallback order + graceful total failure
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 5: Fallback host order and graceful
# total failure


class TestProperty5RequestShapeAndFallback:
    """Validates: Requirements 1.2, 1.4, 1.5"""

    def test_primary_is_post_to_html_ddg_with_form_q_and_browser_ua(self):
        captured = {}

        def handler(method, url, kw):
            if not captured:
                captured.update({"method": method, "url": url, "kw": kw})
            return _Resp(200, _SEARCH_HTML)

        spy = _SpyHttpx(handler)
        with mock.patch.object(web_search, "httpx", spy):
            outcome = http_search_helper(query="quantum computing")

        assert outcome.ok is True
        assert outcome.host_used == "html.duckduckgo.com"
        # Primary request is a POST to the HTML endpoint.
        assert captured["method"] == "POST"
        assert captured["url"] == "https://html.duckduckgo.com/html/"
        # Query carried in the form field named q.
        assert captured["kw"]["data"] == {"q": "quantum computing"}
        # Browser-class User-Agent.
        assert "Mozilla" in captured["kw"]["headers"]["User-Agent"]

    def test_non_200_primary_falls_back_to_lite(self):
        def handler(method, url, kw):
            if "html.duckduckgo.com" in url:
                return _Resp(503, "service unavailable")
            return _Resp(200, _SEARCH_HTML)  # lite endpoint

        spy = _SpyHttpx(handler)
        with mock.patch.object(web_search, "httpx", spy):
            outcome = http_search_helper(query="fallback test")

        assert outcome.ok is True
        assert outcome.host_used == "lite.duckduckgo.com"
        # A GET to the lite host must have occurred.
        assert any(c[0] == "GET" and "lite.duckduckgo.com" in c[1] for c in spy.calls())

    def test_raising_primary_falls_back_to_lite(self):
        def handler(method, url, kw):
            if "html.duckduckgo.com" in url:
                raise RuntimeError("connection reset")
            return _Resp(200, _SEARCH_HTML)

        spy = _SpyHttpx(handler)
        with mock.patch.object(web_search, "httpx", spy):
            outcome = http_search_helper(query="raise then fallback")

        assert outcome.ok is True
        assert outcome.host_used == "lite.duckduckgo.com"

    def test_all_providers_fail_returns_ok_false_no_raise(self):
        def handler(method, url, kw):
            return _Resp(500, "boom")

        spy = _SpyHttpx(handler)
        with mock.patch.object(web_search, "httpx", spy):
            outcome = http_search_helper(query="everything fails")

        assert outcome.ok is False
        assert outcome.error  # descriptive, non-empty
        assert outcome.hits == []

    def test_all_providers_raise_returns_ok_false_no_raise(self):
        def handler(method, url, kw):
            raise RuntimeError("network down")

        spy = _SpyHttpx(handler)
        with mock.patch.object(web_search, "httpx", spy):
            outcome = http_search_helper(query="all raise")

        assert outcome.ok is False
        assert outcome.error


def http_search_helper(query):
    """Thin call-through so the patched module-level httpx is used."""
    return web_search.http_search(query)


# --------------------------------------------------------------------------- #
# Property 6 — best-effort page-fetch failures are skipped
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 6: Best-effort page fetch failures are
# skipped


class TestProperty6PageFetchSkip:
    """Validates: Requirements 2.6, 7.5"""

    def test_page_403_and_raise_are_skipped_search_evidence_retained(self):
        hits = [
            ("https://p403.example.com/a", "snippet a", "A"),
            ("https://praise.example.com/b", "snippet b", "B"),
        ]
        html = _mk_results_html(hits)

        def handler(method, url, kw):
            low = url.lower()
            if "duckduckgo.com" in low:
                return _Resp(200, html)
            if url == "https://p403.example.com/a":
                return _Resp(403, "forbidden")
            if url == "https://praise.example.com/b":
                raise RuntimeError("transport error")
            return _Resp(200, "unexpected")

        spy = _SpyHttpx(handler)
        with _EnvHttpxPatch(spy, dry_run="0"):
            ev = ExecutionEvidence()
            # Must NOT raise.
            result = web_search.gather("query", ev, max_sources=3)

        # Search-page evidence (snippets + urls) retained despite page-fetch failures.
        assert ev.has(EvidenceKind.GATHERED_INFO)
        assert ev.has(EvidenceKind.SOURCE_URL)
        assert result.error == "" or isinstance(result.error, str)


# --------------------------------------------------------------------------- #
# Property 11 — browser-path parity + unchanged production defaults
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 11: Browser-path parity and unchanged
# defaults


class _FakeBrowser:
    """Fake browser exposing search_web/navigate/read_text/current_url."""

    def __init__(self, pages):
        self.available = True
        self._pages = pages
        self._current_url = ""

    def search_web(self, query):
        links = [{"text": f"R{i}", "href": u} for i, u in enumerate(self._pages)]
        return {"ok": True, "text": f"Search results for {query}", "links": links}

    def navigate(self, url):
        self._current_url = url
        return {"ok": True, "url": url} if url in self._pages else {"ok": False}

    def read_text(self, max_chars=4000):
        return self._pages.get(self._current_url, "")[:max_chars]

    def current_url(self):
        return self._current_url


class TestProperty11BrowserParityAndDefaults:
    """Validates: Requirements 3.2, 3.5, 5.4"""

    def test_browser_present_uses_browser_path_not_gather(self):
        browser = _FakeBrowser(pages={
            "https://site-a.example.com/x": "Real content about the topic A.",
            "https://site-b.example.com/y": "Real content about the topic B.",
        })
        # Patch the browserless gatherer; the browser path must NOT invoke it.
        with mock.patch.object(web_search, "gather") as gather_spy:
            ev = ExecutionEvidence()
            result = research("some topic", browser, ev, max_sources=3)

        gather_spy.assert_not_called()
        assert result.success is True
        assert ev.has(EvidenceKind.GATHERED_INFO)
        assert ev.has(EvidenceKind.SOURCE_URL)

    def test_belief_defaults_unchanged(self):
        from friday.world.belief import Belief

        b = Belief(description="x", confidence=0.5, source="s")
        # M15 defaults must be untouched by M16.
        assert b.half_life_seconds == 86400.0
        assert b.ttl_seconds is None

    def test_worldmodel_defaults_unchanged(self):
        from friday.world.world_model import WorldModel

        sig = inspect.signature(WorldModel.__init__)
        assert sig.parameters["decay_rate"].default == 0.01
        assert sig.parameters["staleness_threshold"].default == 0.1

    def test_browsercontroller_and_research_defaults_unchanged(self):
        from friday.actions.browser_controller import BrowserController

        bc_sig = inspect.signature(BrowserController.__init__)
        assert bc_sig.parameters["remote_debug_port"].default == 9222
        assert bc_sig.parameters["require_real_chrome"].default is False

        r_sig = inspect.signature(research)
        assert r_sig.parameters["max_sources"].default == 3
        assert r_sig.parameters["max_chars_per_source"].default == 2500


# --------------------------------------------------------------------------- #
# Property 12 — backward-compatible signatures
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 12: Backward-compatible signatures


class TestProperty12BackwardCompatSignatures:
    """Validates: Requirements 3.3"""

    def test_research_accepts_legacy_positional_browser_shape(self):
        browser = _FakeBrowser(pages={"https://legacy.example.com/z": "legacy content"})
        ev = ExecutionEvidence()
        # Legacy positional call: research(query, browser, evidence)
        result = research("legacy query", browser, ev)
        assert isinstance(result, ResearchResult)

    def test_research_accepts_none_browser_with_kw_max_sources(self):
        ev = ExecutionEvidence()
        # research(query, None, evidence, max_sources=2) — under dry-run: blocked, no raise.
        result = research("legacy query", None, ev, max_sources=2)
        assert isinstance(result, ResearchResult)
        assert result.success is False

    def test_execute_research_accepts_legacy_call_shape(self):
        from friday.executor import GoalExecutor, ExecutionContext

        # Signature spot-check: (self, query, ctx).
        sig = inspect.signature(GoalExecutor._execute_research)
        assert list(sig.parameters)[1:] == ["query", "ctx"]

        executor = GoalExecutor()  # no browser -> dry-run browserless path
        ctx = ExecutionContext(goal="research the topic")
        out = executor._execute_research("research the topic", ctx)
        assert isinstance(out, str)
