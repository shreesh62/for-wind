# After-Milestone Review — M16 Research Competence

> Completed per the governance rule: every milestone must improve a *measured* capability. Unlike
> M15 (which shipped a mechanism without moving its target number), M16 was chosen specifically to
> move a measured benchmark — and it did.

## 0. Milestone under review

- Milestone: `M16 — Research Competence (Browserless Gather + Evidence)`
- Target capability domain(s): `research`, `long_horizon`
- Summary: The only web search/read path lived inside the Playwright `BrowserController`; the
  capability benchmark runs the Operator with no browser, so research goals produced zero
  `GATHERED_INFO`/`SOURCE_URL` and scored 0.0. M16 adds a **browserless** HTTP gatherer
  (`friday/capabilities/web_search.py`) over the existing `httpx` dependency — a general, pluggable
  DuckDuckGo-backed search provider (stdlib-only HTML parsing, no new deps) that records real
  snippet + source-URL evidence and best-effort page text. It is wired into `research()`'s
  no-browser guard (browser path unchanged), gated by `FRIDAY_DRY_RUN`, treats fetched content as
  untrusted, and — closing the M15 governance note — turns gathered findings into M15 beliefs with
  provenance (source URLs) and research freshness, returned on `ResearchResult.beliefs`.

## 1. Regression safety (automated)

- [x] Full test suite green: `python -m pytest tests/friday/ tests/world/ -q` → **1322 passed, 0 failed**
      (1297 prior + 25 new M16 tests; one pre-existing test updated to the new no-browser contract).
- [x] No production default changed. Additive only: `research()`/`_execute_research` signatures and
      the browser path unchanged; `ResearchResult` gained a defaulted `beliefs` field; no `Belief`,
      `WorldModel`, or `BrowserController` default altered (asserted via `inspect.signature`).
- [x] Invariants preserved: no application/site-specific branching (Axiom 15 — hosts are module
      constants, guarded by a static AST scan); Evidence Law remains the sole judge of a GATHER
      requirement; all network I/O mocked in tests (zero live calls); untrusted content handled as
      text-only, never executed.

## 2. Real-world capability benchmarks (real machine)

Run on a real machine (NVIDIA keys live, `FRIDAY_DRY_RUN` unset), per-benchmark timeout 90s.
Recorded to `baseline.local.json`; the committed seed stays all-unmeasured.

```
# Competence Scorecard
- Overall (mean of measured domains): 0.6000
- Ratchet: PASS
- Improvements: browser, coding, research
| Domain       | Score  | Measured |
|--------------|--------|----------|
| browser      | 0.5000 | yes      |
| desktop      | 0.5000 | yes      |
| research     | 1.0000 | yes      |
| coding       | 1.0000 | yes      |
| long_horizon | 0.0000 | yes      |
```

- Ratchet verdict: **PASS** — improvements in browser, coding, research; no regressions.
- Newly passing benchmarks: `research.gather_with_sources` (10.6s), `research.produce_cited_summary`
  (18–24s), `browser.search_multiple_sources` (11s), `coding.edit_existing_file` (9–17s).
- Confirmed across two consecutive runs (0.6000 both times) — not a fluke.

## 3. Competence delta

| Domain | Prev baseline (M15) | This run (M16) | Δ | Verdict |
|---|---|---|---|---|
| browser | 0.0 | 0.5 | +0.5 | improved |
| desktop | 0.5 | 0.5 | 0 | held |
| research | 0.0 | 1.0 | **+1.0** | improved (target) |
| coding | 0.5 | 1.0 | +0.5 | improved |
| long_horizon | 0.0 | 0.0 | 0 | held (target — not yet moved) |
| overall | 0.2 | 0.6 | +0.4 | improved |

- Did the target domain improve? **research: YES (0.0 → 1.0).** `long_horizon` held at 0.0 — the
  multi-stage `research_to_document` goal now gathers real info but does not yet complete the full
  end-to-end chain (research → produce cited content → save file artifact) within the run. The
  research *portion* now works; the remaining gap is the multi-stage orchestration that assembles a
  cited document and saves it — a candidate for a future milestone.
- Non-target improvements (browser, coding) are genuine: the browserless gatherer also satisfies
  `browser.search_multiple_sources`, and the M15-era NVIDIA model fix let both coding benchmarks pass.

## 4. Architecture review

- Realizes the M15 review's governance recommendation: gathered findings now produce M15 beliefs
  (provenance from source URLs + research freshness), giving the M15 World Model v2 mechanism its
  first live producer.
- FAS alignment: extends the research/gather capability (Ch 25/exploration + Ch 14 retrieval spirit)
  with a general search provider; no app-specific logic. The `ResearchResult.beliefs` handoff is an
  honest boundary — the executor holds no `WorldModel`, so beliefs are surfaced for a future
  kernel/world consumer to ingest (documented; not silently dropped).
- New technical debt: (a) `long_horizon` end-to-end orchestration remains unsolved; (b) beliefs are
  returned but not yet ingested by a live `WorldModel` on the Operator path (deferred wiring);
  (c) pre-existing flags carried over (stale model names in some `*.md` docs; dead retry branch in
  `NvidiaProvider.complete`). None block; all recorded here.
- Mechanism vs component: M16 improved a **measured capability**, not just added a component — the
  research domain moved 0.0 → 1.0.

## 5. Decision

- [x] **PROCEED** — measured competence improved (research +1.0, overall +0.4), ratchet PASS,
      invariants intact, regressions none, new baseline recorded to `baseline.local.json`.
- Recommended next targets (competence-first): (1) **long_horizon** — the multi-stage
  research→document→save chain (the one domain still at 0.0); and/or (2) wire the returned research
  beliefs into a live `WorldModel` on the Operator path so freshness/provenance informs planning.

Reviewer / date: FRIDAY orchestrator, M16 close-out.
