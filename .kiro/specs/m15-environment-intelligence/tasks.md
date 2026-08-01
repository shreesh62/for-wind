# Implementation Plan: M15 — Environment Intelligence (Fingerprints & Capability Invalidation)

## Overview

Deliver Environment Intelligence (A2.2, previously *Absent*) as one general fingerprinting +
change-detection mechanism over the existing `WorldState` universal perception. A pure
fingerprint library, a kernel-attached change monitor that emits invalidation proposals, and
a version-aware confidence helper. All new code is additive and inert without a kernel; no
application-specific logic (Axiom 15). Property tests use Hypothesis (≥100 examples) tagged
`# Feature: m15-environment-intelligence, Property N`.

**Language:** Python.

## Tasks

- [x] 1. Baseline verification (no code change) — confirmed the current full-suite floor:
  **1637** green post-M20 (measured at M20 close-out) via `python -m pytest tests`.
  - _Requirements: 7.3_

### Phase 1 — Fingerprint library (pure)

- [x] 2. Create `friday/perception/fingerprint.py`
  - [x] 2.1 `EnvironmentFingerprint` (frozen dataclass: digest, components dict,
    ui_fingerprint; `to_dict()`), `compute_fingerprint(world_state, *, platform=None,
    capability_version="", layout_version="")`, `compute_ui_fingerprint(world_state)`, and
    `version_confidence_factor(validated, current)`. Pure/total/deterministic; sparse
    WorldState never raises; window identity uses a GENERIC window kind (class/process),
    never title text (Axiom 15); a11y/ui signatures hash sorted role multisets independent
    of volatile text.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 5.1, 5.2, 5.3; Design C1, C2, C3, C4_
  - [ ]* 2.2 Property test P1 (fingerprint determinism + per-signal sensitivity + sparse
    safety) — `tests/friday/test_m15_environment_intelligence.py`. ≥100 examples.
    - **Property 1** — **Validates: 1.1, 1.2, 1.4**
  - [ ]* 2.3 Property test P2 (UI-fingerprint layout sensitivity + value-independence).
    - **Property 2** — **Validates: 2.1, 2.2, 2.3**
  - [ ]* 2.4 Property test P5 (version_confidence_factor: 1.0 on match, reduced on mismatch,
    defined on missing validated; total/never raises).
    - **Property 5** — **Validates: 5.1, 5.2, 5.3**

### Phase 2 — Change monitor (kernel-driven)

- [x] 3. Create `friday/perception/fingerprint_monitor.py`
  - [x] 3.1 `FingerprintMonitor`: `attach(kernel)` (no-op if None); `observe(env_key,
    world_state, **versions) -> "first_seen"|"unchanged"|"changed"` with a bounded per-key
    last-seen registry (oldest evicted beyond `max_environments`); on "changed" (kernel
    present) emit `environment.fingerprint_changed` then
    `environment.capabilities_invalidated` (JSON-safe, changed-components); first-seen
    records a baseline and emits nothing; the monitor mutates no competence; `observe`
    never raises. Plus `attach_fingerprint_monitor(kernel, *, monitor=None,
    max_environments=...)` reusable wiring helper.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 6.1, 6.2, 6.3; Design C5, C6_
  - [ ]* 3.2 Property test P3 (change detection: first_seen/unchanged/changed + bounded
    registry) — same test module. ≥100 examples.
    - **Property 3** — **Validates: 3.1, 3.2, 3.3, 3.4**
  - [ ]* 3.3 Property test P4 (invalidation emission: one of each event, JSON-safe, no
    competence mutation).
    - **Property 4** — **Validates: 4.1, 4.2, 4.3**
  - [ ]* 3.4 Property test P6 (isolation: no app/site/title identity branching; malformed/
    sparse never raises; no-op without kernel; only `environment.*` emitted).
    - **Property 6** — **Validates: 1.3, 6.1, 6.2, 6.3**

### Phase 3 — Bootstrap wiring (additive)

- [ ] 4. `friday/api/server.py`: within the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block,
  call `attach_fingerprint_monitor(kernel)` and expose it (`kernel.fingerprint_monitor`).
  Additive; default (flag-off) path byte-unchanged; wiring failure logged with structured
  context, never crashes bootstrap.
  - _Requirements: 7.1, 7.2; Design C7_

### Phase 4 — Benchmark (hermetic, not baselined)

- [ ] 5. Deterministic environment-intelligence benchmark
  - [ ] 5.1 Create `friday/benchmarks/environment.py`: `EnvironmentScenario`,
    `EnvironmentMetrics` (fingerprint stability rate, sensitivity rate, change-detection
    precision/recall over synthetic WorldState sequences; JSON + markdown),
    `EnvironmentBenchmark`. Deterministic + hermetic (no LLM/network/wall-clock);
    domain-general (Axiom 15); NOT part of the 5-domain scorecard; never recorded to the
    committed baseline.
    - _Requirements: 8.2_
  - [ ]* 5.2 Tests (`tests/friday/test_m15_environment_benchmark.py`): stable inputs → same
    digest; mutated → changed; change-detection precision/recall == 1.0 on the default
    scenarios; JSON-safe payload; determinism; empty→zero.
    - **Validates: 8.2**

### Phase 5 — Docs + review

- [ ] 6. FAS + traceability + review + checkpoint
  - [ ] 6.1 Mark **A2.2 Environment Intelligence → Built** in
    `docs/architecture/FAS_v2.1_AMENDMENTS.md` (code-state line pointing at
    `friday/perception/fingerprint.py` + `fingerprint_monitor.py`) and flip the A2.2 rows in
    `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` from Absent → Built.
    - _Requirements: 8.3_
  - [ ] 6.2 Write `docs/reviews/REVIEW_m15-environment-intelligence.md` (architecture-
    compliance review + benchmark results) and run the full-suite checkpoint: **≥1637 + new
    M15 tests, 0 failed**, no regressions.
    - _Requirements: 8.1, 8.3_

## Notes

- Tasks marked `*` are optional test sub-tasks; core implementation tasks are never optional.
- No duplicate perception system: reuses `WorldState` / `WindowInfo` / `UIElement` and the
  existing screenshot hash. Fingerprints are pure functions of generic signals.
- Invariant preserved: a UI/version change makes FRIDAY re-explore (emits invalidation),
  never silently wrong. The monitor PROPOSES invalidation via events; Exploration/competence
  decide. No app-, site-, or window-title-specific logic (Axiom 15).
- Additive + safe: the monitor is attached only in the guarded kernel-exec path; hermetic
  runs do no unbidden I/O; default path byte-unchanged.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "5.1"] },
    { "id": 4, "tasks": ["4", "5.2", "6.1"] },
    { "id": 5, "tasks": ["6.2"] }
  ]
}
```
