# Evaluation: Open Browser Use / Browser Agents

**Tier**: 1 (HIGH)
**Sources**:
- Browser Use (78,000+ GitHub stars per firecrawl.dev)
- Stagehand, Notte browser-agent stack analyses (notte.cc, browserless.io)
**Date**: 2026-06-09
**Verdict**: Study architecture patterns. Do NOT replace FRIDAY's browser stack.

---

## What It Provides

Browser agent libraries handle the "reasoning loop" for browser automation.
The 2026 browser automation stack splits into layers (rephrased for compliance):

- **Agent libraries** (Browser Use, Stagehand) — the reasoning loop:
  interpret goal → observe page → decide next action → act.
- **Cloud browser providers** (Browserbase, Steel, Hyperbrowser) — run Chromium.
- **Web data layers** (Firecrawl) — return clean structured pages.

The classic loop is **observe → think → act**: set a goal, the agent sees the
page, reasons about the next step, then acts — like a careful remote intern.

A key 2026 insight: browser automation (live DOM/page state) is more reliable
than static scraping because scrapers return static HTML that breaks on site
updates and can't handle login sessions or incomplete page state.

Sources: notte.cc, firecrawl.dev, skywork.ai, roborhythms.com.
*Content was rephrased for compliance with licensing restrictions.*

## How FRIDAY Compares

FRIDAY ALREADY implements the observe→think→act→**verify** loop:
- Observe: `FridayEngine.perceive()` builds WorldState (DOM via DevTools)
- Plan: `planner/` goal parser + task decomposer
- Act: `actions/browser.py` (DOM-first, ADR-014)
- Verify: `verification/verifier.py` (we add this step beyond their loop)
- Repair: `planner/replanner.py`

**FRIDAY's differentiators vs typical browser agents:**
- Explicit **verification** step with evidence (most agents skip this)
- **Semantic-first** perception priority (ADR-014) — DOM > UIA > OCR > Vision
- Desktop AND browser (most browser agents are browser-only)
- Local-control + cloud-reasoning split

## What's Worth Borrowing

| Pattern | Borrow? | Notes |
|---------|---------|-------|
| Observe→think→act loop | Already have it (+verify) | — |
| DOM-over-screenshot preference | Already ADR-014 | Validates our decision |
| Goal → action decomposition | Already have planner | Compare prompt strategies |
| Cloud browser providers | No | We control local Chrome via DevTools |
| Their action vocabulary | Maybe | Compare to our semantic_actions for coverage gaps |

## Recommendation

**Study, do not integrate.** Concretely:
1. Review Browser Use's action vocabulary and prompt structure to find gaps
   in our `automation/semantic_actions.py` and goal parser coverage.
2. Validate our perceive→plan→act→verify loop against their observe→think→act
   — confirm our verification step is a genuine reliability advantage.
3. Do NOT adopt cloud browser providers — conflicts with local-control.
4. If we ever need a `browser_agent/` subsystem, model its loop on ours
   (which already exceeds theirs via verification), informed by their
   action taxonomy.

**Priority**: Medium (research/study). No code integration. Our browser stack
is architecturally ahead due to the verification layer.
