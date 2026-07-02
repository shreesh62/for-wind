"""Tests for the honest research capability (M3).

Proves: research actually opens pages, records source URLs as evidence,
handles blocked pages gracefully, and never fabricates gathered info.
"""

from __future__ import annotations

import pytest

from friday.capabilities.research import research, ResearchResult, _select_best_links
from friday.verification.evidence_law import ExecutionEvidence, EvidenceKind


class FakeBrowser:
    """Fake browser that simulates controllable search + navigate + read."""

    def __init__(self, search_ok=True, pages=None, blocked_pages=None):
        self.available = True
        self._search_ok = search_ok
        self._pages = pages or {}        # url -> text
        self._blocked = set(blocked_pages or [])
        self._current_url = ""
        self.navigated = []

    def search_web(self, query):
        if not self._search_ok:
            return {"ok": False, "error": "search failed"}
        links = [{"text": f"Result {i}", "href": url} for i, url in enumerate(self._pages.keys())]
        return {"ok": True, "text": f"Search results for {query}", "links": links}

    def navigate(self, url):
        self.navigated.append(url)
        self._current_url = url
        if url in self._blocked:
            return {"ok": True, "url": url}
        if url in self._pages:
            return {"ok": True, "url": url}
        return {"ok": False, "error": "not found"}

    def read_text(self, max_chars=4000):
        if self._current_url in self._blocked:
            return "unusual traffic detected captcha"
        return self._pages.get(self._current_url, "")[:max_chars]

    def current_url(self):
        return self._current_url


class TestResearchCapability:
    def test_reads_real_pages_and_records_evidence(self):
        browser = FakeBrowser(pages={
            "https://pcmag.com/laptops": "Best laptops 2026: Lenovo ThinkPad...",
            "https://techradar.com/best": "Top 10 laptops for students...",
        })
        evidence = ExecutionEvidence()
        result = research("best laptops", browser, evidence, max_sources=3)

        assert result.success is True
        assert result.sources_read >= 1
        assert len(result.source_urls) >= 1
        # Evidence must have real gathered info + source URLs
        assert evidence.has(EvidenceKind.GATHERED_INFO)
        assert evidence.has(EvidenceKind.SOURCE_URL)

    def test_no_browser_returns_honest_failure(self):
        evidence = ExecutionEvidence()
        result = research("anything", None, evidence)
        assert result.success is False
        assert "no browser" in result.error.lower()
        assert not evidence.has(EvidenceKind.GATHERED_INFO)

    def test_blocked_page_skipped_gracefully(self):
        browser = FakeBrowser(
            pages={
                "https://good.com/article": "Real content about laptops",
                "https://blocked.com/page": "captcha verify human",
            },
            blocked_pages=["https://blocked.com/page"],
        )
        evidence = ExecutionEvidence()
        result = research("laptops", browser, evidence, max_sources=3)

        # Should still succeed by reading the non-blocked page
        assert result.success is True
        assert "https://good.com/article" in result.source_urls
        assert "https://blocked.com/page" not in result.source_urls

    def test_search_failure_returns_honest_error(self):
        browser = FakeBrowser(search_ok=False)
        evidence = ExecutionEvidence()
        result = research("anything", browser, evidence)
        assert result.success is False
        assert "search failed" in result.error.lower()


class TestLinkSelection:
    def test_prefers_official_domains(self):
        links = [
            {"href": "https://facebook.com/post"},
            {"href": "https://gov.uk/policy"},
            {"href": "https://random.com/article"},
        ]
        selected = _select_best_links(links, limit=2)
        assert "https://gov.uk/policy" in selected
        assert "https://facebook.com/post" not in selected

    def test_skips_search_engine_domains(self):
        links = [
            {"href": "https://duckduckgo.com/something"},
            {"href": "https://real-site.com/article"},
        ]
        selected = _select_best_links(links, limit=5)
        assert "https://duckduckgo.com/something" not in selected
        assert "https://real-site.com/article" in selected

    def test_decodes_duckduckgo_redirect(self):
        """DDG wraps real URLs in /l/?uddg= — must decode, not drop."""
        links = [
            {"href": "//duckduckgo.com/l/?uddg=https%3A%2F%2Fpython.org%2Fabout&rut=x"},
        ]
        selected = _select_best_links(links, limit=3)
        assert selected == ["https://python.org/about"]

    def test_dedupes_by_domain(self):
        links = [
            {"href": "https://site.com/a"},
            {"href": "https://site.com/b"},
            {"href": "https://other.com/c"},
        ]
        selected = _select_best_links(links, limit=5)
        domains = [u.split("/")[2] for u in selected]
        assert len(domains) == len(set(domains))  # no dup domains
