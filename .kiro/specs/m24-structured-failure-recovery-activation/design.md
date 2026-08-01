# Design: M24 — Structured Failure Taxonomy & Verification-Event Activation

## Overview

Implement, using **only existing mechanisms** (no duplicated systems), the audit's
architectural objectives 1–4:

1. **Structured Error Model** — replace the free-form `ActionResult.error_category`
   string convention with a canonical, classifiable taxonomy, without rewriting the
   ~19 existing producers (they keep emitting strings; a pure classifier maps them).
2. **Unified Observability** — logging becomes a *consumer of the event system*: a
   subscriber turns failure/recovery kernel events into structured log records
   (level, subsystem id, goal id, correlation id, logical time).
3. **Failure Classification** — failures become first-class objects carrying domain,
   severity, confidence, recoverability, recommended recovery path, and evidence.
4. **Recovery Framework activation** — close the dormant reactive loop.

## Architecture

### Architectural rationale (the root-cause finding)

Recon established a concrete architectural defect: `RecoveryEngine`,
`CompetenceModel`, and `ReflectionEngine` all **subscribe** to the
`verification.completed` kernel event, but **no `friday/` module publishes it**. The
entire failure → recovery / competence / reflection loop is therefore **dormant** in
production. M24's core is the *missing producer* that activates this loop — a genuine
mechanism improvement, not legacy polish.

We deliberately do NOT introduce a new recovery taxonomy. The existing
`recovery.engine.FailureClass` (recoverability: transient/precondition/capability/…)
and `RecoveryLevel` (escalation ladder) are reused verbatim. M24 adds an **orthogonal**
dimension — `FailureDomain` (the *stage/subsystem* a failure originated in:
perception/resource/environment/capability/verification/planning/execution/external) —
because "where did it fail" and "how recoverable is it" are independent and both useful.

### Modified / new subsystems

| Component | File | Change |
|---|---|---|
| Failure model | `friday/verification/failure.py` (NEW) | `FailureDomain`, `Severity`, `classify_error_category()`, `StructuredFailure` |
| Verification producer | `friday/verification/publisher.py` (NEW) | `VerificationEventPublisher` — publishes `verification.completed` |
| Observability | `friday/observability/failure_log.py` (NEW package) | `FailureLogSubscriber` — events → structured logs |
| Production wiring | `friday/operator.py` | additive optional `kernel=` injection; publish verdicts |
| Docs | `docs/architecture/FAS_v2.1_AMENDMENTS.md` | amendment A2.14 |

## Components and Interfaces

Runtime contracts for each component:

### C1 — `FailureDomain` / `Severity` / `classify_error_category`
- `FailureDomain(str, Enum)`: `PERCEPTION, RESOURCE, ENVIRONMENT, CAPABILITY, VERIFICATION, PLANNING, EXECUTION, EXTERNAL_SERVICE, UNKNOWN`.
- `Severity(IntEnum)`: `LOW=0, MEDIUM=1, HIGH=2, CRITICAL=3`.
- `classify_error_category(category: Optional[str]) -> FailureDomain` is a **total, pure**
  function over a module-level data map from the existing free-form strings
  (`target_not_found`, `adapter_failed`, `perception_unavailable`, `desktop_error`,
  `timeout`, `blocked`, …). Unknown/empty ⇒ `UNKNOWN`. No app/site logic (Axiom 15) —
  the map is DATA keyed on generic category tokens, never application identity.

### C2 — `StructuredFailure` (frozen dataclass, the first-class failure)
Fields: `domain: FailureDomain`, `severity: Severity`, `category: str` (original),
`message: str`, `confidence: float` (of the classification, [0,1]), `recoverable: bool`,
`recommended_recovery: int` (a `RecoveryLevel` ordinal), `goal_id`, `capability`,
`environment`, `requirement`, `evidence: dict` (provenance). `to_payload()` →
JSON-safe dict. Constructors:
- `from_action_result(result, *, goal_id="", capability="", environment="")` — maps
  `ActionStatus`→severity, `error_category`→domain, `status in {BLOCKED}`/
  `NEEDS_REPAIR`→recoverable, sets recommended recovery from domain/severity.
- `from_verdict(verdict, *, goal_id="", capability="", environment="")` — an unmet
  `RequirementVerdict` (from the Evidence Law) → `VERIFICATION`/`PLANNING` domain.
Purity: constructors never raise; missing fields default safely.

### C3 — `VerificationEventPublisher`
- `attach(kernel)` stores the kernel. `publish_verdict(*, goal_id, requirement,
  satisfied, evidence, capability="", environment="", reversible=True, blocked=False,
  competence=1.0)` builds a `verification.completed` Event via `make_event` (source
  `"verification"`, logical_time = `kernel.health()["tick"]+1`) with the exact payload
  shape the existing subscribers read, then `kernel.publish_event(...)`.
- **No kernel ⇒ silent no-op.** Never raises into the caller. This is what activates
  `RecoveryEngine` / `CompetenceModel` / `ReflectionEngine`.

### C4 — `FailureLogSubscriber` (observability)
- `attach(kernel)` subscribes to `verification.completed` and `recovery.proposed`.
- Emits one structured `logging` record per event: log level from `Severity`
  (CRITICAL→error, HIGH→warning, else info), with `subsystem`, `goal_id`,
  `correlation_id`, `logical_time`, `domain`, `failure_class` in the record's
  `extra`. Uses `classify_error_category` for the domain. Never raises (a broken
  handler must not break the bus — mirrors `EventBus` isolation).
- Logging is thus a *consumer of the event system*, replay-compatible (events persist
  in the append-only `EventStore`).

### C5 — Production wiring (additive, safe)
- `Operator.__init__` gains optional `kernel=None`; when present it builds a
  `VerificationEventPublisher.attach(kernel)`.
- `_verify_requirements` publishes a `verification.completed` per requirement verdict
  (satisfied or not) when a publisher exists. **When `kernel` is absent (benchmark
  runner, unit tests) behavior is byte-identical** — no event, no change.

## Data Models

- **`FailureDomain(str, Enum)`** — 9 members (perception, resource, environment,
  capability, verification, planning, execution, external_service, unknown).
- **`Severity(IntEnum)`** — LOW=0, MEDIUM=1, HIGH=2, CRITICAL=3.
- **`StructuredFailure`** (frozen dataclass) — fields listed in C2; `to_payload() -> dict`
  is JSON-safe (enums projected to their values/ordinals).
- **`verification.completed` payload** — `{goal_id, satisfied, requirement, evidence,
  capability, environment, reversible, blocked, competence}` (the shape existing
  subscribers already read). Reused, not redefined.
- Existing reused models: `recovery.engine.FailureClass`, `RecoveryLevel`; `events.event.Event`.

## Correctness Properties

### Property 1: classifier totality
`classify_error_category` is a total function; every known category maps to a
non-`UNKNOWN` `FailureDomain`; no app/site branching.
**Validates: Requirements 1.1, 1.2**

### Property 2: failure model safety
`StructuredFailure.from_action_result`/`from_verdict` never raise and `to_payload()`
round-trips to JSON-safe primitives.
**Validates: Requirements 2.1, 2.2, 2.3**

### Property 3: publisher contract
Publisher is a no-op without a kernel; with a kernel it emits exactly a
`verification.completed` event carrying the required payload keys.
**Validates: Requirements 3.1, 3.2**

### Property 4: dormant loop activation
A real `RecoveryEngine` + publisher on a real kernel yields `recovery.proposed` on a
failed verdict.
**Validates: Requirements 3.3**

### Property 5: observability consumer
The log subscriber emits exactly one structured record per failure event and never
raises into the bus.
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 6: additive wiring
Operator without a kernel is byte-identical to pre-M24; with a kernel it publishes one
verdict event per requirement.
**Validates: Requirements 5.1, 5.2**

## Error Handling

Every new component follows the structured-error-model rule: no bare `except Exception:
pass`. The publisher and subscriber catch narrowly and degrade to a no-op (never raise
into the kernel tick loop or the event bus), mirroring the existing `EventBus` and
`RecoveryEngine._on_verification` isolation pattern. Failures in classification default
to `UNKNOWN`/`LOW` rather than raising.

## Testing Strategy

Hypothesis property tests (≥100 examples) for the pure taxonomy/model (P1, P2). Unit
tests for the publisher no-op and payload shape (P3) and the log subscriber (P5). An
integration test wires a real `CognitiveKernel` + `RecoveryEngine` + publisher to prove
the loop activation end-to-end (P4). An Operator wiring test proves additive safety (P6).
Full regression suite must stay green.

## Acceptance criteria

- The dormant loop is demonstrably activated: attaching a real `RecoveryEngine` + the
  publisher to a real `CognitiveKernel` and publishing a failed verdict yields a
  `recovery.proposed` event (integration test).
- `classify_error_category` is total (property test over arbitrary strings; every
  known category maps to a non-UNKNOWN domain).
- No production default changes when `kernel` is not injected (full suite green).

## Rollback

All new code is additive and inert without a `kernel`. Rollback = do not inject a
kernel into the `Operator` (the pre-M24 state). No default flips.

## Benchmarks / risks

- Benchmark impact: none on the 5-domain scorecard (the benchmark runner constructs the
  Operator without a kernel). Recovery-rate benchmarking is a later milestone (audit
  objective 5) that builds on this producer.
- Risk: event volume. Mitigated — one event per requirement verdict, isolated handlers,
  append-only store already bounded by checkpointing.

## Traceability

- FAS Ch 34 (Recovery), Ch 52 (kernel-driven), Ch 12/28 (evidence/competence).
- v2.1 amendment **A2.14 — Structured Failure & Recovery Activation** (this milestone).
- Audit objectives 1 (structured error model), 2 (observability), 3 (failure
  classification), 4 (recovery framework).
