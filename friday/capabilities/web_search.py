"""Browserless web search + gather — real information without a browser (M16).

The Playwright ``BrowserController`` is the only browser-based search path in the
codebase; when no controller is available (as in the capability benchmark) the
research path could gather nothing and every GATHER requirement went UNMET. This
module fills that gap with a plain-HTTP search + best-effort page read over the
already-present ``httpx`` dependency — no browser, no new dependency.

Design notes (see .kiro/specs/m16-research-competence/design.md):
- A general ``Search_Provider`` interface is expressed as an *ordered list of
  backend functions*; the DuckDuckGo hosts are module-level configuration DATA,
  never per-site conditional branching (Axiom 15).
- HTML is parsed with the standard library only (``html.parser`` / bounded regex);
  ``bs4``/``lxml`` are intentionally not used. ``uddg=`` redirects are decoded with
  the shared ``_decode_ddg_redirect`` helper from ``research.py`` (no duplication).
- All network I/O is gated by ``FRIDAY_DRY_RUN`` — under dry-run no client is
  constructed and no request is issued.
- Every error path degrades to a descriptive ``ResearchResult`` and never raises to
  the caller, so the Evidence Law remains the sole judge of a satisfied requirement.
- Gathered findings additionally become M15 World Model v2 beliefs (provenance from
  result URLs, freshness for recency), returned on ``ResearchResult.beliefs`` for a
  future kernel/world consumer to ingest.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable, List, Optional

from friday.capabilities.research import ResearchResult, _decode_ddg_redirect
from friday.verification.evidence_law import ExecutionEvidence

try:
    import httpx
except ImportError:  # pragma: no cover - exercised only when httpx is absent
    httpx = None  # type: ignore

# --- Search_Provider configuration DATA (NOT site-specific logic, Axiom 15) ---
_PRIMARY_HOST = "html.duckduckgo.com"   # POST form {"q": query}
_FALLBACK_HOST = "lite.duckduckgo.com"  # GET  ?q=query
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
# Research recency: findings are treated as fresh for ~6 hours (does not change the
# Belief default of 86400s).
RESEARCH_HALF_LIFE = 21600.0

# Upper bound on parsed hits regardless of body size (defensive).
_MAX_HITS = 25


@dataclass
class SearchHit:
    """One search result: a real destination URL, a snippet, and a title."""

    url: str
    snippet: str
    title: str = ""


@dataclass
class SearchOutcome:
    """Outcome of walking the provider list for a query."""

    hits: List[SearchHit]
    ok: bool
    error: str = ""
    host_used: str = ""


# --------------------------------------------------------------------------- #
# Parsing (stdlib only)
# --------------------------------------------------------------------------- #


class _DDGResultParser(HTMLParser):
    """Extract ``result__a`` links (+ text) and ``result__snippet`` text.

    Robust to malformed/adversarial markup: it only reads attributes and text, never
    executes anything, and never raises out of ``feed`` for well-formed-ish input.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hits: List[SearchHit] = []
        self._cur_href: Optional[str] = None
        self._in_anchor = False
        self._anchor_text_parts: List[str] = []
        self._in_snippet = False
        self._snippet_parts: List[str] = []
        self._pending_snippet = ""

    @staticmethod
    def _classes(attrs) -> str:
        for name, value in attrs:
            if name == "class" and value:
                return value
        return ""

    @staticmethod
    def _href(attrs) -> str:
        for name, value in attrs:
            if name == "href" and value:
                return value
        return ""

    def handle_starttag(self, tag: str, attrs) -> None:
        classes = self._classes(attrs)
        if tag == "a" and "result__a" in classes:
            self._in_anchor = True
            self._anchor_text_parts = []
            self._cur_href = _decode_ddg_redirect(self._href(attrs))
        elif "result__snippet" in classes:
            self._in_snippet = True
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            self._anchor_text_parts.append(data)
        if self._in_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_anchor:
            self._in_anchor = False
            title = "".join(self._anchor_text_parts).strip()
            url = self._cur_href or ""
            # Attach the most recent snippet if one was seen just before/after.
            snippet = self._pending_snippet
            self._pending_snippet = ""
            self.hits.append(SearchHit(url=url, snippet=snippet, title=title))
            self._cur_href = None
        elif self._in_snippet:
            # A snippet may close before or after its anchor; buffer it and also
            # backfill the most recent hit that has no snippet yet.
            self._in_snippet = False
            text = "".join(self._snippet_parts).strip()
            if text:
                backfilled = False
                for hit in reversed(self.hits):
                    if not hit.snippet:
                        hit.snippet = text
                        backfilled = True
                        break
                if not backfilled:
                    self._pending_snippet = text


def parse_ddg_html(body: str) -> List[SearchHit]:
    """Parse a DuckDuckGo HTML results body into a bounded list of ``SearchHit``.

    Uses the standard-library HTML parser. A body with no result markers yields an
    empty list. Adversarial/malformed markup is handled as text only and never
    raises. The total number of hits is bounded by ``_MAX_HITS``.
    """
    if not body:
        return []
    parser = _DDGResultParser()
    try:
        parser.feed(body)
        parser.close()
    except Exception:
        # Fall back to a bounded regex sweep on parser failure; never raise.
        return _regex_fallback(body)
    hits = [h for h in parser.hits if (h.url or h.snippet or h.title)]
    if not hits:
        hits = _regex_fallback(body)
    return hits[:_MAX_HITS]


_ANCHOR_RE = re.compile(
    r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _regex_fallback(body: str) -> List[SearchHit]:
    """Bounded regex extraction of result anchors — a defensive parser fallback."""
    hits: List[SearchHit] = []
    for match in _ANCHOR_RE.finditer(body):
        if len(hits) >= _MAX_HITS:
            break
        href = _decode_ddg_redirect(match.group(1) or "")
        title = _TAG_RE.sub("", match.group(2) or "").strip()
        hits.append(SearchHit(url=href, snippet="", title=title))
    return hits


# --------------------------------------------------------------------------- #
# Search_Provider backends (ordered) + http_search
# --------------------------------------------------------------------------- #


def _search_html_ddg(
    query: str, *, timeout: float, max_results: int, client
) -> List[SearchHit]:
    """Primary backend: POST form ``{"q": query}`` to the HTML endpoint."""
    resp = client.post(
        f"https://{_PRIMARY_HOST}/html/",
        data={"q": query},
        headers={"User-Agent": _USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
    )
    if resp.status_code != 200:
        return []
    return parse_ddg_html(resp.text)[:max_results]


def _search_lite_ddg(
    query: str, *, timeout: float, max_results: int, client
) -> List[SearchHit]:
    """Fallback backend: GET the lite endpoint with ``?q=query``."""
    resp = client.get(
        f"https://{_FALLBACK_HOST}/lite/",
        params={"q": query},
        headers={"User-Agent": _USER_AGENT},
        timeout=timeout,
        follow_redirects=True,
    )
    if resp.status_code != 200:
        return []
    return parse_ddg_html(resp.text)[:max_results]


_WIKIPEDIA_HOST = "en.wikipedia.org"  # OpenSearch API — resilient, no scrape-throttle
# Wikimedia's robot policy requires a descriptive User-Agent with contact info;
# a generic browser UA is 403'd. Overridable via FRIDAY_CONTACT for real deploys.
_WIKI_USER_AGENT = "FRIDAY-Operator/1.0 (https://example.com/friday; contact: friday@example.com)"


def _search_wikipedia(
    query: str, *, timeout: float, max_results: int, client
) -> List[SearchHit]:
    """Resilient fallback: the Wikipedia OpenSearch API (a general public-information
    source). Returns real article URLs with titles. Not scraper-throttled and needs
    no API key, so it keeps research working when HTML search engines rate-limit.

    This is a DATA-driven provider entry, not task-specific logic (Axiom 15).
    """
    resp = client.get(
        f"https://{_WIKIPEDIA_HOST}/w/api.php",
        params={
            "action": "opensearch", "search": query,
            "limit": str(max_results), "namespace": "0", "format": "json",
        },
        headers={"User-Agent": _WIKI_USER_AGENT, "Accept": "application/json"},
        timeout=timeout,
        follow_redirects=True,
    )
    if resp.status_code != 200:
        return []
    try:
        data = resp.json()  # [query, [titles], [descriptions], [urls]]
    except Exception:
        return []
    titles = data[1] if len(data) > 1 and isinstance(data[1], list) else []
    descs = data[2] if len(data) > 2 and isinstance(data[2], list) else []
    urls = data[3] if len(data) > 3 and isinstance(data[3], list) else []
    hits: List[SearchHit] = []
    for i, url in enumerate(urls):
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        hits.append(SearchHit(
            url=url,
            snippet=descs[i] if i < len(descs) and isinstance(descs[i], str) else "",
            title=titles[i] if i < len(titles) and isinstance(titles[i], str) else "",
        ))
    return hits[:max_results]


# Ordered provider list — general interface, hosts are DATA not branching. The
# Wikipedia OpenSearch API is the resilient fallback when HTML engines throttle.
_PROVIDERS: List[Callable[..., List[SearchHit]]] = [
    _search_html_ddg, _search_lite_ddg, _search_wikipedia,
]

# Backend -> host label, for reporting host_used without per-site branching.
_PROVIDER_HOSTS = {
    _search_html_ddg: _PRIMARY_HOST,
    _search_lite_ddg: _FALLBACK_HOST,
    _search_wikipedia: _WIKIPEDIA_HOST,
}


def http_search(
    query: str, *, timeout: float = 10.0, max_results: int = 10
) -> SearchOutcome:
    """Walk the provider list in order; first provider with >=1 hit wins.

    A provider returning non-200 or raising a transport error is skipped and the
    next is tried. If every provider fails, ``ok=False`` with a descriptive error.
    Never raises to the caller.
    """
    if httpx is None:
        return SearchOutcome(hits=[], ok=False, error="httpx unavailable")

    errors: List[str] = []
    try:
        with httpx.Client() as client:
            for provider in _PROVIDERS:
                host = _PROVIDER_HOSTS.get(provider, "")
                try:
                    hits = provider(
                        query, timeout=timeout, max_results=max_results, client=client
                    )
                except Exception as exc:  # transport / parse error -> try next
                    errors.append(f"{host}: {type(exc).__name__}: {exc}")
                    continue
                if hits:
                    return SearchOutcome(
                        hits=hits, ok=True, host_used=host
                    )
                errors.append(f"{host}: no results")
    except Exception as exc:  # pragma: no cover - client construction failure
        return SearchOutcome(
            hits=[], ok=False, error=f"search client error: {type(exc).__name__}: {exc}"
        )

    return SearchOutcome(
        hits=[], ok=False,
        error="all search providers failed: " + "; ".join(errors) if errors
        else "all search providers failed",
    )


# --------------------------------------------------------------------------- #
# Belief production (M15)
# --------------------------------------------------------------------------- #


def _build_beliefs(query: str, findings, source_urls, *, max_sources: int):
    """Build up to ``max_sources`` beliefs from recorded findings.

    Each belief carries research recency (``observed_at=now``,
    ``half_life_seconds=RESEARCH_HALF_LIFE``) and provenance from the supporting
    result URLs. Empty findings yield an empty list.
    """
    from friday.world.belief import Belief

    beliefs = []
    now = time.time()
    for text in findings[:max_sources]:
        if not text or not text.strip():
            continue
        belief = Belief(
            description=f"Research finding for '{query}': {text[:200]}",
            confidence=0.5,  # unverified web finding
            source="browserless_gather",
            observed_at=now,
            half_life_seconds=RESEARCH_HALF_LIFE,
        )
        for url in source_urls:
            belief = belief.add_supporting_observation(url)
        beliefs.append(belief)
    return beliefs


# --------------------------------------------------------------------------- #
# gather
# --------------------------------------------------------------------------- #


def gather(
    query: str,
    evidence: ExecutionEvidence,
    *,
    max_sources: int = 3,
    max_chars_per_source: int = 2500,
    timeout: float = 10.0,
) -> ResearchResult:
    """Browserless search + best-effort page read + evidence + belief production.

    Behavior:
    1. Dry-run: if ``FRIDAY_DRY_RUN == "1"`` return a blocked/empty result with NO
       client construction and NO network call.
    2. Search via ``http_search``; on total failure return a descriptive result.
    3. Record each non-empty snippet (bounded) and each result URL as evidence.
    4. Best-effort GET up to ``max_sources`` result pages; record 200 body text
       (bounded); skip non-200/403/errors.
    5. Build M15 beliefs from findings and attach to ``ResearchResult.beliefs``.

    Never raises to the caller.
    """
    result = ResearchResult(query=query)

    # 1. Dry-run: no client, no network.
    if os.environ.get("FRIDAY_DRY_RUN", "0") == "1":
        result.error = "dry-run: no network"
        result.blocked = True
        return result

    # 2. Search.
    outcome = http_search(query, timeout=timeout, max_results=max(max_sources * 2, 6))
    if not outcome.ok or not outcome.hits:
        result.error = outcome.error or "no results"
        return result

    findings: List[str] = []

    # 3. Record snippets + source URLs from the search results page.
    for hit in outcome.hits:
        snippet = hit.snippet.strip() if hit.snippet else ""
        if snippet:
            source = hit.url or f"search:{query}"
            bounded = snippet[:max_chars_per_source]
            evidence.add_gathered_info(bounded, source=source)
            result.gathered_text += f"[{source}]\n{bounded}\n\n"
            result.sources_read += 1
            findings.append(bounded)
        if hit.url:
            evidence.add_source_url(hit.url)
            if hit.url not in result.source_urls:
                result.source_urls.append(hit.url)

    # 4. Best-effort page fetch (bounded count). Untrusted -> text only, never exec.
    fetch_urls = [h.url for h in outcome.hits if h.url][:max_sources]
    if fetch_urls and httpx is not None:
        try:
            with httpx.Client() as client:
                for url in fetch_urls:
                    try:
                        resp = client.get(
                            url,
                            headers={"User-Agent": _USER_AGENT},
                            timeout=timeout,
                            follow_redirects=True,
                        )
                    except Exception:
                        continue  # skip non-reachable page, keep going
                    if resp.status_code != 200:
                        continue
                    page_text = _extract_text(resp.text)
                    if not page_text:
                        continue
                    bounded = page_text[:max_chars_per_source]
                    evidence.add_gathered_info(bounded, source=url)
                    result.gathered_text += f"[Source: {url}]\n{bounded}\n\n"
                    result.sources_read += 1
                    findings.append(bounded)
        except Exception:  # pragma: no cover - client construction failure
            pass

    # 5. Beliefs from findings (provenance + freshness).
    if findings:
        result.beliefs = _build_beliefs(
            query, findings, result.source_urls, max_sources=max_sources
        )

    return result


_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)


def _extract_text(body: str) -> str:
    """Extract visible text from an untrusted HTML body — data only, never executed.

    Strips script/style blocks and tags with bounded regex, collapses whitespace.
    Never raises.
    """
    if not body:
        return ""
    try:
        stripped = _SCRIPT_STYLE_RE.sub(" ", body)
        text = _TAG_RE.sub(" ", stripped)
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return ""
