# Implementation Plan: M14 — Capability Benchmarks & Competence Ratchet

## Overview

Build the measurement foundation for competence-driven development before any v2.1 subsystem. M14 adds
a capability-benchmark layer over the M11 primitives: five domain suites (browser/desktop/research/
coding/long_horizon) with evidence-based scorers, a competence ratchet that gates regressions, a
scorecard, and the after-milestone review protocol. **No production default changes.** Real scores are
produced only on a real machine; the sandbox fabricates none.

All code lives under `friday/benchmarks/capability/` (additive; reuses `friday/benchmarks/` +
`friday/competence/`). Tests run under `FRIDAY_DRY_RUN=1` with stub evidence.

**Test command:** `python -m pytest tests/friday/ -q`.

## Tasks

- [ ] 1. Domain benchmark suites + data models
  - [ ] 1.1 Author the five domain suites and CapabilityBenchmark model
    - Create `friday/benchmarks/capability/__init__.py` and
      `friday/benchmarks/capability/domains.py` with frozen `CapabilityBenchmark` and
      `browser_suite()/desktop_suite()/research_suite()/coding_suite()/long_horizon_suite()`, each with
      measurable `acceptance` + `required_evidence` (EvidenceKind names) + `requires_live` flags, and NO
      app/site names (Axiom 15)
    - _Requirements: 1.1, 1.5, 4.2_

  - [ ]* 1.2 Tests: five-domain coverage + no app/site names
    - **Property 5: All five domains are covered**
    - **Property 6: No application/site names in benchmark definitions**
    - **Validates: Requirements 1.1, 1.5**

- [ ] 2. Evidence-based scorer
  - [ ] 2.1 Implement scoring
    - Create `friday/benchmarks/capability/scoring.py`: `score_benchmark(benchmark, evidence) -> bool`
      (True iff every `required_evidence` kind present in the bundle) and `score_domain(results) ->
      float` (weighted [0,1] pass ratio, 0.0 empty, deterministic). Resolve EvidenceKind names to
      `friday.verification.evidence_law.EvidenceKind`
    - _Requirements: 1.2, 1.3, 1.4_

  - [ ]* 2.2 Tests: evidence-judged, bounded domain score
    - **Property 1: Evidence is the judge, never self-report**
    - **Property 2: Domain score is a bounded weighted ratio**
    - **Validates: Requirements 1.2, 1.3, 1.4**

- [ ] 3. Competence ratchet
  - [ ] 3.1 Implement the ratchet + baseline persistence
    - Create `friday/benchmarks/capability/ratchet.py`: frozen `DomainScore`, `RatchetVerdict`,
      `CompetenceRatchet(baseline_path)` with `load()`, `check(new_scores, *, tolerance=0.05)` (fail iff
      a MEASURED domain regressed below baseline − tolerance; unmeasured never blocks), and
      `record(new_scores)` (persist; mark `measured=True` only for supplied real scores)
    - Seed `friday/benchmarks/capability/baseline.json` as all-unmeasured (fabricates nothing)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.3_

  - [ ]* 3.2 Tests: ratchet gate + no fabricated baselines
    - **Property 3: Ratchet blocks regressions, allows improvements**
    - **Property 4: Ratchet never fabricates baselines**
    - **Validates: Requirements 2.1, 2.2, 2.3, 3.3**

- [ ] 4. Scorecard + review protocol
  - [ ] 4.1 Implement CompetenceScorecard and author the review template
    - Add frozen `CompetenceScorecard` (in `ratchet.py` or a `scorecard.py`) aggregating domain scores +
      verdict + overall (mean of measured), with a `to_markdown()` renderer
    - Create `docs/reviews/AFTER_MILESTONE_REVIEW_TEMPLATE.md`: the repeatable protocol (run benchmarks
      → architecture review → confirm no regression via the ratchet → continue) with a fill-in scorecard
      section
    - _Requirements: 3.1, 3.2_

- [ ] 5. Runnable capability-benchmark entry point
  - [ ] 5.1 Wire the domain suites to the runner (real-machine entry)
    - Add `scripts/kernel_validation/run_capability_benchmarks.py`: constructs the domain suites, is
      driven with a real Operator factory on a real machine, scores each domain via the Evidence Law,
      runs the ratchet, and writes a `CompetenceScorecard`. Skips `requires_live` under FRIDAY_DRY_RUN
    - _Requirements: 3.1, 3.3, 4.1_

- [ ] 6. Final checkpoint
  - [ ] 6.1 Run the full suite and confirm green; confirm no production change
    - Run `python -m pytest tests/friday/ -q`; confirm ≥ 1234 + new M14 tests pass; confirm no
      production default changed
    - _Requirements: 4.3_

## Notes

- Tasks marked `*` are framework tests (stub evidence; no real scores asserted).
- STRICT: additive only; reuse M11 benchmarks + M8 competence; no production default change; no
  app/site names in benchmark definitions (Axiom 15).
- The seeded `baseline.json` is all-UNMEASURED — the maintainer's first real-machine run establishes
  the true baselines. The sandbox never fabricates competence numbers.
- After M14, the after-milestone review protocol becomes mandatory for M15+ (World Model v2 onward):
  each milestone must show its target domain's measured score improved or held.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.1"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["6.1"] }
  ]
}
```
