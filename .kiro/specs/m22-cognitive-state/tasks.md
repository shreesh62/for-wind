# Implementation Plan: M22 — Cognitive State Manager (completion)

## Overview

Complete FAS §A2.12 (A2.12, previously *Partial*) additively over the existing
`CognitiveStateManager`: add Cognitive Load + Background cognition state, complete
engagement-mode coverage from events, add pure coordination queries (`should_interrupt`,
`suggested_thinking_depth`), and wire the manager into the guarded bootstrap. Preserve the
isolation invariant (events + stdlib only; handlers never raise). Also true up the stale v2.1
traceability matrix (A2.1/A2.2/A2.3/A2.6 are already Built). All new code is additive and
inert without a kernel. Property tests use Hypothesis (≥100 examples) tagged
`# Feature: m22-cognitive-state, Property N`.

**Language:** Python.

## Tasks

- [x] 1. Baseline verification (no code change) — confirmed the current full-suite floor:
  **1658** green post-M17 (measured at M17 close-out) via `python -m pytest tests`.
  - _Requirements: 5.3_

### Phase 1 — Complete the mind-state model + queries

- [x] 2. Extend `friday/cognition/state.py` (additive)
  - [x] 2.1 Add `cognitive_load: float = 0.0` and `background_active: bool = False` to
    `CognitiveState` (after existing fields; defaults preserved) and a JSON-safe `to_dict()`
    (enums as `.value`). Keep `snapshot()` returning an immutable copy.
    - _Requirements: 1.1, 1.2, 1.3; Design C1_
  - [x] 2.2 Load tracking: `set_load(value)` / `adjust_load(delta)` always `_clamp01`;
    `set_focus(...)` additionally sets `cognitive_load` from committed attention (preserve
    the existing focus/attention behavior); returning to idle lowers load.
    - _Requirements: 2.1, 2.2, 2.3; Design C2_
  - [x] 2.3 Mode coverage from events: preserve EXECUTION on `action.executed`; add
    EXPLORATION on a generic exploration signal and CONVERSATION on a conversation/user-input
    signal; return to IDLE + clear focus + lower load on a terminal goal state with nothing
    else active; update `background_active`. Handlers defensive, never raise.
    - _Requirements: 3.1, 3.2, 3.3, 3.4; Design C3_
  - [x] 2.4 Query surface: `should_interrupt(urgency)` (honors `interruptible`; when not
    interruptible, True only above a load-scaled urgency threshold) and
    `suggested_thinking_depth()` (SHALLOW under low budget/high load, DEEP under ample
    budget/low load, else NORMAL). Pure reads; deterministic.
    - _Requirements: 4.1, 4.2, 4.3; Design C4_
  - [x]* 2.5 Property tests P1–P6 (`tests/friday/test_m22_cognitive_state.py`, ≥100 examples):
    state additions + clamping + immutable snapshot + JSON; load reflects engagement; mode
    coverage from events (+ malformed never raise); interruptibility query; reasoning-depth
    query; isolation (imports only events+stdlib; usable without a kernel).
    - **Properties 1–6** — **Validates: 1.1, 1.2, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.1**

### Phase 2 — Bootstrap wiring (additive)

- [x] 3. `friday/api/server.py`: within the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block,
  construct a `CognitiveStateManager`, `attach(kernel)`, and expose it as
  `kernel.cognitive_state`. Additive; default (flag-off) path byte-unchanged; wiring failure
  logged with structured context, never crashes bootstrap.
  - _Requirements: 5.2, 5.3; Design C5_

### Phase 3 — Docs + traceability true-up + review

- [x] 4. FAS + traceability true-up + review + checkpoint
  - [x] 4.1 Mark **A2.12 Cognitive State Manager → Built** in
    `docs/architecture/FAS_v2.1_AMENDMENTS.md` (code-state line pointing at
    `friday/cognition/state.py` + `kernel.cognitive_state`). Correct the stale rows in
    `docs/architecture/TRACEABILITY_MATRIX_v2.1.md`: A2.1 → Built (`friday/world/*`, M15),
    A2.2 → Built (`friday/perception/fingerprint*.py`), A2.3 → Built
    (`friday/deliberation/expanded_utility.py` + `recovery_contract.py`), A2.6 → Built
    (`friday/resources/economics.py` + `scheduler.py`), A2.12 → Built; update the
    "Summary by state" prose accordingly (only A2.11 seven-tier expansion remains Partial).
    - _Requirements: 6.2_
  - [x] 4.2 Write `docs/reviews/REVIEW_m22-cognitive-state.md` (architecture-compliance
    review) and run the full-suite checkpoint: **≥1658 + new M22 tests, 0 failed**, no
    regressions. Note this closes the Architecture v2.1 build-out.
    - _Requirements: 6.1, 6.3_

## Notes

- Tasks marked `*` are optional test sub-tasks; core implementation tasks are never optional.
- No duplicate mind-state store: extends the existing `CognitiveStateManager`. The World
  Model remains the model of external reality; this remains the model of FRIDAY's own mind.
- Invariant preserved: imports only `friday.events` + stdlib; updated purely from the event
  stream; handlers never raise into the tick loop; no application-specific logic (Axiom 15).
- Additive + safe: attached only in the guarded kernel-exec path; default path byte-unchanged.
- No new benchmark: this is a coordinator, not a measured capability; the 5-domain scorecard
  is unchanged.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["2.5", "3"] },
    { "id": 4, "tasks": ["4.1"] },
    { "id": 5, "tasks": ["4.2"] }
  ]
}
```
