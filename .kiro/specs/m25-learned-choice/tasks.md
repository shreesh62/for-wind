# Implementation Plan: M25 — Learned Choice & Preference Resolution

## Overview

Implement FAS §A2.15 — a general Preference Resolution Pipeline that eliminates repeated
clarification for recurring choices. `DecisionPoint` + `PreferenceResolver` coordinate
Preference Memory (M21), Retrieval Router (M19), Deliberation (M16), Cognitive State (M22),
and Failure Memory (M21) into one event-driven pipeline: detect → query → evaluate → apply
or ask → verify → learn. No new persistence, no application-specific logic (Axiom 15). All
new code additive and inert without a kernel. Property tests Hypothesis ≥100 examples tagged
`# Feature: m25-learned-choice, Property N`.

**Language:** Python.

## Tasks

- [x] 1. Baseline: **1732 passed, 0 failed** (post model-resilience fix).

### Phase 1 — DecisionPoint

- [x] 2. `friday/deliberation/decision_point.py` (NEW)
  - [x] 2.1 Frozen dataclass `DecisionPoint` (decision_id, goal_context, environment,
    options: tuple, risk: clamped [0,1], reversible: bool, category, candidates: tuple,
    metadata: dict). Construction with empty decision_id or empty options raises ValueError.
    `to_dict()` / `from_dict()` JSON round-trip. Import only stdlib.
    - _Requirements: 1.1, 1.2, 1.3, 1.4; Design C1_

### Phase 2 — PreferenceResolver + pure functions

- [x] 3. `friday/deliberation/preference_resolver.py` (NEW)
  - [x] 3.1 `compute_preference_confidence(*, source_type, reuse_count, correction_count,
    recency_days, contradiction_count) -> float` — pure, deterministic, [0,1]. Never
    LLM-asserted. (Design C3)
    - _Requirements: 5.7_
  - [x] 3.2 `contains_secret_material(value) -> bool` — heuristic filter (known prefixes,
    high-entropy base64 blocks ≥20 chars, PEM markers). vault:// refs allowed. (Design C4)
    - _Requirements: 7.2, 7.3_
  - [x] 3.3 `PreferenceResolver`: attach(kernel, *, preference_memory, retrieval_router,
    cognitive_state, failure_memory); `resolve_sync(decision_point)` full pipeline; 
    `learn_preference(...)`, `apply_preference(...)`, `correct_preference(...)`,
    `supersede_preference(...)`, `explain(decision_id)`. Emits lifecycle events. Isolation:
    imports only friday.events + friday.memory.interfaces + friday.deliberation.decision_point
    + stdlib. Handlers never raise. (Design C2, C5, C6)
    - _Requirements: 2.1-2.4, 3.1-3.5, 4.1-4.4, 5.1-5.6, 6.1-6.5, 7.1-7.4, 8.1-8.4, 9.1-9.4, 10.1-10.4_

### Phase 3 — Extend PreferenceRecord (additive)

- [x] 4. `friday/memory/preference_memory.py`: add additive fields to `PreferenceRecord`
  (context_scope, preference_class, confidence, reuse_count, last_verified, corrections,
  superseded_by, provenance) with safe defaults so existing usage is unchanged. Update
  `to_memory_entry()` metadata. Do NOT change existing method signatures/behavior.
  - _Requirements: 5.2, 8.1; Design data models_

### Phase 4 — Property tests (10) + acceptance scenarios (A–H)

- [x]* 5. Tests `tests/friday/test_m25_learned_choice.py` (≥100 Hypothesis examples per
  property): P1 DecisionPoint round-trip + fail-fast; P2 precedence; P3 contextual scope
  gating; P4 confidence determinism + bounds; P5 reversibility gating + should_interrupt;
  P6 secret-material rejection; P7 event JSON round-trip; P8 pipeline idempotence;
  P9 defensive handlers; P10 provenance completeness. Plus acceptance scenarios A–H.
  - **Properties 1–10** — **Validates: all requirements**

### Phase 5 — Bootstrap wiring

- [x] 6. `friday/api/server.py`: `attach_preference_resolver(kernel, preference_memory=...,
  retrieval_router=..., cognitive_state=..., failure_memory=...)` in the guarded path;
  expose as `kernel.preference_resolver`. Additive; default path unchanged; wiring failure
  logged.
  - _Requirements: 11.1, 11.2, 11.3_

### Phase 6 — Docs + review

- [x] 7. FAS + traceability + review + checkpoint
  - [x] 7.1 Mark A2.15 → Built in FAS + traceability matrix.
  - [x] 7.2 Write `docs/reviews/REVIEW_m25-learned-choice.md` + full-suite checkpoint
    (≥1732 + M25 tests, 0 failed).
    - _Requirements: 12.3_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1"] },
    { "id": 1, "tasks": ["3.1", "3.2"] },
    { "id": 2, "tasks": ["3.3", "4"] },
    { "id": 3, "tasks": ["5", "6"] },
    { "id": 4, "tasks": ["7.1"] },
    { "id": 5, "tasks": ["7.2"] }
  ]
}
```
