# After-Milestone Review — M17 Long-Horizon Synthesis

> Governance gate. M17 targeted the last 0.0 domain (`long_horizon`) and moved it.

## 0. Milestone under review

- Milestone: `M17 — Long-Horizon Synthesis Competence`
- Target capability domain(s): `long_horizon`
- Summary: `long_horizon.research_to_document` scored 0.0 because the deterministic
  fallback planner never planned a synthesis step for a "research → produce & save a
  document" goal — it dumped raw gathered text into a file, recording GATHERED_INFO +
  SOURCE_URL + FILE_ARTIFACT but **GENERATED_CONTENT=0**. M17 adds a general structural
  planning invariant — *a plan that both gathers and saves MUST synthesize between
  them* (`needs_info and needs_file ⇒ needs_content`) — plus broadened synthesis-verb
  detection and a PRODUCE-requirement injection in requirements discovery. The
  executor's data-flow (file gets synthesized content, prompt cites source URLs) was
  already correct and needed no change.

## 1. Regression safety (automated)

- [x] Full suite green: `python -m pytest tests/friday/ tests/world/ -q` → **1339 passed, 0 failed**
      (1322 prior + 17 new M17 tests; no pre-existing test needed updating).
- [x] No production default changed. Additive: two small planner/requirements edits;
      `executor.py` and `evidence_law.py` untouched.
- [x] Invariants preserved: Axiom 15 (general goal-shape rule, no app/site/topic
      branching — the keyword additions are data, the invariant is structural);
      Evidence Law remains the judge (generated text satisfies PRODUCE, never GATHER);
      planner decision is pure/deterministic (property-tested).

## 2. Real-world capability benchmarks (real machine)

Real machine, `FRIDAY_DRY_RUN` unset, per-benchmark timeout 120s. Recorded to
`baseline.local.json`; committed seed stays all-unmeasured.

```
# Competence Scorecard
- Overall (mean of measured domains): 0.8000
- Ratchet: PASS
- Improvements: long_horizon
| Domain       | Score  | Measured |
|--------------|--------|----------|
| browser      | 0.5000 | yes      |
| desktop      | 0.5000 | yes      |
| research     | 1.0000 | yes      |
| coding       | 1.0000 | yes      |
| long_horizon | 1.0000 | yes      |
```

- Ratchet verdict: **PASS** — long_horizon improved; no regressions.
- `long_horizon.research_to_document` now PASSES (20.5s) — all four evidence kinds
  (GATHERED_INFO, SOURCE_URL, GENERATED_CONTENT, FILE_ARTIFACT) produced in one run.
- Confirmed across two consecutive runs (0.8000 both).

## 3. Competence delta

| Domain | Prev (M16) | This run (M17) | Δ | Verdict |
|---|---|---|---|---|
| browser | 0.5 | 0.5 | 0 | held |
| desktop | 0.5 | 0.5 | 0 | held |
| research | 1.0 | 1.0 | 0 | held |
| coding | 1.0 | 1.0 | 0 | held |
| long_horizon | 0.0 | 1.0 | **+1.0** | improved (target) |
| overall | 0.6 | 0.8 | +0.2 | improved |

- Did the target domain improve? **long_horizon: YES (0.0 → 1.0).** Every competence
  domain is now non-zero; overall competence is 0.8.
- No regressions in any non-target domain.

## 4. Architecture review

- Realizes a general multi-stage orchestration rule in the fallback planner and closes
  the false-complete gap (a gather+save+document goal now emits a PRODUCE requirement,
  so the Evidence Law can enforce GENERATED_CONTENT). The synthesis is grounded: the
  generate step cites the gathered SOURCE_URLs.
- New technical debt: none introduced. Remaining (pre-existing, carried): browser and
  desktop domains sit at 0.5 (one of two benchmarks each fails —
  `browser.navigate_and_read`, `desktop.open_and_confirm`); stale model names in some
  `*.md` docs; dead retry branch in `NvidiaProvider.complete`.
- Mechanism vs component: improved a **measured capability** via a general mechanism
  (structural planning invariant), not a task template.

## 5. Decision

- [x] **PROCEED** — target competence improved (long_horizon +1.0, overall +0.2),
      ratchet PASS, invariants intact, regressions none, new baseline recorded.
- Recommended next targets (competence-first): the two remaining 0.5 domains —
  `browser.navigate_and_read` (single-page navigate + read without a browser
  controller) and `desktop.open_and_confirm` (confirmed app-launch/foreground
  evidence) — or the deferred wiring of research beliefs into a live `WorldModel` on
  the Operator path.

Reviewer / date: FRIDAY orchestrator, M17 close-out.
