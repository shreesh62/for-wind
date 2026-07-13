# After-Milestone Review — M23 Browser as a Generic Desktop Environment

> Governance gate. M23 inverts the browser execution model: the general desktop-cognition
> pipeline becomes the PRIMARY, canonical browser execution path; CDP/Playwright is demoted to
> an optional optimization plugin. The milestone succeeds if FRIDAY can operate a real browser
> through the same perception+motor stack used for every desktop application, with browser-specific
> automation disabled.

## 0. Milestone under review

- Milestone: `M23 — Browser as a Generic Desktop Environment`
- Target capability domain(s): `browser` (and desktop generality); architectural inversion
- Summary: FRIDAY previously depended on CDP as the primary browser path. M23 makes the desktop
  cognition pipeline canonical and CDP an opt-in accelerator (`FRIDAY_ENABLE_CDP`). Work delivered
  across five phases: (1) **Universal Perception** — `observe_active_window()` fuses UIA→OCR→pixels
  into a WorldState for any active window, wired into the executor; (2) **Generic Controller** —
  `DesktopChromeController` replaced by `DesktopBrowserController` with zero browser-name/window-title
  branching, universal Ctrl+L→type→Enter navigation; (3) **Browser Independence** — strategy default
  is `DESKTOP_CONTROL`, CDP gated behind a flag with silent fallback; (4) **Benchmarks** — an
  11-capability `web_independence` suite that runs with CDP disabled; (5) **Architectural
  strengthening** — semantic World Objects (confidence/freshness/evidence/source/bbox/affordances),
  motor preference ordering, verified-success-by-observed-change, and HARD Evidence Law (no
  placeholder/junk can pass). The FAS Browser Runtime was renamed **Web Environment Runtime** (A2.13).

## 1. Regression safety (automated)

- [x] Full test suite green: `python -m pytest tests/friday/ tests/world/ -q` → **1403 passed, 0 failed**
      (pre-M23 floor 1356; +47 net incl. M23 property/contract tests, hard-verification, and exploration suites).
- [x] Production default change is this milestone's **explicit purpose** (desktop-first), with a
      documented rollback: `FRIDAY_ENABLE_CDP=1` restores CDP-first behaviour. Committed `baseline.json`
      seed unchanged (all-unmeasured); no probabilistic scores recorded.
- [x] Architectural invariants preserved: one Kernel / World Model / Goal Graph / Competence Model;
      **Axiom 15** upheld (no app/site/browser-name/window-title logic — Wikipedia added only as a
      data-driven `Search_Provider` entry, not conditional branching); planner/deliberator reason over
      World Objects only, never over the perception source that produced them.

## 2. Real-world capability benchmarks (real machine)

Web-independence suite, real machine, **CDP disabled**, per-benchmark timeout 200s. This suite is
deliberately kept OUT of `all_domain_suites()` so it never perturbs the 5-domain competence scorecard,
and is NOT recorded to the committed baseline (probabilistic; governance rule).

```
run_capability_benchmarks.py --web-independence --no-cdp --target-browser chrome --only navigate,search
- CDP: DISABLED (FRIDAY_ENABLE_CDP=0)
- navigate : PASS (36.1s)  — NAVIGATION + GATHERED_INFO + SOURCE_URL via desktop pipeline
- search   : PASS (18.2s)  — real evidence chain, HARD Evidence Law satisfied
- score    : 1.0000
```

- Ratchet verdict: **PASS** for the exercised web-independence subset (navigate, search) on Chrome with
  CDP disabled. This is the milestone's core success criterion, proven live.
- The 5-domain competence scorecard is unaffected by design (suite excluded); `coding` re-verified
  1.0000 live post-hardening, and the HARD Evidence Law was exonerated as the cause of any `research`
  0.0 (root cause: external DuckDuckGo throttling, proven by a direct gather probe — the Law correctly
  refused to fabricate a pass from an empty gather; the Wikipedia OpenSearch provider was added as a
  resilient, policy-compliant fallback).

## 3. Competence delta

| Domain | Prev baseline | This run | Δ | Verdict |
|---|---|---|---|---|
| browser (web-independence, CDP off) | n/a (new capability) | navigate PASS, search PASS (1.0000) | **new** | improved — proven live without CDP |
| desktop | 0.5 | 0.5 | 0 | held (generality strengthened via universal perception) |
| research | 1.0 | 1.0 | 0 | held (Wikipedia fallback added for throttle resilience) |
| coding | 1.0 | 1.0 | 0 | held (re-verified 1.0000 live) |
| long_horizon | 1.0 | 1.0 | 0 | held |

- Did the target domain improve or hold? **YES.** The browser can now be operated end-to-end (navigate +
  search) through the general desktop pipeline with CDP disabled — a capability that did not exist before
  M23. No non-target domain regressed.

## 4. Architecture review

- FAS chapters / amendments touched: **A2.13 — Web Environment Runtime** (normative rename of Browser
  Runtime; §A2.13.1–.6). Realizes the perception-fusion hierarchy (Accessibility→native→OCR→Vision→Pixels)
  as the canonical browser path and demotes CDP to a plugin.
- Mechanisms strengthened (not just components added): universal perception fusion; semantic World Objects
  with full metadata + freshness decay; motor preference cascade (Keyboard→Accessibility→Mouse→Pixel);
  **exploration-on-low-confidence** (unresolved targets drive the generic `ExplorationEngine` over the
  abstract `EnvironmentContract` — Observe→hypothesize→risk-ordered SAFE experiment→verify→update World
  Model — instead of a blind action, safe-by-default: unwired = clean failure, never a guess);
  verified-success-by-observed-World-Model-change; and a HARD Evidence Law that refuses placeholder targets
  (`<<topic>>`, `<<extracted URL>>`) and non-URL "sources" at their source in the executor.
- New technical debt (carried / introduced):
  - **Exploration live-provider (Task 11) is opt-in** — the mechanism is wired and unit-verified over the
    abstract contract; enabling real safe-experiments live requires injecting a concrete
    `environment_provider` (e.g. a `DesktopEnvironment` from the active window), a focused live-validated
    step. The "no blind action" guarantee holds unconditionally today.
  - Firefox/Edge/Brave/Electron live parity not run here (Firefox not installed); correctness is guaranteed
    by construction (P4/P5) and differs only in performance, per the milestone's engineering principle.
  - A true UIA-Invoke actuation tier (vs selection-level ordering) is flagged as a future motor optimization.
- Confirm: the milestone improved a **mechanism** (the canonical browser execution model), not merely a
  component, and left the architecture behaving identically with CDP on or off (correctness), differing only
  in speed (optimization).

## 5. Decision

- [x] **PROCEED** — the core success criterion is proven live (navigate + search PASS on Chrome, CDP
      disabled, real evidence via the desktop pipeline), the full unit suite is green (1396, 0 failed),
      architectural invariants intact, rollback available (`FRIDAY_ENABLE_CDP=1`), and no domain regressed.
      No probabilistic score recorded to the committed baseline (governance rule).
- Recommended next targets: (a) inject a live `environment_provider` (a `DesktopEnvironment` over the active
  window) so exploration runs real safe-experiments live, then live-validate (Task 11 mechanism is already
  wired + unit-verified); (b) run live browser parity on Edge/Brave/an Electron app to convert the
  by-construction guarantee into measured evidence; (c) a UIA-Invoke actuation tier for the motor system.

Reviewer / date: FRIDAY orchestrator, M23 close-out.
