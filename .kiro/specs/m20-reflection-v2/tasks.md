# Implementation Plan: M20 — Reflection v2 (Layered Reflection)

## Overview

Formalize the five-layer reflection hierarchy (A2.10, previously *Partial*) additively over
the existing `ReflectionEngine`. The two lowest layers already exist (Immediate/Session);
add the `ReflectionLayer` taxonomy plus three higher consumer layers (Long-Term, Skill,
Architectural) that aggregate the `reflection.completed` stream and emit JSON-safe
`reflection.*` proposal events — never memory writes. All new code is additive and inert
without a kernel. Property tests use Hypothesis (≥100 examples) tagged
`# Feature: m20-reflection-v2, Property N`.

**Language:** Python.

## Tasks

- [x] 1. Baseline verification (no code change) — confirmed the current full-suite floor:
  **1614** green post-M19 (measured during the M19 A8 fix) via `python -m pytest tests`.
  - _Requirements: 7.3_

### Phase 1 — Layer taxonomy

- [x] 2. Add `ReflectionLayer` to `friday/cognition/reflection.py`
  - [x] 2.1 Add a `ReflectionLayer(str, Enum)` with exactly five ordered members
    (`IMMEDIATE`, `SESSION`, `LONG_TERM`, `SKILL`, `ARCHITECTURAL`) + an ordinal helper;
    JSON-safe `.value`. Document the micro→IMMEDIATE / task,goal,session→SESSION mapping.
    Do NOT change any existing `ReflectionEngine`/`ReflectionScale` output.
    - _Requirements: 1.1, 1.2, 1.3, 5.3; Design C1_
  - [x]* 2.2 Property test P1 (five members, immediate→architectural order, strictly
    increasing ordinals, every `.value` JSON-serializes) —
    `tests/friday/test_m20_reflection_layers.py`. ≥100 examples.
    - **Property 1** — **Validates: 1.1, 1.3**

### Phase 2 — Higher layers (consumers of the reflection stream)

- [x] 3. Create `friday/cognition/reflection_layers.py`
  - [x] 3.1 `LongTermReflector`: `attach(kernel)` subscribes to `reflection.completed`;
    bounded per-(capability, environment) sample window; emits `reflection.longterm` when
    mean error ≥ threshold over ≥ min_samples; `trend(...)` query; handlers never raise;
    no memory/competence/recovery imports.
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 5.1, 5.2, 6.1; Design C2_
  - [x] 3.2 `SkillReflector`: per-capability aggregation (count, mean error, verified_rate);
    emits `reflection.skill` candidate proposal when verified low-error threshold met;
    `summaries()` query; bounded; handlers never raise.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 6.1; Design C3_
  - [x] 3.3 `ArchitecturalReflector`: cross-capability meta-signal; emits a single
    deduplicated advisory `reflection.architectural` proposal when the meta-threshold is
    crossed; mutates nothing; bounded; handlers never raise.
    - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2, 6.1; Design C4_
  - [x] 3.4 `attach_reflection_layers(kernel, *, longterm=None, skill=None,
    architectural=None, ...)`: reusable wiring helper (function-local imports; reuses
    injected layers; no-op without a kernel; each layer isolates its exceptions); returns a
    holder object.
    - _Requirements: 6.2, 6.3; Design C5_
  - [x]* 3.5 Property test P2 (long-term aggregation + threshold proposal + bound) —
    same test module. ≥100 examples.
    - **Property 2** — **Validates: 2.1, 2.2, 2.3**
  - [x]* 3.6 Property test P3 (skill aggregation + candidate proposal + summaries + bound).
    - **Property 3** — **Validates: 3.1, 3.2, 3.3, 3.4**
  - [x]* 3.7 Property test P4 (architectural advisory meta-proposal, deduped, mutates nothing).
    - **Property 4** — **Validates: 4.1, 4.2**
  - [x]* 3.8 Property test P5 (isolation: no memory/competence/recovery import; only
    `memory.candidate`/`reflection.*` emitted; malformed events never raise; no-op without
    kernel) + P6 (existing `ReflectionEngine` outputs unchanged with layers attached).
    - **Properties 5, 6** — **Validates: 5.1, 5.2, 5.3, 6.1, 6.2, 6.3**

### Phase 3 — Bootstrap wiring (additive)

- [x] 4. `friday/api/server.py`: within the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block,
  call `attach_reflection_layers(kernel)`. Additive; default (flag-off) path byte-unchanged;
  wiring failure logged with structured context, never crashes bootstrap.
  - _Requirements: 7.1, 7.2; Design C6_

### Phase 4 — Benchmark (hermetic, not baselined)

- [x] 5. Deterministic reflection benchmark
  - [x] 5.1 Create `friday/benchmarks/reflection.py`: `ReflectionScenario`,
    `ReflectionMetrics` (expected-proposal precision/recall over synthetic streams, JSON +
    markdown), `ReflectionBenchmark` feeding synthetic `reflection.completed` streams through
    the layers on a real kernel. Deterministic + hermetic (no LLM/network/wall-clock);
    domain-general (Axiom 15); NOT part of the 5-domain scorecard; never recorded to the
    committed baseline.
    - _Requirements: 8.2_
  - [x]* 5.2 Tests (`tests/friday/test_m20_reflection_benchmark.py`): expected proposals
    emitted, no false proposals below threshold; JSON-safe payload; determinism; empty→zero.
    - **Validates: 8.2**

### Phase 5 — Docs + review

- [x] 6. FAS + traceability + review + checkpoint
  - [x] 6.1 Mark **A2.10 Layered reflection → Built** in
    `docs/architecture/FAS_v2.1_AMENDMENTS.md` (code-state line pointing at
    `friday/cognition/reflection_layers.py`) and flip the A2.10 row in
    `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` from Partial → Built.
    - _Requirements: 8.3_
  - [x] 6.2 Write `docs/reviews/REVIEW_m20-reflection-v2.md` (architecture-compliance review
    + benchmark results) and run the full-suite checkpoint: **≥1614 + new M20 tests, 0
    failed**, no regressions.
    - _Requirements: 8.1, 8.3_

## Notes

- Tasks marked `*` are optional test sub-tasks; core implementation tasks are never optional.
- No duplicate reflection system: reuses the existing `ReflectionEngine`, `ReflectionRecord`,
  and the `reflection.completed` stream. The higher layers are pure consumers.
- Invariant preserved: Reflection PROPOSES (emits `memory.candidate` / `reflection.*`);
  Memory DECIDES. No layer writes memory or mutates any subsystem.
- Additive + safe: layers attached only in the guarded kernel-exec path; hermetic runs do no
  unbidden I/O; default path byte-unchanged.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "3.2", "3.3"] },
    { "id": 3, "tasks": ["3.4", "3.5", "3.6", "3.7"] },
    { "id": 4, "tasks": ["3.8", "4", "5.1"] },
    { "id": 5, "tasks": ["5.2", "6.1"] },
    { "id": 6, "tasks": ["6.2"] }
  ]
}
```
