# Implementation Plan: M21 (slice 1) — Failure Memory

## Overview

Deliver failure memory (A2.11, previously Absent) as a consumer of the M24 loop, reusing
the bounded `JSONFileStore` and the M24 `StructuredFailure`. Additive and kernel-driven.

**Language:** Python.

## Tasks

- [x] 1. Baseline — pre-M21 floor: **1431** tests green (post-M24).

- [x] 2. Failure tier
  - [x] 2.1 Add `MemoryTier.FAILURE` to `friday/memory/interfaces.py`.
    - _Requirements: 1.1_
  - [x] 2.2 Create `friday/memory/failure_memory.py`: `FailureRecord` + `FailureMemory`
    (attach/record/recall/has_failed_before/failure_count/statistics), backed by bounded
    `JSONFileStore`; consumes `verification.completed` + `recovery.proposed`; defensive
    handlers; `record_structured` consumes an M24 `StructuredFailure`.
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3; Design C1, C2_

- [x] 3. Reactive-loop + bootstrap integration
  - [x] 3.1 `friday/kernel/reactive_loop.py`: optional `failure_memory=`; attach it FIRST
    (before recovery) so the failure is recorded before the nested `recovery.proposed`
    annotates it. Default None → not attached (no disk writes in hermetic runs).
    - _Requirements: 2.2, 4.1; Design C3_
  - [x] 3.2 `friday/api/server.py`: attach a bounded `FailureMemory()` in the guarded
    `FRIDAY_USE_KERNEL_EXECUTION=1` block.
    - _Requirements: 4.2_

- [x]* 4. Tests (`tests/friday/test_m21_failure_memory.py`): record/recall/has_failed_before;
  structured recording; count + statistics; bounded storage; end-to-end loop consumption
  (records failure + recovery annotation); satisfied-not-remembered; defensive handlers.
  - **Validates: Properties 1–4**

- [x] 5. Docs — FAS A2.11 marked Built; traceability updated; after-milestone review;
  full-suite checkpoint (≥1431 + new tests, 0 failed).
  - _Requirements: 4.3_

## Notes

- Scope is the failure-memory slice of M21; the full seven-tier expansion and
  Retrieval-Router/Reflection-v2 integration remain future roadmap work.
- No duplicate systems: reuses `JSONFileStore`, `MemoryEntry`, and M24 `StructuredFailure`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1"] },
    { "id": 1, "tasks": ["2.2"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["4"] },
    { "id": 4, "tasks": ["5"] }
  ]
}
```
