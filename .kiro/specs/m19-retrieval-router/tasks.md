# Implementation Plan: M19 — Retrieval Router

## Overview

Deliver the Retrieval Router (A2.7, previously *Absent*) as one general mechanism over the
existing uniform `retrieve(query, top_k) -> List[MemoryEntry]` surface. A draft
`friday/memory/retrieval_router.py` already exists and must be reviewed/hardened (not
assumed correct) before it is wired. All new code is additive; hermetic runs perform no
unbidden I/O. Property tests use Hypothesis (≥100 examples) tagged
`# Feature: m19-retrieval-router, Property N`.

**Language:** Python.

## Tasks

- [x] 1. Baseline verification (no code change) — record the current full-suite floor
  (expected **1438** green post-M21) before touching anything.
  - _Requirements: 7.3_

### Phase 1 — Router core (review + harden the drafted module)

- [x] 2. Router core in `friday/memory/retrieval_router.py`
  - [x] 2.1 Review the drafted `RetrievedItem` + `RetrievalRouter`; verify against the
    design: registration validation (TypeError on missing `retrieve`), weight clamping,
    name-replacement, `unregister`/`source_count`/`tiers`; `route` tier filtering, per-source
    rank scoring × weight, merge/sort/cap, `entry_id`-else-`(tier,content)` de-dup, and the
    per-source degradation guard. Replace the bare `except Exception:` with a narrowly
    justified, commented degradation boundary (A2.14.2 compliance, Requirement 5.3).
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3; Design C1, C2_
  - [x]* 2.2 Property test P1 (routing + tier filter: all-sources vs filtered; never returns
    an out-of-filter tier) — `tests/friday/test_m19_retrieval_router.py`. ≥100 examples.
    - **Property 1** — **Validates: 2.1, 2.2, 6.3**
  - [x]* 2.3 Property test P2 (weighted rank ordering: higher weight ranks ≥ equal-position
    lower weight; scores non-increasing; capped at top_k).
    - **Property 2** — **Validates: 3.1, 3.2, 3.3, 3.4**
  - [x]* 2.4 Property test P3 (provenance present; de-dup by entry_id / (tier,content);
    `to_dict()` round-trips through `json.dumps`).
    - **Property 3** — **Validates: 4.1, 4.2, 4.3**
  - [x]* 2.5 Property test P4 (failing-source isolation: a raising source is skipped, healthy
    results still returned, `route` never raises) + P5 (empty/degenerate → `[]`, bounds).
    - **Properties 4, 5** — **Validates: 5.1, 5.2, 2.3, 2.4**

### Phase 2 — Failure-memory participation

- [x] 3. Failure tier as a router source
  - [x] 3.1 Confirm `FailureMemory.retrieve(query, top_k)` (already added) satisfies the
    source contract; register it under `MemoryTier.FAILURE` in the factory (Task 4).
    - _Requirements: 6.1_
  - [x]* 3.2 Property test P6 (a real `FailureMemory` in a temp dir contributes FAILURE items
    to an unfiltered route by score; a `{FAILURE}` filter returns only those) —
    same test module.
    - **Property 6** — **Validates: 6.1, 6.2, 6.3**

### Phase 3 — Controller factory + bootstrap (additive)

- [x] 4. `friday/memory/controller.py`: add `build_retrieval_router(memory, *,
  failure_memory=None, weights=None)` that registers the backing `MemoryStore` of the
  episodic/semantic/procedural tiers (each tier's `._store`, which implements the uniform
  `retrieve`) and, when supplied, `failure_memory` under `MemoryTier.FAILURE`. Do NOT change
  any existing `FridayMemory` method behavior. Tiers lacking the surface are skipped by the
  same registration validation (no per-tier special-casing).
  - _Requirements: 7.1; Design C3_
  - [x]* 4.1 Test: factory over a real `FridayMemory` (temp dir) registers the expected tiers;
    a seeded episode/fact is retrievable through `route`; failure_memory participates when
    passed. Same test module.
    - **Validates: 7.1**

- [x] 5. `friday/api/server.py`: within the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block,
  build the router via the factory (passing the bootstrapped bounded `FailureMemory`) and
  expose it for planning. Default (flag off) path byte-unchanged; wiring failure degrades
  safely.
  - _Requirements: 7.2_

### Phase 4 — Benchmark (hermetic, not baselined)

- [x] 6. Deterministic retrieval benchmark
  - [x] 6.1 Create `friday/benchmarks/retrieval.py`: `RetrievalScenario`, `RetrievalMetrics`
    (coverage / correct-tier-rate / dedup-rate / mean rank of the planted relevant item,
    JSON + markdown), `RetrievalBenchmark` routing over synthetic multi-tier sources.
    Deterministic + hermetic (no LLM / network / wall-clock); domain-general (Axiom 15); NOT
    part of the 5-domain scorecard; never recorded into the committed baseline (mirrors the
    M23/M24 policy).
    - _Requirements: 8.2_
  - [x]* 6.2 Tests (`tests/friday/test_m19_retrieval_benchmark.py`): planted relevant items
    are retrieved and correctly attributed; JSON-safe payload; determinism (identical runs);
    empty → zero.
    - **Validates: 8.2**

### Phase 5 — Docs + review

- [x] 7. FAS + traceability + review + checkpoint
  - [x] 7.1 Mark **A2.7 Retrieval Router → Built** in
    `docs/architecture/FAS_v2.1_AMENDMENTS.md` (add a Code-state line pointing at
    `friday/memory/retrieval_router.py`) and flip the A2.7 row in
    `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` from Absent → Built.
    - _Requirements: 8.3_
  - [x] 7.2 Write `docs/reviews/REVIEW_m19-retrieval-router.md` (architecture-compliance
    review + benchmark results) and run the full-suite checkpoint: **≥1438 + new M19 tests,
    0 failed**, no regressions.
    - _Requirements: 8.1, 8.3_

## Notes

- Tasks marked `*` are optional test sub-tasks; core implementation tasks are never optional.
- No duplicate systems: reuses `MemoryStore` / `MemoryEntry` / `MemoryTier` and the M21
  `FailureMemory.retrieve`. Tier selection is data (registration + filter), not code branches.
- The only broad exception catch is the per-source degradation boundary in `route`, which
  must be commented/justified (A2.14.2) — no silent `except Exception: pass`.
- Additive + safe: the router is constructed only in the guarded kernel-exec path; hermetic
  tests/benchmarks perform no unbidden disk I/O.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "3.1"] },
    { "id": 3, "tasks": ["3.2", "4"] },
    { "id": 4, "tasks": ["4.1", "5", "6.1"] },
    { "id": 5, "tasks": ["6.2", "7.1"] },
    { "id": 6, "tasks": ["7.2"] }
  ]
}
```
