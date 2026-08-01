# Design: M21 (slice 2) — Seven-Tier Memory Completion (Capability + Preference)

## Overview

This slice completes the FAS §A2.11.1 seven-tier memory model by adding the two remaining
tiers — **Capability** and **Preference** — additively, following the proven M21
`FailureMemory` template exactly. Each tier is a bounded `JSONFileStore`-backed, kernel-driven
memory that consumes events already on the bus, exposes the uniform `retrieve(query, top_k)`
surface (so it plugs into the M19 Retrieval Router), and is attached only within the guarded
kernel-execution path. No new persistence mechanism, no duplicate memory framework, no
application-specific logic.

The **Capability tier is a memory view, not an authority**: the evidence-only
`CompetenceModel` (Ch 28) remains the sole competence authority. `CapabilityMemory` records
what `competence.updated` reports so planning can *recall* capability knowledge; it never
recomputes or overrides competence. The **Preference tier** persists user preferences as
upsertable `(key, value)` records, distinct from volatile working-memory context.

## Architecture

```
   competence.updated ──▶ CapabilityMemory   ─┐
   preference signal  ──▶ PreferenceMemory    ├─ bounded JSONFileStore per tier
                                              │   (MemoryTier.CAPABILITY / PREFERENCE)
                                              ▼
              uniform retrieve(query, top_k) → M19 RetrievalRouter (register both tiers)
```

Both tiers mirror `FailureMemory`: `attach(kernel)` subscribes to the relevant event(s);
defensive handlers never raise; `record_*` direct APIs; `recall`/`get`/`all` queries; bounded
store; `retrieve` delegating to the store. The reactive-loop helper and bootstrap attach them
opt-in; the controller factory registers them in the router.

### Modified / new components

| Component | File | Change |
|---|---|---|
| Tier ids | `friday/memory/interfaces.py` | add `CAPABILITY` + `PREFERENCE` to `MemoryTier` (additive) |
| Capability tier | `friday/memory/capability_memory.py` (NEW) | `CapabilityRecord`, `CapabilityMemory` |
| Preference tier | `friday/memory/preference_memory.py` (NEW) | `PreferenceRecord`, `PreferenceMemory` |
| Router factory | `friday/memory/controller.py` | `build_retrieval_router` registers both when supplied |
| Loop wiring | `friday/kernel/reactive_loop.py` | optional `capability_memory=` / `preference_memory=` (opt-in) |
| Bootstrap | `friday/api/server.py` | attach both bounded tiers + register in router (guarded) |

## Components and Interfaces

### C1 — `MemoryTier` additions
Add `CAPABILITY = "capability"` and `PREFERENCE = "preference"` (additive; existing members
unchanged). The seven canonical tiers are then all representable.

### C2 — `CapabilityMemory` (mirrors `FailureMemory`)
- `CapabilityRecord` (JSON-projectable): `capability`, `environment`, `confidence`,
  `attempts`, `summary`, `timestamp`; `to_memory_entry()` → `MemoryEntry(tier=CAPABILITY, ...)`
  with metadata carrying the fields.
- `attach(kernel)` subscribes to `competence.updated`. `_on_competence(event)` reads
  `capability`, `environment`, `confidence`, `attempts` defensively; records/updates the memory
  (upsert by `(capability, environment)` — newest supersedes). Ignores malformed/empty events;
  never raises.
- `record_capability(*, capability, environment, confidence, attempts, summary="")` direct API.
- **Memory-not-authority:** it stores only what the event reported; it performs no competence
  math and exposes no gate/confidence-authority method (Requirement 2.3).
- Queries: `recall(capability?, environment?, limit)`; `retrieve(query, top_k)` delegating to
  the store. Bounded `JSONFileStore` (oldest evicted).

### C3 — `PreferenceMemory` (mirrors `FailureMemory`)
- `PreferenceRecord` (JSON-projectable): `key`, `value`, `description`, `timestamp`;
  `to_memory_entry()` → `MemoryEntry(tier=PREFERENCE, ...)`.
- `attach(kernel)` subscribes to a preference/user-preference signal already on the bus
  (the design task will grep for the real event type; if none exists, the tier still works via
  its direct API and simply receives no stream — documented, no invented type). Handler reads
  defensively; never raises.
- `record_preference(key, value, description="")` — **upsert** by `key` (newer supersedes:
  delete prior entry for that key, then store).
- Queries: `get(key)`, `all()`, `retrieve(query, top_k)`. Bounded `JSONFileStore`.

### C4 — Router factory registration
`build_retrieval_router(memory, *, failure_memory=None, capability_memory=None,
preference_memory=None, weights=None)` — additively register `capability_memory` under
`MemoryTier.CAPABILITY` and `preference_memory` under `MemoryTier.PREFERENCE` when supplied,
using the same `callable(getattr(store, "retrieve", None))` guard as the other tiers. Existing
behavior/signature for the current parameters is preserved (new params are keyword-only with
`None` defaults).

### C5 — Reactive-loop + bootstrap wiring
- `attach_reactive_loop(kernel, *, capability_memory=None, preference_memory=None, ...)` —
  attach each when supplied (opt-in, like `failure_memory`); default None → not attached (no
  disk writes in hermetic runs). Add both to the returned `ReactiveLoop` holder.
- `friday/api/server.py` (guarded block): construct bounded `CapabilityMemory()` +
  `PreferenceMemory()`, pass them to `attach_reactive_loop`, and pass them to
  `build_retrieval_router(...)` so they participate in routing. Additive; default path
  byte-unchanged; wiring failure logged, never crashes bootstrap.

## Data Models

- `MemoryTier.CAPABILITY` / `MemoryTier.PREFERENCE` (C1).
- `CapabilityRecord` / `PreferenceRecord` — reuse `MemoryEntry` for storage; no new store.
  All payloads JSON-safe.

## Correctness Properties

### Property 1: tier ids complete the seven-tier model
`MemoryTier` contains CAPABILITY + PREFERENCE; the seven canonical tiers each map to a value;
existing members unchanged.
**Validates: Requirements 1.1, 1.2**

### Property 2: capability record + recall + memory-not-authority
A `competence.updated` event records a recallable capability memory (by capability/
environment); re-delivery upserts (no unbounded duplicates); the tier exposes no competence
authority method and never recomputes competence; malformed events never raise.
**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

### Property 3: preference upsert + query
`record_preference`/preference signal stores a preference; a newer value for the same key
supersedes; `get`/`all` reflect the current set; malformed events never raise.
**Validates: Requirements 3.1, 3.2, 3.3**

### Property 4: bounded + uniform retrieve
Both stores never exceed `max_entries` (oldest evicted); `retrieve(query, top_k)` returns
relevance-ranked `MemoryEntry`s from the tier.
**Validates: Requirements 2.4, 3.3, 4.1**

### Property 5: router participation
Registered under CAPABILITY/PREFERENCE, both tiers contribute to a tier-unfiltered route and
are the only results under their respective tier filter.
**Validates: Requirements 5.1, 5.2**

### Property 6: reuse + isolation
Both modules use only `JSONFileStore`/`MemoryEntry`/`MemoryTier` (+ stdlib); no
application-specific logic; handlers never raise; opt-in wiring means no disk writes without a
supplied instance.
**Validates: Requirements 4.1, 4.2, 4.3, 6.1**

## Error Handling

Structured-error-model compliant (A2.14.2): every event handler catches narrowly and degrades
to a no-op, never raising into the bus (mirrors `FailureMemory`). Bootstrap wiring guarded and
logged. `BaseException` propagates. No silent blanket swallow without a justifying comment.

## Testing Strategy

Hypothesis property tests (≥100 examples, tagged `# Feature: m21-memory-seven-tiers,
Property N`) for Properties 1–6 using a fake/real `CognitiveKernel`, real `JSONFileStore` in
`tmp_path`, and the real `RetrievalRouter`. No benchmark (memory tiers are not measured
capabilities — consistent with M21 slice 1). Full regression suite must stay green.

## Traceability

- FAS Ch 14/50; v2.1 amendment **A2.11 — seven-tier memory** (Partial → Built; completes the
  four base tiers + failure with Capability + Preference).
- Reuses `JSONFileStore`/`MemoryEntry`, the `FailureMemory` pattern, and the M19 Retrieval
  Router. The `CompetenceModel` remains the competence authority (Capability tier is a memory
  view). No duplicate systems; no application-specific logic (Axiom 15).
