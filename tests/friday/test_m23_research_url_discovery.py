"""M23 — research discovers real source URLs on the DOM-less desktop path.

Feature: m23-browser-generic-desktop-environment

A desktop/OCR controller returns no result links, so research must discover real
source URLs via the browserless search and then operate the real browser to
open+read them — recording SOURCE_URL, GATHERED_INFO, and a real NAVIGATION.
Hermetic: fake controller + mocked browserless http_search (no network).
"""

import friday.capabilities.web_search as web_search
from friday.capabilities.research import research
from friday.verification.evidence_law import EvidenceKind, ExecutionEvidence


class _Hit:
    def __init__(self, url):
        self.url = url


class _Outcome:
    def __init__(self, hits):
        self.hits = hits


class _DesktopCtrl:
    """DOM-less controller: search yields OCR text but NO usable links."""

    available = True

    def __init__(self):
        self.navigated = []

    def search_web(self, query):
        return {"ok": True, "text": "OCR of the results page " * 4, "links": []}

    def current_url(self):
        return "https://duckduckgo.com/html/?q=x"

    def navigate(self, url):
        self.navigated.append(url)
        return {"ok": True, "url": url}

    def read_text(self, max_chars=2500):
        return "Real content about the topic, several sentences long. " * 6


def test_desktop_research_discovers_urls_and_records_navigation(monkeypatch):
    # Validates: Requirements 8.3 (navigate/search evidence via desktop pipeline)
    monkeypatch.setattr(
        web_search, "http_search",
        lambda q, **k: _Outcome([_Hit("https://alpha.example/a"),
                                 _Hit("https://beta.example/b")]),
    )
    ctrl = _DesktopCtrl()
    ev = ExecutionEvidence()
    result = research("real topic", ctrl, ev, max_sources=2)

    # The desktop browser actually navigated to the discovered real URLs.
    assert ctrl.navigated == ["https://alpha.example/a", "https://beta.example/b"]
    assert result.sources_read == 2

    srcs = {a.detail for a in ev.of_kind(EvidenceKind.SOURCE_URL)}
    assert srcs == {"https://alpha.example/a", "https://beta.example/b"}
    navs = {a.detail for a in ev.of_kind(EvidenceKind.NAVIGATION)}
    assert navs == {"https://alpha.example/a", "https://beta.example/b"}
    assert ev.has(EvidenceKind.GATHERED_INFO)


def test_desktop_research_no_results_records_no_fake_evidence(monkeypatch):
    # When browserless discovery yields nothing (e.g. throttled), no SOURCE_URL /
    # NAVIGATION is fabricated — hard verification stays honest.
    monkeypatch.setattr(web_search, "http_search", lambda q, **k: _Outcome([]))
    ctrl = _DesktopCtrl()
    ev = ExecutionEvidence()
    result = research("real topic", ctrl, ev, max_sources=3)
    assert result.sources_read == 0
    assert ev.of_kind(EvidenceKind.SOURCE_URL) == []
    assert ev.of_kind(EvidenceKind.NAVIGATION) == []
