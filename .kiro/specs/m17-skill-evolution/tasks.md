# Implementation Plan: M17 — Skill Evolution Pipeline

## Overview

Formalize the FAS §A2.5.1 skill-evolution pipeline (A2.5, previously *Partial*) as one
additive, kernel-attached coordinator that reuses the existing M9 learning + M11 evolution
mechanisms. It consumes `learning.validated` + `reflection.skill`, tracks each skill's stage,
and emits a single `skill.candidate` proposal when a skill carries both signals — never
self-promoting, never writing memory, never fabricating competence. All new code is additive
and inert without a kernel. Property tests use Hypothesis (≥100 examples) tagged
`# Feature: m17-skill-evolution, Property N`.

**Language:** Python.

## Tasks

- [x] 1. Baseline verification (no code change) — confirmed the current full-suite floor:
  **1637** green post-M20 (measured at M20 close-out) via `python -m pytest tests`.
  - _Requirements: 5.3_

### Phase 1 — Stage taxonomy

- [x] 2. Create `friday/learning/skill_stage.py`
  - [x] 2.1 Add a `SkillStage(str, Enum)` with exactly eight ordered members
    (`OBSERVATION, EXPERIMENT, REFLECTION, VERIFICATION, COMPILATION, OPTIMIZATION,
    GENERALIZATION, REGISTRY`) + an `ordinal` property; JSON-safe `.value`.
    - _Requirements: 1.1, 1.2; Design C1_
  - [x]* 2.2 Property test P1 (eight members in FAS order, strictly increasing ordinals,
    every `.value` JSON-serializes) — `tests/friday/test_m17_skill_evolution.py`. ≥100 examples.
    - **Property 1** — **Validates: 1.1, 1.2**

### Phase 2 — Coordinator

- [x] 3. Create `friday/learning/skill_pipeline.py`
  - [x] 3.1 `SkillRecord` dataclass (stage, generalized, candidate_flag, emitted, evidence
    summary; `to_dict()`), and `SkillEvolutionPipeline`: `attach(kernel)` subscribes to
    `learning.validated` + `reflection.skill` (+ observes `learning.rejected`); bounded
    per-`(capability, environment)` store (oldest evicted); `learning.validated` →
    `generalized=True` + stage ≥ `GENERALIZATION`; `reflection.skill` → `candidate_flag=True`
    + evidence summary; `learning.rejected` → clear `generalized`; dual-signal condition emits
    ONE deduplicated `skill.candidate` and advances stage to `REGISTRY`; `skill(...)` /
    `skills()` queries; defensive handlers never raise. ISOLATION: no import of
    `friday.memory.*` / `friday.competence.*` / `friday.evolution.*`, no `FridayMemory`/
    `MemoryStore` reference, no lifecycle/promotion call; only side effect is emitting
    `skill.candidate`.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2; Design C2, C3_
  - [x] 3.2 `attach_skill_pipeline(kernel, *, pipeline=None, **kwargs)` reusable wiring helper
    (mirror `attach_reflection_layers`): construct/reuse a pipeline, attach, return it; no-op
    without a kernel; attach failure isolated.
    - _Requirements: 5.2; Design C4_
  - [x]* 3.3 Property test P2 (maturation tracking: `learning.validated`→≥GENERALIZATION;
    `reflection.skill`→candidate flag; bounded store; malformed events never raise / create
    no junk).
    - **Property 2** — **Validates: 2.1, 2.2, 2.3, 2.4**
  - [x]* 3.4 Property test P3 (dual-signal candidate emitted exactly once; neither signal
    alone emits; re-delivery does not re-emit; JSON-safe payload carries identity + evidence;
    `skills()` query).
    - **Property 3** — **Validates: 3.1, 3.2, 3.3**
  - [x]* 3.5 Property test P4 (isolation: no memory/competence/evolution import; only
    `skill.candidate` emitted; `learning.rejected` clears generalized so a rejected skill
    never becomes a candidate; no-op without kernel) + P5 (skills keyed only by generic
    `(capability, environment)`; identical behavior under arbitrary labels).
    - **Properties 4, 5** — **Validates: 4.1, 4.2, 4.3, 4.4, 5.2**
  - [x] 3.6 Close the production chain (additive): enrich the M9 `learning.validated` (and
    `learning.rejected`) event payload emitted by `friday/learning/engine.py` to include the
    `capability` + `environment` of the experience, so real learning events (not just
    synthetic ones) carry the identity the pipeline keys on. Additive only — extra payload
    keys; existing consumers unaffected. Re-run the M9 learning test suite to confirm no
    regression.
    - _Requirements: 2.1, 2.3, 4.1_

### Phase 3 — Bootstrap wiring (additive)

- [x] 4. `friday/api/server.py`: within the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block
  (after the reactive loop + reflection layers are wired), call `attach_skill_pipeline(kernel)`
  and expose it as `kernel.skill_pipeline`. Additive; default (flag-off) path byte-unchanged;
  wiring failure logged with structured context, never crashes bootstrap.
  - _Requirements: 5.2, 5.3; Design C5_

- [x] 4.1 Activate the `learning.validated` producer (additive): the reactive loop
  (`friday/kernel/reactive_loop.py::attach_reactive_loop`) attaches Recovery/Competence/
  Reflection but NO `LearningEngine`, so `learning.validated` has no production producer and
  the M9→M17 chain cannot complete. Attach the M9 `LearningEngine` in `attach_reactive_loop`
  (guarded, additive, function-local import, isolates its own exceptions — mirrors the
  existing components) so verified experience actually produces `learning.validated`. Re-run
  the reactive-loop + learning suites; confirm no regression.
  - _Requirements: 2.1, 4.1, 5.2_

### Phase 4 — Benchmark (hermetic, not baselined)

- [x] 5. Deterministic skill-evolution benchmark
  - [x] 5.1 Create `friday/benchmarks/skill_evolution.py`: `SkillScenario`, `SkillMetrics`
    (candidate-emission precision/recall + exact-match over synthetic streams, JSON +
    markdown), `SkillEvolutionBenchmark` feeding synthetic `learning.validated` /
    `reflection.skill` / `learning.rejected` streams through the pipeline on a real kernel.
    Deterministic + hermetic (no LLM/network/wall-clock); domain-general (Axiom 15); NOT part
    of the 5-domain scorecard; never recorded to the committed baseline.
    - _Requirements: 6.2_
  - [x]* 5.2 Tests (`tests/friday/test_m17_skill_evolution_benchmark.py`): dual-signal skills
    emit exactly one candidate; single-signal + rejected skills emit none; JSON-safe payload;
    determinism; empty→zero.
    - **Validates: 6.2**

### Phase 5 — Docs + review

- [x] 6. FAS + traceability + review + checkpoint
  - [x] 6.1 Mark **A2.5 Skill evolution pipeline → Built** in
    `docs/architecture/FAS_v2.1_AMENDMENTS.md` (code-state line pointing at
    `friday/learning/skill_pipeline.py`) and flip the A2.5 row in
    `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` from Partial → Built.
    - _Requirements: 6.3_
  - [x] 6.2 Write `docs/reviews/REVIEW_m17-skill-evolution.md` (architecture-compliance review
    + benchmark results) and run the full-suite checkpoint: **≥1637 + new M17 tests, 0
    failed**, no regressions.
    - _Requirements: 6.1, 6.3_

## Notes

- Tasks marked `*` are optional test sub-tasks; core implementation tasks are never optional.
- No duplicate systems: reuses M9 learning (`learning.validated`), M20 reflection
  (`reflection.skill`), and offers `skill.candidate` to the M11 `PromotionPipeline`. The
  coordinator tracks stage and proposes — it never promotes, writes memory, or fabricates
  competence.
- Invariant preserved: only verified, evidence-backed signals advance a skill; a
  `learning.rejected` disqualifies it. No application-specific logic (Axiom 15).
- Additive + safe: attached only in the guarded kernel-exec path; hermetic runs do no
  unbidden I/O; default path byte-unchanged.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.5"] },
    { "id": 4, "tasks": ["4", "5.1"] },
    { "id": 5, "tasks": ["5.2", "6.1"] },
    { "id": 6, "tasks": ["6.2"] }
  ]
}
```
