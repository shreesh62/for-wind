"""Research capability — gather real information from real sources.

NOT a ResearchPipeline. This is a reusable capability that:
1. Searches for the topic (via browser controller or desktop)
2. Opens actual result pages (not just the search results page)
3. Reads real content from those pages
4. Records source URLs + gathered text as evidence artifacts
5. Returns the gathered material so later steps can synthesize from it

The Evidence Law (ADR-023) requires that a "gather/research" requirement is
satisfied ONLY by real gathered info + source URLs. Generated text from an
LLM (without reading any page) can NEVER satisfy it. This capability is what
makes research requirements satisfiable honestly.

This is NOT an application-specific pipeline. The same capability works for:
- "research laptops" (consumer products)
- "France's position on X" (geopolitics)  
- "latest AI papers" (academic)
- "best restaurants nearby" (local)

It composes from: browser.search_web + browser.navigate + browser.read_text
+ evidence recording. Any goal that triggers a GATHER requirement runs this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.verification.evidence_law import ExecutionEvidence
from friday.verification.screenshot_evidence import is_blocked_page, capture_screenshot


@dataclass
class ResearchResult:
    """What the research capability actually gathered."""

    query: str
    sources_read: int = 0
    source_urls: List[str] = field(default_factory=list)
    gathered_text: str = ""
    blocked: bool = False
    error: str = ""

    @property
    def success(self) -> bool:
        return self.sources_read > 0 and bool(self.gathered_text.strip())


def research(
    query: str,
    browser_controller,
    evidence: ExecutionEvidence,
    *,
    max_sources: int = 3,
    max_chars_per_source: int = 2500,
) -> ResearchResult:
    """Execute real research: search → open pages → read → record evidence.

    Args:
        query: focused search query (already extracted from the goal)
        browser_controller: any object with search_web/navigate/read_text
                            (BrowserController or DesktopChromeController)
        evidence: the execution evidence bundle to populate
        max_sources: how many result links to actually open and read
        max_chars_per_source: text limit per page read

    Returns:
        ResearchResult describing what was actually gathered.
    """
    result = ResearchResult(query=query)

    if not browser_controller or not getattr(browser_controller, "available", False):
        result.error = "No browser available for research"
        return result

    # 1. SEARCH
    search_result = browser_controller.search_web(query)
    if not search_result.get("ok"):
        result.error = f"Search failed: {search_result.get('error', 'unknown')}"
        return result

    search_text = search_result.get("text", "")
    search_url = browser_controller.current_url() if hasattr(browser_controller, "current_url") else ""

    # Block detection on search results page
    if is_blocked_page(search_text, search_url):
        result.blocked = True
        result.error = "Search page is blocked (captcha/verification)"
        shot = capture_screenshot(label="research_search_blocked")
        if shot.is_real:
            evidence.add_screenshot(shot.path, shot.size, "research_search_blocked")
        return result

    # Record the search results themselves as gathered info
    if search_text.strip():
        evidence.add_gathered_info(search_text[:max_chars_per_source], source=f"search:{query}")
        result.gathered_text += f"[Search results for '{query}']\n{search_text[:max_chars_per_source]}\n\n"

    # 2. FOLLOW LINKS — open actual source pages
    links = search_result.get("links", [])
    urls_to_read = _select_best_links(links, max_sources)

    for url in urls_to_read:
        if not url or url in result.source_urls:
            continue

        nav = browser_controller.navigate(url)
        if not nav.get("ok"):
            continue

        landed_url = nav.get("url", url)

        # Read the page
        page_text = browser_controller.read_text(max_chars=max_chars_per_source)
        if not page_text or not page_text.strip():
            continue

        # Block detection on this page
        if is_blocked_page(page_text, landed_url):
            continue  # skip blocked pages, try the next one

        # Record as REAL evidence
        result.source_urls.append(landed_url)
        result.sources_read += 1
        result.gathered_text += f"[Source: {landed_url}]\n{page_text.strip()}\n\n"
        evidence.add_gathered_info(page_text, source=landed_url)
        evidence.add_source_url(landed_url)

    # Screenshot after research
    shot = capture_screenshot(label="research_complete")
    if shot.is_real:
        evidence.add_screenshot(shot.path, shot.size, "research_complete")

    return result


def _decode_ddg_redirect(href: str) -> str:
    """DuckDuckGo HTML results wrap targets in /l/?uddg=<encoded-url>.

    Decode them to the real destination so research can actually follow links
    (the old filter dropped every ddg redirect -> zero sources opened).
    """
    import urllib.parse as _up
    if "duckduckgo.com/l/" in href or href.startswith("//duckduckgo.com/l/"):
        try:
            q = _up.urlparse(href if href.startswith("http") else "https:" + href).query
            params = _up.parse_qs(q)
            if "uddg" in params:
                return _up.unquote(params["uddg"][0])
        except Exception:
            pass
    return href


def _select_best_links(links: List[Dict[str, str]], limit: int) -> List[str]:
    """Pick the most relevant/authoritative real source URLs to read.

    - Decodes DuckDuckGo redirect links to their true destinations.
    - Prefers official/primary domains, skips search-engine/social/ad domains.
    - Deduplicates by domain so we read diverse sources.
    """
    skip_domains = {"duckduckgo.com", "google.com", "bing.com",
                    "facebook.com", "twitter.com", "x.com", "tiktok.com",
                    "youtube.com", "pinterest.com"}
    prefer_domains = {".gov", ".edu", ".org", ".ac."}

    scored: List[tuple] = []
    seen_domains = set()
    for link in links:
        href = _decode_ddg_redirect(link.get("href", ""))
        if not href or not href.startswith("http"):
            continue
        parts = href.split("/")
        domain = parts[2] if len(parts) > 2 else ""
        if not domain or any(skip in domain for skip in skip_domains):
            continue
        if domain in seen_domains:
            continue  # one source per domain for diversity
        seen_domains.add(domain)
        score = 3 if any(pref in domain for pref in prefer_domains) else 1
        scored.append((score, href))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [url for _, url in scored[:limit]]
