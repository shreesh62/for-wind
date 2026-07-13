"""M16 — Research Competence: Hypothesis property tests (P1-P10, P13).

Every test MOCKS the HTTP layer (``friday.capabilities.web_search.httpx``) so the
suite makes ZERO live network calls. The root conftest forces ``FRIDAY_DRY_RUN=1``;
non-dry-run paths are exercised by locally patching ``os.environ`` AND a spy httpx so
no real request ever occurs.

Design source: .kiro/specs/m16-research-competence/design.md (Correctness Properties).
"""

from __future__ import annotations

import os
import string
import time
import urllib.parse
from unittest import mock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import friday.capabilities.web_search as web_search
from friday.capabilities.web_search import (
    RESEARCH_HALF_LIFE,
    SearchHit,
    gather,
    http_search,
    parse_ddg_html,
    _MAX_HITS,
)
from friday.verification.evidence_law import (
    EvidenceKind,
    EvidenceVerifier,
    ExecutionEvidence,
)

_LETTERS = string.ascii_letters + string.digits
_LOWER = string.ascii_lowercase


# --------------------------------------------------------------------------- #
# Fake httpx (spy) — intercepts .post/.get, returns fake responses. No real I/O.
# --------------------------------------------------------------------------- #


class _Resp:
    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _SpyClient:
    def __init__(self, handler) -> None:
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
    """Stands in for the ``httpx`` module — only exposes ``Client``."""

    def __init__(self, handler) -> None:
        self._handler = handler
        self.clients = []

    def Client(self, *a, **kw):
        c = _SpyClient(self._handler)
        self.clients.append(c)
        return c

    @property
    def call_count(self) -> int:
        return sum(len(c.calls) for c in self.clients)

    def calls(self):
        return [c for client in self.clients for c in client.calls]


def _make_handler(search_html, *, page_status=200, page_text="<html>page body text here</html>",
                  raise_page_urls=(), page_status_map=None):
    """Build a request handler. DDG hosts -> search html; other urls -> page."""
    page_status_map = page_status_map or {}

    def handler(method, url, kw):
        low = url.lower()
        if "duckduckgo.com" in low:
            return _Resp(200, search_html)
        if url in raise_page_urls:
            raise RuntimeError("simulated transport error")
        status = page_status_map.get(url, page_status)
        return _Resp(status, page_text)

    return handler


def _patch(spy, dry_run="0"):
    """Context: patch web_search.httpx + FRIDAY_DRY_RUN together."""
    return _CombinedPatch(spy, dry_run)


class _CombinedPatch:
    def __init__(self, spy, dry_run):
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
# HTML builders
# --------------------------------------------------------------------------- #


def _mk_results_html(hits):
    """hits: list of (href, snippet, title) -> a DDG-style results body."""
    blocks = []
    for href, snippet, title in hits:
        b = f'<div class="result"><a class="result__a" href="{href}">{title}</a>'
        if snippet:
            b += f'<div class="result__snippet">{snippet}</div>'
        b += "</div>"
        blocks.append(b)
    return "<html><body>" + "".join(blocks) + "</body></html>"


# Constant valid search body with hits (for dry-run-inactive request counting).
SEARCH_HTML = _mk_results_html([
    ("https://a.example.com/x", "alpha snippet", "Alpha"),
    ("https://b.example.com/y", "beta snippet", "Beta"),
])


# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #

_dest_url = st.builds(
    lambda h, p: f"https://{h}.example.com/{p}",
    st.text(_LOWER, min_size=1, max_size=8),
    st.text(_LOWER + string.digits, min_size=0, max_size=8),
)


@st.composite
def _p1_block(draw):
    """A single result block with a bare/wrapped/empty href (Property 1)."""
    dest = draw(_dest_url)
    variant = draw(st.sampled_from(["bare", "wrapped", "empty"]))
    if variant == "bare":
        href = dest
    elif variant == "wrapped":
        href = "//duckduckgo.com/l/?uddg=" + urllib.parse.quote(dest, safe="") + "&rut=1"
    else:
        href = ""
    title = draw(st.text(_LETTERS, max_size=15))
    snippet = draw(st.one_of(st.none(), st.text(_LETTERS, min_size=1, max_size=20)))
    b = f'<div class="result"><a class="result__a" href="{href}">{title}</a>'
    if snippet is not None:
        b += f'<div class="result__snippet">{snippet}</div>'
    b += "</div>"
    return b


# hits with a real URL + non-empty snippet
_good_hit = st.tuples(
    _dest_url,
    st.text(_LETTERS + " ", min_size=1, max_size=40).filter(lambda s: s.strip()),
    st.text(_LETTERS, max_size=15),
)
_good_hits = st.lists(_good_hit, min_size=1, max_size=5, unique_by=lambda t: t[0])

# hits where url may be empty (Property 3)
_maybe_hit = st.tuples(
    st.one_of(_dest_url, st.just("")),
    st.text(_LETTERS, max_size=30),
    st.text(_LETTERS, max_size=15),
)
_maybe_hits = st.lists(_maybe_hit, min_size=1, max_size=6)

# adversarial body fragments (Property 13)
_adv_frag = st.sampled_from([
    "<script>alert('x')</script>",
    "<script>while(true){}",
    "<style>body{color:red}</style>",
    "<div class='result__a'",
    "<<>><a href=",
    "\x00\x01\x02\x1f control chars",
    '</html><a class="result__a" href="x">malformed',
    "plain visible text",
    "<img src=x onerror=1>",
])
_adv_body = st.lists(_adv_frag, max_size=8).map("".join)


# --------------------------------------------------------------------------- #
# Property 1
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 1: Search-results parsing extracts
# bounded, well-formed records
@settings(max_examples=100, deadline=None)
@given(st.lists(_p1_block(), max_size=12))
def test_property1_parse_bounded_and_wellformed(blocks):
    """Validates: Requirements 1.3, 2.1, 2.2"""
    body = "<html><body>" + "".join(blocks) + "</body></html>"
    hits = parse_ddg_html(body)

    # Bounded: at most one record per result block (and never above the hard cap).
    assert len(hits) <= len(blocks)
    assert len(hits) <= _MAX_HITS

    # Zero result markers -> empty list.
    if not blocks:
        assert hits == []

    # Every URL is either empty or a decoded (non-uddg-wrapped) destination.
    for h in hits:
        assert "uddg=" not in h.url
        assert "/l/?" not in h.url


def test_property1_no_markers_yields_empty():
    """Explicit zero-marker / empty-body cases (Property 1)."""
    assert parse_ddg_html("") == []
    assert parse_ddg_html("<html><body>nothing to see here</body></html>") == []


# --------------------------------------------------------------------------- #
# Property 4
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 4: Dry-run performs zero network calls
@settings(max_examples=100, deadline=None)
@given(query=st.text(max_size=25))
def test_property4_dry_run_zero_calls(query):
    """Validates: Requirements 1.1, 4.1, 4.2, 5.5"""
    # Dry-run active -> ZERO requests, blocked result.
    spy = _SpyHttpx(_make_handler(SEARCH_HTML))
    with _patch(spy, dry_run="1"):
        ev = ExecutionEvidence()
        res = gather(query, ev)
    assert spy.call_count == 0
    assert res.blocked is True
    assert not ev.has(EvidenceKind.GATHERED_INFO)

    # Dry-run inactive + non-empty query -> at least one request issued (via spy).
    if query.strip():
        spy2 = _SpyHttpx(_make_handler(SEARCH_HTML))
        with _patch(spy2, dry_run="0"):
            gather(query, ExecutionEvidence())
        assert spy2.call_count >= 1


# --------------------------------------------------------------------------- #
# Property 2
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 2: Evidence recording invariant
# (Evidence Law satisfied)
@settings(max_examples=100, deadline=None)
@given(hits=_good_hits, query=st.text(_LETTERS + " ", min_size=1, max_size=20))
def test_property2_evidence_recording_invariant(hits, query):
    """Validates: Requirements 2.1, 2.2, 2.3, 3.1, 3.4, 7.4"""
    urls = {h[0] for h in hits}
    html = _mk_results_html(hits)
    spy = _SpyHttpx(_make_handler(html, page_text="<html>real page text body</html>"))
    with _patch(spy, dry_run="0"):
        ev = ExecutionEvidence()
        gather(query, ev, max_sources=3, max_chars_per_source=2000)

    gathered = ev.of_kind(EvidenceKind.GATHERED_INFO)
    sources = ev.of_kind(EvidenceKind.SOURCE_URL)
    assert gathered, "expected >=1 GATHERED_INFO artifact"
    assert sources, "expected >=1 SOURCE_URL artifact"

    allowed = set(urls) | {f"search:{query}"}
    for art in gathered:
        assert art.source, "GATHERED_INFO must carry a source"
        assert art.source in allowed

    # EvidenceVerifier marks a GATHER requirement satisfied.
    verdict = EvidenceVerifier().verify_one(
        "research and gather information about the topic", ev
    )
    assert verdict.satisfied is True


# --------------------------------------------------------------------------- #
# Property 3
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 3: Only real gathered text is recorded
# (no generated text)
@settings(max_examples=100, deadline=None)
@given(hits=_maybe_hits, query=st.text(_LETTERS, min_size=1, max_size=20))
def test_property3_only_real_gathered_text(hits, query):
    """Validates: Requirements 2.4, 3.4"""
    urls = {h[0] for h in hits if h[0]}
    html = _mk_results_html(hits)
    spy = _SpyHttpx(_make_handler(html, page_text="<html>fetched page text</html>"))
    with _patch(spy, dry_run="0"):
        ev = ExecutionEvidence()
        gather(query, ev, max_sources=3)

    allowed = set(urls) | {f"search:{query}"}
    for art in ev.of_kind(EvidenceKind.GATHERED_INFO):
        # Every source traces to a result/page URL or the search query — never model text.
        assert art.source in allowed


# --------------------------------------------------------------------------- #
# Property 7
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 7: Page-fetch enrichment is monotonic
@settings(max_examples=100, deadline=None)
@given(hits=_good_hits, query=st.text(_LETTERS, min_size=1, max_size=15))
def test_property7_page_fetch_enrichment_monotonic(hits, query):
    """Validates: Requirements 2.5, 2.7"""
    urls = [h[0] for h in hits]
    html = _mk_results_html(hits)

    # Run WITHOUT page enrichment (pages 404) -> snippet-only baseline.
    spy0 = _SpyHttpx(_make_handler(html, page_status=404))
    with _patch(spy0, dry_run="0"):
        ev0 = ExecutionEvidence()
        gather(query, ev0, max_sources=3)
    count_before = len(ev0.of_kind(EvidenceKind.GATHERED_INFO))

    # Run WITH page enrichment (pages 200 + text).
    spy1 = _SpyHttpx(_make_handler(html, page_status=200,
                                   page_text="<html>enriched page body</html>"))
    with _patch(spy1, dry_run="0"):
        ev1 = ExecutionEvidence()
        gather(query, ev1, max_sources=3)
    count_after = len(ev1.of_kind(EvidenceKind.GATHERED_INFO))

    # Monotonic: fetching can only add artifacts.
    assert count_after >= count_before
    # With fetchable urls, enrichment strictly adds page-sourced artifacts.
    fetched = urls[:3]
    if fetched:
        assert count_after > count_before
        assert any(a.source in fetched for a in ev1.of_kind(EvidenceKind.GATHERED_INFO))


# --------------------------------------------------------------------------- #
# Property 8
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 8: Bounded reads and bounded fetches
@settings(max_examples=100, deadline=None)
@given(
    n=st.integers(min_value=1, max_value=8),
    max_sources=st.integers(min_value=1, max_value=3),
    max_chars=st.integers(min_value=10, max_value=120),
    query=st.text(_LETTERS, min_size=1, max_size=15),
)
def test_property8_bounded_reads_and_fetches(n, max_sources, max_chars, query):
    """Validates: Requirements 4.4, 4.5"""
    # Result set larger than the limit, each with an oversized snippet.
    big_snip = "S" * (max_chars * 5 + 50)
    hits = [(f"https://s{i}.example.com/p", big_snip, f"T{i}") for i in range(n + max_sources)]
    html = _mk_results_html(hits)
    big_page = "<html>" + ("P" * (max_chars * 6 + 100)) + "</html>"
    spy = _SpyHttpx(_make_handler(html, page_text=big_page))

    with _patch(spy, dry_run="0"):
        ev = ExecutionEvidence()
        gather(query, ev, max_sources=max_sources, max_chars_per_source=max_chars)

    # Bounded reads: no single recorded artifact exceeds the char cap.
    for art in ev.of_kind(EvidenceKind.GATHERED_INFO):
        assert art.value <= max_chars

    # Bounded fetches: at most max_sources result pages fetched (non-DDG GETs).
    page_gets = [c for c in spy.calls()
                 if c[0] == "GET" and "duckduckgo.com" not in c[1].lower()]
    assert len(page_gets) <= max_sources


# --------------------------------------------------------------------------- #
# Property 13
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 13: Untrusted content is handled as
# data only
@settings(max_examples=100, deadline=None)
@given(body=_adv_body, query=st.text(_LETTERS, min_size=1, max_size=15))
def test_property13_untrusted_content_is_data_only(body, query):
    """Validates: Requirements 4.3"""
    # Parsing adversarial markup never raises.
    hits = parse_ddg_html(body)
    assert isinstance(hits, list)

    # Text extraction never raises and never leaks script/style tags.
    extracted = web_search._extract_text(body)
    assert isinstance(extracted, str)
    low = extracted.lower()
    assert "<script>" not in low and "</script>" not in low
    assert "<style>" not in low and "</style>" not in low

    # gather over adversarial page bodies: no raise, no script leak in gathered text.
    clean_html = _mk_results_html([("https://ok.example.com/a", "clean snippet", "OK")])
    spy = _SpyHttpx(_make_handler(clean_html, page_text=body))
    with _patch(spy, dry_run="0"):
        ev = ExecutionEvidence()
        res = gather(query, ev, max_sources=2)
    assert "<script>" not in res.gathered_text.lower()


# --------------------------------------------------------------------------- #
# Property 10
# --------------------------------------------------------------------------- #
# Feature: m16-research-competence, Property 10: Gathered findings produce beliefs
# with provenance and freshness
@settings(max_examples=100, deadline=None)
@given(hits=_good_hits, query=st.text(_LETTERS + " ", min_size=1, max_size=20))
def test_property10_beliefs_provenance_and_freshness(hits, query):
    """Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5"""
    html = _mk_results_html(hits)
    spy = _SpyHttpx(_make_handler(html, page_status=404))  # snippet-only findings
    before = time.time()
    with _patch(spy, dry_run="0"):
        ev = ExecutionEvidence()
        res = gather(query, ev, max_sources=3)
    after = time.time()

    assert len(res.beliefs) >= 1
    for belief in res.beliefs:
        # Provenance carries each supporting result URL.
        for url in res.source_urls:
            assert url in belief.provenance.supporting_observations
        # Recency: observed_at reflects gather time.
        assert before - 1.0 <= belief.observed_at <= after + 1.0
        # Research freshness constant.
        assert belief.half_life_seconds == RESEARCH_HALF_LIFE
