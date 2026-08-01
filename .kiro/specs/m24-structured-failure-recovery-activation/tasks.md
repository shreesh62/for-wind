# Implementation Plan: M24 — Structured Failure Taxonomy & Verification-Event Activation

## Overview

Activate the dormant failure→recovery/competence/reflection loop and formalize failures
as first-class objects, using only existing mechanisms (no duplicate systems). All new
code is additive and inert without a kernel. Property tests use Hypothesis (≥100
examples) tagged `# Feature: m24-structured-failure-recovery-activation, Property N`.

**Language:** Python.

## Tasks

- [x] 1. Baseline verification (no code change) — pre-M24 floor: **1403** tests green.

### Phase 1 — Structured error model + first-class failures

- [x] 2. Failure taxonomy + classifier + StructuredFailure
  - [x] 2.1 Created `friday/verification/failure.py`: `FailureDomain` (9 stage domains),
    `Severity`, `classify_error_category()` (total, data-driven exact map + generic
    substring signals over existing categories; unknown→UNKNOWN), `StructuredFailure`
    with `from_action_result`/`from_verdict`/`to_payload`. Reuses the existing
    `RecoveryLevel` ordinals for `recommended_recovery` (no new recovery taxonomy).
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3; Design C1, C2_
  - [x]* 2.2 Property test P1 (classifier total over arbitrary text; every known category
    → non-UNKNOWN; case-insensitive) — `tests/friday/test_m24_failure_model.py`. ≥200 examples. PASS.
    - **Property 1** — **Validates: 1.1, 1.2**
  - [x]* 2.3 Property test P2 (constructors never raise; payload JSON-serializes;
    unrecoverable→HUMAN escalation). ≥100 examples. PASS.
    - **Property 2** — **Validates: 2.1, 2.2, 2.3**

### Phase 2 — Verification-event producer (recovery activation)

- [x] 3. VerificationEventPublisher
  - [x] 3.1 Created `friday/verification/publisher.py`: `VerificationEventPublisher` with
    `attach(kernel)` + `publish_verdict(...)` emitting `verification.completed` in the
    subscribers' payload shape; no-op without a kernel; never raises. Payload is
    JSON-safe (live evidence replaced by `_summarize_evidence` JSON summary; `evidence`
    key is None so subscribers build an empty bundle) — replay-compatible.
    - _Requirements: 3.1, 3.2; Design C3_
  - [x]* 3.2 Test P3 (no-kernel no-op; correct event type + all payload keys; logical_time
    = tick+1; JSON persistence-safe) — `tests/friday/test_m24_publisher.py`. PASS.
    - **Property 3** — **Validates: 3.1, 3.2**
  - [x]* 3.3 Integration test P4 — REAL `RecoveryEngine` + publisher on a REAL
    `CognitiveKernel`: a failed verdict emits `recovery.proposed` (dormant loop
    ACTIVATED); a satisfied verdict emits none. PASS.
    - **Property 4** — **Validates: 3.3**

### Phase 3 — Observability as an event consumer

- [x] 4. FailureLogSubscriber
  - [x] 4.1 Created `friday/observability/__init__.py` + `friday/observability/failure_log.py`:
    `FailureLogSubscriber.attach(kernel)` subscribing to `verification.completed` +
    `recovery.proposed`, emitting one structured log record per FAILURE event (level from
    severity; subsystem/goal/correlation/logical_time/failure_domain/failure_class in
    `extra`); satisfied verdicts not logged; never raises into the bus.
    - _Requirements: 4.1, 4.2, 4.3; Design C4_
  - [x]* 4.2 Test P5 (one record per failure event; satisfied not logged; recovery.proposed
    logged; structured fields present; level from severity; never raises on malformed
    event) — `tests/friday/test_m24_observability.py`. PASS.
    - **Property 5** — **Validates: 4.1, 4.2, 4.3**

### Phase 4 — Production wiring (additive)

- [x] 5. Wire the publisher into the Operator verdict path
  - [x] 5.1 `friday/operator.py`: added optional `kernel=None`; builds a
    `VerificationEventPublisher(kernel=kernel)`; `_verify_requirements` publishes each
    verdict. No-op and byte-identical when `kernel` is absent (benchmark runner + unit
    tests unaffected).
    - _Requirements: 5.1, 5.2, 5.3; Design C5_
  - [x]* 5.2 Test P6 (no kernel ⇒ no events, verdicts still computed; with a kernel ⇒ one
    `verification.completed` per requirement; satisfied→satisfied=True) —
    `tests/friday/test_m24_operator_wiring.py`. PASS.
    - **Property 6** — **Validates: 5.1, 5.2**

### Phase 5 — Docs + review

- [x] 6. FAS amendment A2.14 + after-milestone review
  - [x] 6.1 Added amendment **A2.14 — Structured Failure & Recovery Activation** to
    `docs/architecture/FAS_v2.1_AMENDMENTS.md` (§A2.14.1–.5) and a traceability row.
    - _Requirements: —_
  - [x] 6.2 Full-suite checkpoint: **1422 passed, 0 failed** (1403 floor + 19 M24 tests),
    no regressions; wrote `docs/reviews/REVIEW_m24-structured-failure-recovery-activation.md`.
    - _Requirements: 5.3_

### Phase 6 — Production loop activation (end-to-end wiring)

- [x] 7. Wire the reactive loop into the production bootstrap
  - [x] 7.1 Created `friday/kernel/reactive_loop.py::attach_reactive_loop(kernel)` — one
    reusable helper that attaches recovery + competence + reflection (+ observability)
    to a kernel (function-local imports; no cycles; components isolate their own
    exceptions). Returns a `ReactiveLoop` holding the attached components; supports
    reusing injected components and disabling logging.
    - _Requirements: 3.3, 4.1; Design C3, C4_
  - [x] 7.2 `friday/api/server.py`: in the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block,
    call `attach_reactive_loop(kernel)` and pass `kernel=kernel` to the Operator factory
    so verdicts drive the live loop. Additive: default (flag off) unchanged; wiring
    failure falls back safely.
    - _Requirements: 3.3, 5.1_
  - [x]* 7.3 End-to-end test (`tests/friday/test_m24_reactive_loop.py`): one failed verdict
    → `recovery.proposed` AND `competence.updated` AND a structured log record; logging
    toggle; component reuse. Full suite **1426 passed, 0 failed**. PASS.
    - **Validates: 3.3, 4.1**

### Phase 7 — Recovery-rate benchmark (audit objective 5)

- [x] 8. Deterministic recovery-rate benchmark over the active loop
  - [x] 8.1 Created `friday/benchmarks/recovery.py`: `RecoveryScenario`, `RecoveryMetrics`
    (recovery_rate / proposal_rate / by_domain / by_failure_class, JSON + markdown),
    `RecoveryBenchmark` (feeds synthetic failure verdicts through a real kernel wired with
    the reactive loop; counts actionable recoveries). Deterministic, hermetic (no LLM /
    network / wall-clock); NOT part of the 5-domain scorecard; never recorded to the
    committed baseline (mirrors the M23 web-independence policy). Domain-general
    scenarios (Axiom 15).
    - _Requirements: 3.3; audit objective 5_
  - [x]* 8.2 Tests (`tests/friday/test_m24_recovery_benchmark.py`): default scenarios yield
    actionable recoveries; JSON-safe payload; determinism (identical runs); empty→zero;
    domain classification. Measured live: **6/6 failures → actionable recoveries, recovery
    rate 1.0** across 4 domains (perception/execution/environment/verification). Full
    suite **1431 passed, 0 failed**. PASS.
    - **Validates: 3.3**

## Notes

- Tasks marked `*` are optional test sub-tasks; core implementation tasks are never optional.
- No new recovery taxonomy: `FailureClass`/`RecoveryLevel` are reused. `FailureDomain` is
  an orthogonal *stage* dimension.
- All new code is additive and inert without a kernel; rollback = do not inject a kernel.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1"] },
    { "id": 1, "tasks": ["2.2", "2.3", "3.1"] },
    { "id": 2, "tasks": ["3.2", "3.3", "4.1"] },
    { "id": 3, "tasks": ["4.2", "5.1"] },
    { "id": 4, "tasks": ["5.2", "6.1"] },
    { "id": 5, "tasks": ["6.2"] }
  ]
}
```
