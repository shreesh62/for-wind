# Implementation Plan: M16 — Deliberation v2 (Expanded Utility & Recovery Contracts)

## Overview

Deliver A2.3 Deliberation v2 (previously *Partial*) additively: a `RecoveryContract`, the
additive `CandidateAction` term/contract fields, a nine-term `ExpandedUtilityFunction` with
action-safety/irreversibility penalties and a no-undo confidence gate, and an opt-in
`Deliberator` seam — leaving the existing simple `UtilityFunction`/`Deliberator` default
behavior byte-unchanged. All scoring is deterministic and evidence-shaped (no model calls).
Property tests use Hypothesis (≥100 examples) tagged `# Feature: m16-deliberation-v2, Property N`.

**Language:** Python.

## Tasks

- [x] 1. Baseline verification (no code change) — confirmed the current full-suite floor:
  **1658** green post-M17 (measured at M17 close-out) via `python -m pytest tests`.
  - _Requirements: 5.3_

### Phase 1 — Recovery contract + candidate fields

- [x] 2. Recovery contract + additive candidate fields
  - [x] 2.1 Create `friday/deliberation/recovery_contract.py`: `RecoveryContract` frozen
    dataclass (`undoable`, `rollback`, `verification`, `compensation`, `recovery`);
    `has_undo_path` property; JSON-safe `to_dict()`.
    - _Requirements: 1.1, 1.2, 1.5; Design C1_
  - [x] 2.2 Extend `friday/deliberation/candidate.py` additively: defaulted fields
    `information_gain`, `future_optionality`, `time_cost`, `resource_cost`, `attention_cost`,
    `opportunity_cost`, `touches_protected`, `recovery_contract`; a `has_undo_path` helper
    (reversible AND contract undo path; missing contract ⇒ no undo path). Existing
    construction + `build(...)` unchanged; construction never raises. Export new types from
    `friday/deliberation/__init__.py`.
    - _Requirements: 1.3, 1.4, 2.4; Design C2_
  - [ ]* 2.3 Property test P1 (recovery contract semantics + JSON) + P2 (additive
    construction unchanged; simple `UtilityFunction.score` identical for default-field
    candidate) — `tests/friday/test_m16_deliberation_v2.py`. ≥100 examples.
    - **Properties 1, 2** — **Validates: 1.1, 1.2, 1.3, 1.4, 1.5, 2.5, 5.1**

### Phase 2 — Expanded utility + gate

- [ ] 3. Expanded utility function
  - [x] 3.1 Create `friday/deliberation/expanded_utility.py`: `UtilityWeights` (bounded
    per-term policy weights + `safety_penalty` + `irreversibility_penalty`; clamped in
    `__post_init__`) and `ExpandedUtilityFunction`: `score` (nine terms + safety +
    irreversibility, pure/deterministic), `required_confidence`, `rank`, `best`
    (utility bar AND per-candidate raised-confidence gate), `requires_human_confirmation`.
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4; Design C3_
  - [ ]* 3.2 Property test P3 (term monotonicity + no-dominance).
    - **Property 3** — **Validates: 2.1, 2.2, 2.3**
  - [ ]* 3.3 Property test P4 (safety + irreversibility penalties: irreversible/no-undo and
    protected candidates score strictly lower).
    - **Property 4** — **Validates: 3.1, 3.2, 3.3**
  - [ ]* 3.4 Property test P5 (confidence gate: raised required_confidence for no-undo;
    `best` withholds a no-undo candidate below its raised confidence even at top raw score;
    human-confirmation flag) + P6 (determinism).
    - **Properties 5, 6** — **Validates: 4.1, 4.2, 4.3, 4.4, 2.3, 5.2**

### Phase 3 — Deliberator seam (additive)

- [ ] 4. `friday/deliberation/deliberator.py`: accept an injected `utility=` (default = the
  existing `UtilityFunction()`, byte-unchanged); allow passing an `ExpandedUtilityFunction`.
  Add optional additive `DecisionRecord` fields for the elevated-confidence /
  human-confirmation flags when the expanded scorer is used. No existing call site changes.
  - _Requirements: 5.1, 5.3; Design C4_

### Phase 4 — Benchmark (hermetic, not baselined)

- [ ] 5. Deterministic deliberation benchmark
  - [ ] 5.1 Create `friday/benchmarks/deliberation.py`: `DeliberationScenario`,
    `DeliberationMetrics` (ranking-correctness + gate-correctness over synthetic candidate
    sets, JSON + markdown), `DeliberationBenchmark`. Deterministic + hermetic (no
    LLM/network/wall-clock); domain-general (Axiom 15); NOT part of the 5-domain scorecard;
    never recorded to the committed baseline.
    - _Requirements: 6.2_
  - [ ]* 5.2 Tests (`tests/friday/test_m16_deliberation_benchmark.py`): expected ranking +
    gate outcomes; JSON-safe payload; determinism; empty→zero.
    - **Validates: 6.2**

### Phase 5 — Docs + review

- [ ] 6. FAS + traceability + review + checkpoint
  - [ ] 6.1 Mark **A2.3 Deliberation v2 → Built** in
    `docs/architecture/FAS_v2.1_AMENDMENTS.md` (code-state line pointing at
    `friday/deliberation/expanded_utility.py` + `recovery_contract.py`) and flip the A2.3
    rows in `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` from Partial → Built.
    - _Requirements: 6.3_
  - [ ] 6.2 Write `docs/reviews/REVIEW_m16-deliberation-v2.md` (architecture-compliance review
    + benchmark results) and run the full-suite checkpoint: **≥1658 + new M16 tests, 0
    failed**, no regressions.
    - _Requirements: 6.1, 6.3_

## Notes

- Tasks marked `*` are optional test sub-tasks; core implementation tasks are never optional.
- No duplicate deliberation system: reuses `CandidateAction` / `Deliberator`; the existing
  simple `UtilityFunction` stays and remains the default. The expanded scorer is opt-in.
- Deterministic + evidence-only: no model calls, no clock, no network; term inputs are
  evidence/estimates, never self-asserted competence. No application-specific logic (Axiom 15).
- Additive + safe: default `Deliberator` behavior byte-unchanged; new fields all defaulted.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["2.3", "3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "3.4", "4"] },
    { "id": 5, "tasks": ["5.1"] },
    { "id": 6, "tasks": ["5.2", "6.1"] },
    { "id": 7, "tasks": ["6.2"] }
  ]
}
```
