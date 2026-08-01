# Design: M21 (slice 1) — Failure Memory

## Overview

Failure Memory is the seventh memory tier: a persistent, queryable record of failures
that consumes the M24 failure→recovery loop. It reuses existing mechanisms — the bounded
`JSONFileStore`, the `MemoryEntry`/`MemoryTier` contracts, and the M24 `StructuredFailure`
model + kernel events — introducing no duplicate persistence or taxonomy.

## Architecture

Failure Memory subscribes to the two M24 event types on the kernel bus:
`verification.completed` (records a failure for an unmet verdict) and `recovery.proposed`
(annotates the just-recorded failure with the proposed recovery). It also exposes direct
`record_failure` / `record_structured` APIs so producers holding a live `StructuredFailure`
can record the richest form. Persistence is the existing bounded JSON store.

### Ordering invariant
In `attach_reactive_loop`, Failure Memory subscribes BEFORE the `RecoveryEngine`. Because
the `EventBus` delivers to handlers in subscription order, the failure is recorded before
recovery publishes the nested `recovery.proposed` that annotates it.

### Modified / new components

| Component | File | Change |
|---|---|---|
| Failure tier | `friday/memory/failure_memory.py` (NEW) | `FailureRecord`, `FailureMemory` |
| Tier enum | `friday/memory/interfaces.py` | add `MemoryTier.FAILURE` |
| Loop wiring | `friday/kernel/reactive_loop.py` | optional `failure_memory=`; attach first |
| Bootstrap | `friday/api/server.py` | attach a bounded `FailureMemory` |

## Components and Interfaces

### C1 — `FailureRecord` (JSON-projectable dataclass)
requirement, domain, category, capability, environment, goal_id, severity, message,
recoverable, recovery_class, recovery_actionable, timestamp. `to_memory_entry()` maps to
a `MemoryEntry(tier=FAILURE, ...)`.

### C2 — `FailureMemory`
- `attach(kernel)` subscribes to `verification.completed` + `recovery.proposed`.
- `_on_verification` records unmet verdicts (ignores satisfied / empty payloads; never
  raises). `_on_recovery` annotates the newest matching-goal record with the recovery
  class and whether a recovery alternative was chosen (actionable).
- `record_failure(...)` / `record_structured(StructuredFailure)` — direct recording.
- Query: `recall(capability?, environment?, domain?, limit)`,
  `has_failed_before(requirement, capability?, environment?)`,
  `failure_count(...)`, `statistics()`.
- Backed by bounded `JSONFileStore` (oldest evicted at `max_entries`).

### C3 — Reactive-loop integration
`attach_reactive_loop(kernel, failure_memory=...)` attaches it (first) when supplied.
Default None → not attached (no disk writes in hermetic runs). Production bootstrap
supplies `FailureMemory()`.

## Data Models

- `MemoryTier.FAILURE` — new tier id.
- `FailureRecord` — as C1. Reuses `MemoryEntry` for storage. Reuses M24
  `StructuredFailure` on the `record_structured` path (no new taxonomy).

## Correctness Properties

### Property 1: record + recall
A recorded failure is recallable by capability/environment/domain and
`has_failed_before` matches its requirement.
**Validates: Requirements 1.1, 1.2, 3.1, 3.2**

### Property 2: bounded storage
Storage never exceeds `max_entries` (oldest evicted).
**Validates: Requirements 1.3**

### Property 3: loop consumption
An attached FailureMemory records an unmet verdict and annotates it with the proposed
recovery; a satisfied verdict is not recorded.
**Validates: Requirements 2.1, 2.2**

### Property 4: defensive handlers
Malformed/empty events never raise and never record.
**Validates: Requirements 2.3**

## Error Handling

Structured-error-model compliant: event handlers catch narrowly and degrade to a no-op,
never raising into the bus (mirrors the M24 subscribers). Empty/malformed payloads are
ignored rather than recorded.

## Testing Strategy

Unit tests for record/recall/count/statistics, bounded storage, direct structured
recording, and defensive handlers; an integration test attaches FailureMemory to a real
kernel via `attach_reactive_loop` and publishes a verdict to prove end-to-end recording +
recovery annotation. Full regression suite stays green.

## Traceability

- FAS Ch 14/50 (memory tiers); v2.1 amendment **A2.11 — failure memory** (was Absent).
- Consumes M24 (`verification.completed`/`recovery.proposed`, `StructuredFailure`).
