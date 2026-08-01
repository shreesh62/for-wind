# Implementation Plan: M21 (slice 2) — Seven-Tier Memory Completion

## Overview

Complete the FAS §A2.11.1 seven-tier memory model by adding the **Capability** and
**Preference** tiers additively, mirroring the M21 `FailureMemory` template (bounded
`JSONFileStore`, kernel-driven, defensive, uniform `retrieve`, opt-in wiring). The
`CompetenceModel` remains the competence authority — the Capability tier is a memory view. No
duplicate systems; no application-specific logic. All new code is additive and inert without a
kernel. Property tests use Hypothesis (≥100 examples) tagged
`# Feature: m21-memory-seven-tiers, Property N`.

**Language:** Python.

## Tasks

- [x] 1. Baseline verification (no code change) — confirmed the current full-suite floor:
  **1677** green post-M22 (measured at M22 close-out) via `python -m pytest tests`.
  - _Requirements: 6.3_

### Phase 1 — Tier ids + the two tiers

- [x] 2. Tier identifiers
  - [x] 2.1 Add `CAPABILITY = "capability"` and `PREFERENCE = "preference"` to
    `friday/memory/interfaces.py::MemoryTier` (additive; existing members unchanged).
    - _Requirements: 1.1, 1.2; Design C1_

- [x] 3. Capability tier — `friday/memory/capability_memory.py` (NEW)
  - [x] 3.1 `CapabilityRecord` (capability/environment/confidence/attempts/summary/timestamp;
    `to_memory_entry()` → `MemoryEntry(tier=CAPABILITY,...)`) + `CapabilityMemory`: bounded
    `JSONFileStore`; `attach(kernel)` subscribes to `competence.updated`; `_on_competence`
    upserts by `(capability, environment)` defensively (never raises); `record_capability(...)`
    direct API; `recall(capability?, environment?, limit)`; uniform `retrieve(query, top_k)`.
    Memory-not-authority: no competence math, no gate/authority method (records only what the
    event reported).
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 4.3; Design C2_

- [x] 4. Preference tier — `friday/memory/preference_memory.py` (NEW)
  - [x] 4.1 First grep for a real preference/user-preference event type on the bus; use it if
    present (else the tier still works via its direct API, documented — no invented type).
    `PreferenceRecord` (key/value/description/timestamp; `to_memory_entry()` →
    `MemoryEntry(tier=PREFERENCE,...)`) + `PreferenceMemory`: bounded `JSONFileStore`;
    `attach(kernel)` subscribes to the preference signal (if any); `record_preference(key,
    value, description="")` UPSERT by key (newer supersedes); `get(key)` / `all()`; uniform
    `retrieve(query, top_k)`; defensive handlers never raise.
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3; Design C3_

- [x]* 5. Property tests (`tests/friday/test_m21_memory_seven_tiers.py`, ≥100 examples):
  P1 tier ids complete the seven-tier model; P2 capability record+recall+upsert+memory-not-
  authority+malformed-safe; P3 preference upsert+get/all+malformed-safe; P4 bounded storage
  + uniform retrieve for both; P6 reuse/isolation (only JSONFileStore/MemoryEntry/MemoryTier
  +stdlib; handlers never raise). (P5 router participation is Task 6.1's test.)
  - **Properties 1, 2, 3, 4, 6** — **Validates: 1.1, 1.2, 2.1-2.4, 3.1-3.3, 4.1-4.3, 6.1**

### Phase 2 — Retrieval-router participation

- [x] 6. `friday/memory/controller.py`: extend `build_retrieval_router(...)` with keyword-only
  `capability_memory=None` / `preference_memory=None`, registering each (when supplied) under
  `MemoryTier.CAPABILITY` / `MemoryTier.PREFERENCE` using the same `callable(retrieve)` guard.
  Preserve the existing signature/behavior for current parameters.
  - _Requirements: 5.1, 5.2; Design C4_
  - [x]* 6.1 Property test P5 (both tiers, registered, contribute to an unfiltered route and
    are the only results under their tier filter) — same test module.
    - **Property 5** — **Validates: 5.1, 5.2**

### Phase 3 — Reactive-loop + bootstrap wiring (additive, opt-in)

- [x] 7. `friday/kernel/reactive_loop.py`: add optional `capability_memory=` /
  `preference_memory=` params; attach each when supplied (opt-in, like `failure_memory`); add
  both to the `ReactiveLoop` holder. Default None → not attached (no disk writes in hermetic
  runs).
  - _Requirements: 6.1; Design C5_

- [x] 8. `friday/api/server.py`: in the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block,
  construct bounded `CapabilityMemory()` + `PreferenceMemory()`, pass them to
  `attach_reactive_loop(...)`, and pass them to `build_retrieval_router(...)` so they
  participate in routing. Additive; default path byte-unchanged; wiring failure logged, never
  crashes bootstrap.
  - _Requirements: 6.2; Design C5_

### Phase 4 — Docs + review

- [x] 9. FAS + traceability + review + checkpoint
  - [x] 9.1 Mark **A2.11 seven-tier memory → Built** in
    `docs/architecture/FAS_v2.1_AMENDMENTS.md` (note all seven tiers now exist) and flip the
    A2.11 seven-tier row in `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` from Partial →
    Built; update the "Summary by state" prose so NOTHING remains Partial/Absent (v2.1 fully
    Built).
    - _Requirements: 7.2_
  - [x] 9.2 Write `docs/reviews/REVIEW_m21-memory-seven-tiers.md` (architecture-compliance
    review) and run the full-suite checkpoint: **≥1677 + new tests, 0 failed**, no
    regressions. Note this closes the Architecture v2.1 build-out entirely.
    - _Requirements: 7.1, 7.2_

## Notes

- Tasks marked `*` are optional test sub-tasks; core implementation tasks are never optional.
- No duplicate systems: reuses `JSONFileStore` / `MemoryEntry` / `MemoryTier`, the
  `FailureMemory` pattern, and the M19 Retrieval Router. The `CompetenceModel` stays the
  competence authority (Capability tier is a memory view).
- Invariant preserved: bounded storage, defensive handlers never raise, opt-in wiring (no disk
  writes without a supplied instance), no application-specific logic (Axiom 15).
- No benchmark: memory tiers are not measured capabilities (consistent with M21 slice 1).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["3.1", "4.1"] },
    { "id": 3, "tasks": ["5", "6"] },
    { "id": 4, "tasks": ["6.1", "7"] },
    { "id": 5, "tasks": ["8", "9.1"] },
    { "id": 6, "tasks": ["9.2"] }
  ]
}
```
