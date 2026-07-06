# Implementation Plan: M8 — Reflection, Memory Wiring, Competence & Recovery

## Overview

This plan converts the M8 design into a series of incremental, code-focused steps for a
code-generation LLM. M8 wires four kernel-event-driven subsystems onto the existing M1–M7 substrate
**without rewriting** the 7 `friday/memory/` modules, the `RepairDiagnoser`
(`friday/planner/repair.py`), or the `CompetenceRecord` (`friday/kernel/contracts/capability.py`) —
each is wrapped, extended, or wired.

Ordering is dependency-driven and validates functionality early through code:

1. **Reflection core** (`friday/cognition/reflection.py`) — pure `reflect()` + `ReflectionRecord` +
   `FiveQuestions` + `ConfidenceCalibrator`, then kernel event handlers/`attach`. Its
   `memory.candidate` output is the contract Memory consumes.
2. **Memory Runtime** (`friday/memory/runtime.py`) — pure `decide()` core, then `RuntimeContract` +
   `subscribe`, wrapping the existing `FridayMemory`.
3. **Competence Model** (`friday/competence/model.py`) — `record_outcome`/`confidence`/`decay`/
   `is_permitted`/graph, then `attach`; independent of Reflection/Memory.
4. **Recovery Engine** (`friday/recovery/engine.py`) — pure `recover()` core + `_classify`
   (`RepairCause → FailureClass`), then `attach`; independent.
5. **Checkpoints** after major groups (keep ≥ 871 tests green).
6. **Tests** — isolation/import-boundary, 8 property tests, kernel-event integration, and the M8 gate.
7. **Final regression checkpoint.**

Every pure decision core (`reflect` / `decide` / `recover` / `confidence`) is separated from kernel
wiring so it is directly unit- and property-testable under `FRIDAY_DRY_RUN=1`. All new modules carry
a `"""Ch NN — ..."""` docstring and communicate only through kernel events (Ch 52).

**Language:** Python 3.12 (the project language, used throughout the design). **Test command:**
`python -m pytest tests/friday/ -q`.

## Tasks

- [ ] 1. Reflection core (pure) — `friday/cognition/reflection.py`
  - [ ] 1.1 Create the `friday/cognition/` package and Reflection data models + pure core
    - Create `friday/cognition/__init__.py` and `friday/cognition/reflection.py` with a
      `"""Ch 13 — ..."""` module docstring
    - Define `ReflectionScale(str, Enum)` with `MICRO`/`TASK`/`GOAL`/`SESSION` (all four scales)
    - Define frozen `FiveQuestions` (5 fields) and frozen `ReflectionRecord`
      (`goal_id`, `scale`, `capability`, `environment`, `predicted_beliefs`, `observed_beliefs`,
      `predicted_confidence`, `prediction_error`, `questions`, `verified`, `calibration_delta`, `id`)
      with `__post_init__` clamping `predicted_confidence` and `prediction_error` to `[0, 1]`
    - Implement `ReflectionRecord.to_candidate_payload()` copying `verified` verbatim and emitting
      `kind`/`content`/`context_hash`/`competence_delta`/`source_goal_id`/`capability`/`environment`
    - Implement the pure `ReflectionEngine.reflect(...)` computing `prediction_error` (0 on exact
      match of expected vs observed beliefs; 1 when a non-empty prediction has no overlap) and
      answering the Five_Questions; deterministic and side-effect free (no I/O, no memory writes)
    - Import `PredictedOutcome` from `friday.deliberation.candidate`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 7.3_

  - [ ]* 1.2 Write unit tests for `reflect()` and `ReflectionRecord`
    - Table-test `prediction_error` for exact-match (0), partial-overlap (0..1), and disjoint (1)
    - Assert `ReflectionRecord` immutability and that `to_candidate_payload()["verified"]` mirrors input
    - Assert all four `ReflectionScale` values are reflectable
    - Set `os.environ.setdefault("FRIDAY_DRY_RUN", "1")` before importing any `friday` module
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 7.2_

  - [ ] 1.3 Implement `ConfidenceCalibrator`
    - Implement `observe(predicted_confidence, was_accurate)` and the `calibration_error` property as
      the mean absolute difference between predicted confidence and observed accuracy in `[0, 1]`
    - Wire `calibration_delta` into `reflect()`/`ReflectionRecord`
    - _Requirements: 1.9_

  - [ ]* 1.4 Write unit tests for `ConfidenceCalibrator`
    - Assert `calibration_error` stays in `[0, 1]` and equals mean absolute error over samples
    - _Requirements: 1.9, 7.2_

  - [ ] 1.5 Implement Reflection kernel wiring (`attach` + handlers + candidate emission)
    - Implement `attach(kernel)` subscribing to `action.executed`, `verification.completed`, and
      `goal.state_changed` via `kernel.subscribe`
    - Implement `_on_verification`/`_on_action`/`_on_goal_state` to call `reflect()` then
      `_emit_candidate` publishing a `memory.candidate` event (the ONLY memory touchpoint), plus a
      `reflection.completed` audit event, using `make_event` from `friday.events.event`
    - Set `verified=True` on the candidate only when the triggering experience was verification-backed,
      else `False`
    - Read event fields defensively (`payload.get(...)`); if `goal_id`, prediction, or observed beliefs
      are absent, skip reflection and never raise into the kernel tick loop
    - Do NOT import or call `FridayMemory`/any memory store (enforces Property 1 structurally)
    - _Requirements: 1.1, 1.7, 1.8, 1.10, 5.1, 5.2_

  - [ ]* 1.6 Write property test: Reflection never writes long-term memory directly
    - **Property 1: Reflection never writes long-term memory directly**
    - **Validates: Requirements 1.1**

  - [ ]* 1.7 Write property test: Prediction error is a bounded score
    - **Property 8: Prediction error is a bounded, symmetric-free score**
    - **Validates: Requirements 1.2, 1.3, 1.4**

- [ ] 2. Checkpoint — Reflection complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Memory Runtime — `friday/memory/runtime.py` (wraps existing FridayMemory)
  - [ ] 3.1 Implement the pure `decide()` decision core + `MemoryDecision`/`CandidateVerdict`
    - Create `friday/memory/runtime.py` with a `"""Ch 14/52 — ..."""` module docstring
    - Define `MemoryDecision(str, Enum)` (`ACCEPT`/`REJECT`/`MERGE`/`FORGET`) and frozen
      `CandidateVerdict` (`decision`, `reason`, `tier`, `entry_ref`)
    - Implement pure `decide(candidate, *, contradicting_observation=False)`: REJECT when
      `candidate["verified"]` is not `True` (reason "unverified experience"); REJECT when
      `contradicting_observation` is `True` regardless of `verified` (reason "reality outranks memory");
      otherwise MERGE if a similar entry exists else ACCEPT
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ]* 3.2 Write property test: candidates integrated only from verified experience
    - **Property 2: Memory candidates are integrated only from verified experience**
    - **Validates: Requirements 2.1**

  - [ ]* 3.3 Write property test: Memory never overrides a contradicting observation
    - **Property 7: Memory never overrides a contradicting observation**
    - **Validates: Requirements 2.2**

  - [ ] 3.4 Implement `MemoryRuntime` RuntimeContract + kernel wiring wrapping FridayMemory
    - Implement all `RuntimeContract` members (`name`, `initialize`, `tick`, `observe`, `receive`,
      `publish`, `checkpoint`, `restore`, `shutdown`, `health`) so the kernel can `register_runtime` it
    - `initialize(kernel)` subscribes to `memory.candidate`; `_on_candidate` calls `decide()`, delegates
      storage to the wrapped `FridayMemory` (`record_turn`/`record_pattern`/`remember_fact`) via
      `_integrate` routed by `kind`, and publishes `memory.integrated` (accept/merge) or
      `memory.rejected` (reject) via `make_event`
    - Lazily construct `FridayMemory`; on construction/IO failure under DRY_RUN degrade to in-memory
      no-op storage, report `degraded` status via `health()`, and keep publishing decisions
    - Implement periodic forgetting/decay in `tick()` on `decay_interval_ticks` without modifying World
      Model observations; `checkpoint()` returns JSON-serializable stats only
    - Do NOT reimplement the memory tiers and do NOT rewrite the 7 memory modules
    - _Requirements: 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 5.1, 5.5, 7.3_

  - [ ]* 3.5 Write unit tests for MemoryRuntime contract and degraded mode
    - Table-test `decide()` across the verified/unverified × contradiction matrix
    - Assert all `RuntimeContract` methods are present and `checkpoint()`/`restore()` round-trips
    - Assert degraded-mode `health()["status"] == "degraded"` still publishes decisions
    - _Requirements: 2.4, 2.6, 2.7, 2.9, 7.2_

- [ ] 4. Competence Model — `friday/competence/model.py` (builds on existing CompetenceRecord)
  - [ ] 4.1 Create the `friday/competence/` package and core model (record/confidence/graph)
    - Create `friday/competence/__init__.py` and `friday/competence/model.py` with a
      `"""Ch 28 — ..."""` module docstring
    - Define `CompetenceKey = Tuple[str, str]` and `CompetenceNode` (`key`, `record: CompetenceRecord`,
      `last_evidence_tick`, `confidence` delegating to the record)
    - Implement `CompetenceModel.record_outcome(key, *, success, tick)` folding a verified outcome into
      the `(capability, environment)` `CompetenceRecord` (increment attempts; successes iff success)
    - Implement `confidence(key)` returning the Laplace-smoothed value in `[0, 1]` (neutral prior if
      unseen) and `graph()` returning a read-only view of `CompetenceKey` nodes
    - Import and reuse the existing `CompetenceRecord` from `friday.kernel.contracts.capability`; do NOT
      import `friday.memory.controller`
    - _Requirements: 3.1, 3.4, 3.8, 5.3, 5.5, 7.3_

  - [ ]* 4.2 Write property test: competence is in [0, 1] and evidence-derived
    - **Property 3: Competence is in [0, 1] and evidence-derived**
    - **Validates: Requirements 3.1, 3.4**

  - [ ] 4.3 Implement decay and risk gating
    - Implement `decay(now_tick)` reducing effective confidence toward the neutral prior — monotonic
      non-increasing, never increasing confidence and never adding successes
    - Define `RISK_CONFIDENCE_GATE` for `observe`/`reversible`/`modify`/`irreversible` such that gates
      are non-decreasing in risk, and implement `is_permitted(key, risk)` as
      `confidence(key) >= RISK_CONFIDENCE_GATE[risk]`
    - _Requirements: 3.2, 3.5, 3.6_

  - [ ]* 4.4 Write property test: competence decay is monotonic non-increasing without new evidence
    - **Property 4: Competence decay is monotonic non-increasing without new evidence**
    - **Validates: Requirements 3.2**

  - [ ] 4.5 Implement Competence kernel wiring (`attach` + verification handler)
    - Implement `attach(kernel)` subscribing to `verification.completed`
    - Implement `_on_verification` folding the verified outcome into the `(capability, environment)`
      key via `record_outcome` and publishing `competence.updated` via `make_event`; read fields
      defensively and never raise into the tick loop
    - _Requirements: 3.3, 3.7, 5.1_

  - [ ]* 4.6 Write unit tests for competence folding and gating boundaries
    - Fold known outcome sequences and assert `confidence` equals the Laplace formula
    - Assert `is_permitted` at each risk threshold boundary
    - _Requirements: 3.1, 3.5, 3.6, 7.2_

- [ ] 5. Checkpoint — Memory + Competence complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Recovery Engine — `friday/recovery/engine.py` (wraps existing RepairDiagnoser)
  - [ ] 6.1 Create the `friday/recovery/` package and taxonomy + data models
    - Create `friday/recovery/__init__.py` and `friday/recovery/engine.py` with a
      `"""Ch 34 — ..."""` module docstring
    - Define `FailureClass(str, Enum)` (Ch 34.3 taxonomy), `RecoveryLevel(IntEnum)` (Ch 34.5 ladder),
      `RollbackKind(str, Enum)` (Ch 34.9), frozen `RecoveryAlternative`, and frozen `RecoveryPlan`
      (`goal_id`, `failure_class`, `level`, `rollback`, `alternatives`, `chosen`, `reversible`, `note`)
      with `to_payload()`
    - Import `RepairCause`/`RepairDiagnoser`/`RepairDiagnosis` from `friday.planner.repair`; do NOT
      import `friday.memory.controller`
    - _Requirements: 4.5, 5.3, 5.5, 7.3_

  - [ ] 6.2 Implement the pure `recover()` core + `_classify` mapping
    - Implement `_classify(diagnosis)` mapping each `RepairCause` into a `FailureClass` (wrap, don't
      rewrite the diagnoser); delegate diagnosis to `RepairDiagnoser.diagnose`
    - Define `IRREVERSIBLE_CONFIDENCE_FLOOR`/`REVERSIBLE_CONFIDENCE_FLOOR` and `_required_confidence`
      such that irreversible ≥ reversible
    - Implement pure `recover(*, goal_id, requirement, evidence, reversible, blocked, competence)`:
      preserve `goal_id`; generate `RecoveryAlternative`s ordered by estimated utility desc, each with a
      `RecoveryLevel` and `RollbackKind`; for irreversible failures with `competence <
      IRREVERSIBLE_CONFIDENCE_FLOOR`, set `chosen = None` and escalate `level` to `HUMAN` or higher
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 6.3 Write property test: recovery preserves the goal id
    - **Property 5: Recovery preserves the goal id**
    - **Validates: Requirements 4.1**

  - [ ]* 6.4 Write property test: irreversible-action confidence gate is monotonic
    - **Property 6: Irreversible-action confidence gate is monotonic**
    - **Validates: Requirements 3.6, 4.2, 4.3**

  - [ ] 6.5 Implement Recovery kernel wiring (`attach` + failure handler)
    - Implement `attach(kernel)` subscribing to `verification.completed`
    - Implement `_on_verification` reacting to failure events, running `recover()`, and publishing a
      `recovery.proposed` event (carrying the same `goal_id`) via `make_event` for the Deliberator to
      re-enter; read fields defensively and never raise into the tick loop
    - _Requirements: 4.1, 4.6, 5.1_

  - [ ]* 6.6 Write unit tests for RepairCause→FailureClass mapping and escalation
    - Map each `RepairCause` to its `FailureClass`; assert goal-id preservation
    - Assert the irreversible/insufficient-competence escalation branch (`chosen is None`, `level ≥ HUMAN`)
    - _Requirements: 4.2, 4.4, 4.5, 7.2_

- [ ] 7. Checkpoint — All four subsystems complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Isolation and import-boundary tests
  - [ ]* 8.1 Write AST-based import-boundary/isolation tests
    - Create `tests/friday/test_m8_isolation.py` (extending the M6/M7 AST pattern)
    - Assert `friday/cognition/reflection.py` imports none of `friday.memory.*` storage,
      `friday.competence.*`, or `friday.recovery.*`, and uses no `FridayMemory`/`MemoryStore` symbol
    - Assert `friday/competence/` and `friday/recovery/` do not import `friday.memory.controller`
    - Assert no hardcoded application names, site names, or URLs in the M8 file set
    - Assert each new M8 module carries a `"""Ch NN — ..."""` docstring
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.3_

- [ ] 9. Kernel-event integration test (closed-loop causal order)
  - [ ]* 9.1 Write kernel-event integration test
    - Create `tests/friday/test_m8_integration.py`: build a real `CognitiveKernel`,
      `register_runtime` the `MemoryRuntime`, and `attach` Reflection/Competence/Recovery
    - Publish an `action.executed` + `verification.completed` pair through `kernel.publish_event`; assert
      the event log contains, in causal order, `memory.candidate → memory.integrated` and that
      `competence.updated` follows `verification.completed`
    - Assert no subsystem is called directly — everything flows through `subscribe`/`publish_event`
    - Run under `FRIDAY_DRY_RUN=1`
    - _Requirements: 5.1, 6.2, 7.2_

- [ ] 10. The M8 Gate (end-to-end acceptance oracle)
  - [ ]* 10.1 Write the M8 Gate test
    - Create `tests/friday/test_m8_gate.py` wiring a real kernel with all four subsystems
    - Publish a prediction-mismatch `action.executed`/`verification.completed` (observed beliefs differ,
      `satisfied` false); assert Reflection computes `prediction_error > 0` and emits a verified
      `memory.candidate`, Memory publishes `memory.integrated`, and `competence.updated` is emitted
    - Assert the kernel event log contains, in causal order, `action.executed →
      verification.completed → memory.candidate → memory.integrated` and `competence.updated` following
      `verification.completed`
    - Publish a second, successful `action.executed`/`verification.completed` for the same
      `(capability, environment)`; assert `CompetenceModel.confidence` strictly increased and the
      wrapped `FridayMemory.get_context(...)` returns a non-empty learned context where it was empty
    - Assert re-running the gate with identical inputs produces an identical ordered sequence of M8
      event types (deterministic under DRY_RUN)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.2_

- [ ] 11. Final regression checkpoint
  - Run `python -m pytest tests/friday/ -q`; ensure ≥ 871 existing tests plus all new M8 tests pass.
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core
  implementation tasks are never optional.
- Pure decision cores (`reflect` / `decide` / `recover` / `confidence`) are implemented and tested
  before kernel wiring so they are directly unit- and property-testable.
- Existing modules are wrapped/extended, never rewritten: the 7 `friday/memory/` modules
  (`FridayMemory`), `RepairDiagnoser` (`friday/planner/repair.py`), and `CompetenceRecord`
  (`friday/kernel/contracts/capability.py`).
- All eight design Correctness Properties (1–8) are realized as Hypothesis property tests, each
  annotated with its property number and validated requirements.
- Every task references specific requirement acceptance criteria for traceability, and all tests run
  under `FRIDAY_DRY_RUN=1`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1", "4.1", "6.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "3.2", "3.3", "3.4", "4.2", "4.3", "6.2"] },
    { "id": 2, "tasks": ["1.4", "1.5", "3.5", "4.4", "4.5", "6.3", "6.4", "6.5"] },
    { "id": 3, "tasks": ["1.6", "1.7", "4.6", "6.6", "8.1"] },
    { "id": 4, "tasks": ["9.1"] },
    { "id": 5, "tasks": ["10.1"] }
  ]
}
```
