# Design: M19 — Retrieval Router

## Overview

The Retrieval Router is one general mechanism that routes a retrieval query across
registered memory sources, then merges, ranks, de-duplicates, and returns a single
provenance-carrying result list. It reuses the existing uniform retrieval surface —
`retrieve(query, top_k) -> List[MemoryEntry]`, already implemented by every `MemoryStore`
and by `FailureMemory` — so no source internals are touched and no duplicate persistence
or taxonomy is introduced. Tier selection is **data** (a registration attribute + an
optional per-call filter), never a per-tier `if`/`else` branch (Axiom 15).

This satisfies FAS §A2.7.1: the router selects sources per request *before* any search
runs; vector/keyword search is one source strategy among many, never the universal default.

## Architecture

```
caller ── route(query, tiers?, top_k) ──▶ RetrievalRouter
                                             │  for each registered source
                                             │  whose tier passes the filter:
                                             ▼
                         source.retrieve(query, per_source_k)  ──▶ List[MemoryEntry]
                                             │  (a raising source is skipped)
                                             ▼
                   normalize → RetrievedItem (rank-based score × weight, provenance)
                                             ▼
                       merge all → sort by score desc → de-dup → cap top_k
                                             ▼
                                   List[RetrievedItem]
```

Sources are registered under a unique name + an owning `MemoryTier` + an optional weight.
The router is backend-agnostic: it scores by best-first *rank* per source (not by each
backend's internal score), so heterogeneous sources merge fairly.

### Modified / new components

| Component | File | Change |
|---|---|---|
| Router | `friday/memory/retrieval_router.py` (NEW, drafted) | `RetrievedItem`, `RetrievalRouter` |
| Uniform surface | `friday/memory/failure_memory.py` | `retrieve(query, top_k)` (already added) |
| Controller helper | `friday/memory/controller.py` | `build_retrieval_router(...)` factory (additive) |
| Bootstrap | `friday/api/server.py` | register router in the guarded kernel-exec path |

## Components and Interfaces

### C1 — `RetrievedItem` (JSON-projectable dataclass)
Fields: `content`, `tier` (str), `score` (float), `source` (name — provenance),
`entry_id`, `timestamp`, `metadata`. `to_dict()` rounds score and returns a plain dict for
replay/logging (Requirement 4.3).

### C2 — `RetrievalRouter`
- **Registration:** `register_source(name, tier, source, *, weight=1.0)` — validates the
  source exposes `retrieve` (TypeError otherwise, Requirement 1.2), clamps weight ≥ 0,
  replaces any prior registration for `name` (Requirement 1.4). `unregister(name) -> bool`;
  `source_count` property; `tiers() -> List[MemoryTier]` (distinct, Requirement 1.3).
- **Routing:** `route(query, *, tiers=None, top_k=10, per_source_k=10) -> List[RetrievedItem]`.
  - `tiers=None` → query all; else query only sources whose tier ∈ `tiers` (Requirement 2.1–2.2).
  - Each source is asked for `per_source_k`; a source that raises is skipped (Requirement 5.1);
    an empty/None return contributes nothing.
  - Per-source scoring: `rank_score = 1.0 - (i / n)` for position `i` of `n` results
    (top hit = 1.0), then `× weight` (Requirement 3.1, 3.4).
  - Merge → sort by score desc (Requirement 3.2) → de-dup → cap at `top_k` (Requirement 2.4, 3.3).
- **De-duplication:** `_dedupe` keeps the first (highest-scored, since pre-sorted)
  occurrence, keyed by `entry_id` if present else `(tier, content)` (Requirement 4.2).

### C3 — Controller factory (`friday/memory/controller.py`)
`build_retrieval_router(memory, *, failure_memory=None, weights=None) -> RetrievalRouter`:
a thin, additive helper that registers the persistent tiers exposed by `FridayMemory`
(episodic/semantic/procedural stores) and, when supplied, `failure_memory` under
`MemoryTier.FAILURE`. It does not alter any existing `FridayMemory` method (Requirement 7.1).
Weights default to 1.0 and may be overridden per tier via `weights`.

> Note: the episodic/procedural/semantic tiers wrap their own stores; the factory registers
> whichever expose the uniform `retrieve(query, top_k)` surface. Any tier lacking it is
> skipped by the same validation as C2 (kept general — no per-tier special-casing).

### C4 — Bootstrap wiring (`friday/api/server.py`)
Within the existing guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block, construct the router via
C3 (passing the already-bootstrapped bounded `FailureMemory`) and expose it for planning.
Default (flag off) path is byte-unchanged; wiring failure degrades safely (Requirement 7.2).

## Data Models

- Reuses `MemoryEntry` / `MemoryTier` (no new persistence).
- `RetrievedItem` (C1) is the only new type — a normalized, provenance-carrying view over a
  `MemoryEntry`. `tier` is stored as the entry's tier value, falling back to the source's
  registered tier when an entry omits it.

## Correctness Properties

### Property 1: routing + tier filter
For registered sources, `route(query)` queries all; `route(query, tiers=T)` returns only
items whose tier ∈ T and never items from a tier ∉ T.
**Validates: Requirements 2.1, 2.2, 6.3**

### Property 2: weighted rank ordering
Given two sources returning results at equal positions, the higher-weighted source's item
sorts at least as high; results are non-increasing in score and capped at `top_k`.
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

### Property 3: provenance + de-duplication + JSON
Every returned item carries a registered `source` and a tier; duplicates (same entry_id, or
same tier+content) appear at most once; `to_dict()` round-trips through `json.dumps`.
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 4: failing-source isolation
With one source that always raises and one healthy source, `route` never raises and returns
the healthy source's results merged/ranked.
**Validates: Requirements 5.1, 5.2**

### Property 5: empty/degenerate routing
No registered sources, or a tier filter matching none, yields `[]` (never an error);
`per_source_k`/`top_k` bounds are respected.
**Validates: Requirements 2.3, 2.4**

### Property 6: failure-memory participation
A `FailureMemory` registered under `FAILURE` contributes failure items to an unfiltered
route by score, and a `{FAILURE}` filter returns only those.
**Validates: Requirements 6.1, 6.2, 6.3**

## Error Handling

Structured-error-model compliant (A2.14.2): the only broad catch is the per-source guard in
`route`, which is a deliberate **degradation boundary** — a single bad source must not break
retrieval for the rest. It is annotated with a justifying comment (Requirement 5.3) rather
than a silent `except Exception: pass`. Registration fails fast (TypeError) on an invalid
source. No handler swallows errors silently elsewhere.

## Testing Strategy

Hypothesis property tests (≥100 examples, tagged
`# Feature: m19-retrieval-router, Property N`) for Properties 1–6 using in-memory fake
sources plus a real `JSONFileStore` and a real `FailureMemory` in a temp dir. A deterministic,
hermetic **retrieval benchmark** (`friday/benchmarks/retrieval.py`) measures routing
correctness/coverage over synthetic multi-tier sources; it is NOT part of the 5-domain
scorecard and is never written to the committed baseline (mirrors the M23/M24 policy). Full
regression suite must stay green.

## Traceability

- FAS Ch 14.13; v2.1 amendment **A2.7 — Retrieval Router** (was Absent → Built).
- Consumes the M21 failure tier (`FailureMemory.retrieve`) and the existing `MemoryStore`
  uniform surface. No duplicate memory system; no application-specific logic.
