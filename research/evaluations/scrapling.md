# Evaluation: Scrapling

**Tier**: 2 (MEDIUM-HIGH)
**Source**: https://github.com/D4Vinci/Scrapling (PyPI: scrapling 0.3.x)
**Date**: 2026-06-09
**Verdict**: Adopt for a future `research/` extraction subsystem. Deferred, low risk.

---

## What It Provides

Scrapling is a high-performance, adaptive Python web-scraping library
(rephrased for compliance):

- **Adaptive parser** — relocates elements after a site redesign by matching
  structural fingerprints (prior attributes + position), so scrapers keep
  working when class names / nesting change. Uses similarity algorithms, no
  LLM calls — works offline at scraping speed (`auto_save=True` records a
  structural profile).
- **Three fetcher classes**: HTTP fetcher (with browser TLS impersonation),
  Playwright-backed DynamicFetcher (JS-rendered pages), and StealthyFetcher
  (stealth Firefox for anti-bot).
- BeautifulSoup/Selectolax-like familiar API; Scrapy-style spider for crawls.

Sources: github.com/D4Vinci/Scrapling, scrapingbee.com, brightdata.com,
betterstack.com. *Content was rephrased for compliance with licensing
restrictions.*

## How FRIDAY Could Use It

- A `research/scraping/` subsystem for FRIDAY's research mode (Level 3 complex
  goals like "research laptops and build a spreadsheet").
- The adaptive parser is valuable: structural fingerprinting survives site
  redesigns, reducing maintenance vs brittle CSS selectors.
- Complements (does not replace) our DOM-via-DevTools browser automation:
  - Browser automation = interactive tasks (login, click, form fill, sessions)
  - Scrapling = bulk extraction / content harvesting for research

## Fit Assessment

| Criterion | Assessment |
|-----------|-----------|
| Capability | Strong for extraction; adaptive selectors reduce breakage |
| Reliability | Self-healing selectors improve long-term reliability |
| Maintainability | Pure-Python, pip-installable, familiar API — low friction |
| Scalability | Spider mode handles full crawls |
| UX | Enables research workflows that need multi-page extraction |
| Local-first | ✅ Runs locally, no hosted dependency |
| Overlap | Partial with our browser stack — but different use case |

## Important Distinction (per ADR-014)

The Research Integration Guide and 2026 best practice agree: for INTERACTIVE
browser tasks, live DOM/browser automation beats static scraping. Scrapling is
for EXTRACTION/RESEARCH, not for FRIDAY's interactive FRIDAY-mode actions.
Keep the boundary clear:
- FRIDAY-mode browser actions → DevTools/Playwright (interactive, verified)
- Research-mode bulk extraction → Scrapling (read-only harvesting)

## Recommendation

**Adopt later for a dedicated research subsystem.** Concretely:
1. Defer until Level 3 research workflows are prioritized.
2. When building `research/scraping/`, use Scrapling's adaptive parser +
   StealthyFetcher for content extraction.
3. Do NOT use Scrapling for interactive FRIDAY-mode actions (those stay on
   DevTools per ADR-014).
4. Gate behind an optional dependency (not in core requirements).

**Priority**: Medium-High when research mode is scheduled; otherwise deferred.
Clean fit, local-first, no architectural conflict.
