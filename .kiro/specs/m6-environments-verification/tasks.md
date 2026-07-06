# Implementation Plan: M6 — Environment Contracts, Unified Verification, Operation

## Overview

Implements the M6 milestone: a uniform `EnvironmentContract` ABC, the `BrowserEnvironment` adapter wrapping the existing `BrowserController`, a `StubEnvironment` for gate tests, the `UnifiedVerificationEngine` merging artifact-based and diff-based verification, the `EvidenceRepository` with signed append-only storage, and a desktop placeholder. All work is additive — existing 802 tests must remain green throughout.

## Tasks

- [x] 1. EnvironmentContract ABC and core types
  - [x] 1.1 Create `friday/environments/__init__.py` and `friday/environments/contract.py` with the full EnvironmentContract ABC, Action dataclass, and ObjectQuery dataclass
    - Define `Action(capability, target, params)` frozen dataclass
    - Define `ObjectQuery(object_type, text_contains, editable_only, limit)` frozen dataclass
    - Define `EnvironmentContract` subclassing the existing kernel stub `friday/kernel/contracts/environment.py`
    - Implement all abstract methods: `name`, `observe`, `interact`, `verify`, `query_objects`, `query_capabilities`, `pause`, `resume`, `shutdown`, `health`
    - Docstring must reference FAS Ch 23
    - _Requirements: 1.1, 1.5, 2.2, 8.3_

  - [x] 1.2 Create `friday/environments/runtime.py` with the `EnvironmentRuntime` mix-in bridging `RuntimeContract` and `EnvironmentContract`
    - Implement `initialize(kernel)`, `tick(logical_time)`, `observe() -> List[Dict]`, `receive(event)`, `publish(event)`, `checkpoint()`, `restore(state)`
    - `tick()` does passive observe and publishes `observation.received` events
    - `receive()` handles `capability.requested` events by routing to `interact()`
    - `checkpoint()` returns only JSON-serializable primitives (no Playwright handles)
    - Docstring must reference FAS Ch 52
    - _Requirements: 6.3, 7.5, 8.2_

  - [x]* 1.3 Write unit tests for EnvironmentContract and EnvironmentRuntime
    - Test that `Action` and `ObjectQuery` are frozen dataclasses with correct fields
    - Test that `EnvironmentContract` subclasses the kernel stub
    - Test that `EnvironmentRuntime` abstract methods have correct signatures
    - _Requirements: 1.1, 8.3_

- [x] 2. StubEnvironment
  - [x] 2.1 Create `friday/environments/stub.py` implementing `StubEnvironment`
    - Implement `EnvironmentRuntime` + `EnvironmentContract`
    - Accept `scripted: Optional[List[Observation]]` and `capabilities: Optional[List[str]]` in constructor
    - `name` returns `"stub.testenv"`
    - `observe()` returns the scripted observations list
    - `interact(action)` returns `ActionResult.success(...)` without I/O
    - `verify(expected)` returns a deterministic `VerificationResult`
    - `query_objects(query)` filters scripted observations by query parameters
    - `query_capabilities()` returns the configured capability list
    - `health()` returns `{"status": "ok", ...}`
    - `pause()/resume()/shutdown()` are no-ops
    - Docstring must reference FAS Ch 23
    - _Requirements: 6.4, 6.5, 1.2, 1.3_

  - [x]* 2.2 Write unit tests for StubEnvironment
    - Test all EnvironmentContract methods return correct types
    - Test interact never raises for any valid capability
    - Test observe returns scripted Observations with correct fields
    - Test query_objects filters by object_type
    - _Requirements: 6.4, 6.5_

- [x] 3. Checkpoint — Ensure all tests pass
  - Ensure all tests pass (`python -m pytest tests/friday/ -q`), ask the user if questions arise.

- [x] 4. BrowserEnvironment adapter
  - [x] 4.1 Create `friday/environments/browser/__init__.py` and `friday/environments/browser/adapter.py` implementing `BrowserEnvironment`
    - Implement `EnvironmentRuntime` + `EnvironmentContract`
    - Accept a `BrowserController` instance in constructor (dependency injection, not import-time coupling)
    - `name` returns `"browser.chrome.dedicated"` (no site names)
    - Build `_routes` dict mapping capability strings to handler methods
    - `observe()` calls `browser_controller.observe_interactive(limit)` and maps dicts to `Observation` objects with `environment="browser"`, `object_type=role`
    - `interact(action)` dispatches via `_routes` dict; returns `ActionResult.blocked(...)` if controller unavailable
    - `query_objects(query)` filters latest observation snapshot into `WorldObject` instances
    - `query_capabilities()` returns `["observe", "read", "navigate", "click", "type", "scroll", "press", "upload", "download"]`
    - `health()` returns `{status, available, connection_mode, is_real_chrome, last_error}`
    - `pause()/resume()` toggle a flag gating `tick()` passive observation
    - `shutdown()` calls `browser_controller.stop()`
    - Each controller dict result is translated to `ActionResult` with `ActionEvidence` populated from url_changed/state_changed signals
    - No Playwright types escape the adapter boundary
    - Docstring must reference FAS Ch 29
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 2.3, 2.4, 1.2_

  - [x]* 4.2 Write unit tests for BrowserEnvironment with mocked BrowserController
    - Mock `BrowserController` with `available=True` and scripted method returns
    - Test each capability routes to the correct controller method
    - Test observe maps dicts to Observation objects correctly
    - Test interact returns ActionResult.blocked when controller unavailable
    - Test query_objects filters by object_type
    - Test health() returns correct shape
    - Test no Playwright types in any return value
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.6_

- [x] 5. EvidenceRepository
  - [x] 5.1 Create `friday/verification/evidence_repo.py` implementing `EvidenceRepository`
    - Define `EvidenceRecord` frozen dataclass: `record_id`, `goal_id`, `requirement`, `artifact`, `verdict_satisfied`, `created_at`, `signature`
    - Implement `add_artifact(goal_id, artifact, requirement)` → appends and signs record
    - Implement `add_verdict(goal_id, verdict)` → appends and signs record
    - Implement `query(goal_id, kind)` → returns matching records via index
    - Implement `for_goal(goal_id)` → reconstructs `ExecutionEvidence` from valid artifacts
    - Implement `verify_integrity()` → validates all HMAC signatures
    - Use in-memory dict indices: `by_goal[goal_id] -> [record_id]`, `by_kind[EvidenceKind] -> [record_id]`
    - Signing key loaded from parameter (not hardcoded)
    - Append-only: no update or delete API
    - Docstring must reference FAS Ch 33
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x]* 5.2 Write unit tests for EvidenceRepository
    - Test add→query round-trips
    - Test signature validates on read
    - Test tampering is detected by verify_integrity()
    - Test query filters by goal_id and kind
    - Test for_goal reconstructs ExecutionEvidence correctly
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 6. UnifiedVerificationEngine
  - [x] 6.1 Create `friday/verification/engine.py` implementing `UnifiedVerificationEngine`
    - Define `GoalVerificationResult` dataclass: `goal_id`, `satisfied`, `requirement_verdicts`, `reason`
    - Accept optional `EvidenceRepository`, `ActionVerifier`, `EvidenceVerifier` in constructor
    - `verify_requirement(requirement, evidence)` delegates to `EvidenceVerifier.verify_one()` and wraps into `VerificationResult`
    - `verify_goal(goal, evidence)` evaluates every requirement via `EvidenceVerifier.verify_one()`; satisfied iff ALL verdicts satisfied AND requirements list is non-empty
    - `verify_action(action_type, predicted, observed, evidence)` uses `ActionVerifier.verify()` for diff verdict; artifact presence for corroboration; never downgrades artifact-backed truth
    - Persist verdicts and artifacts into `EvidenceRepository` when repo is provided
    - Docstring must reference FAS Ch 32
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 5.6_

  - [x]* 6.2 Write unit tests for UnifiedVerificationEngine
    - Test verify_requirement returns same satisfied status as EvidenceVerifier.verify_one
    - Test verify_goal with all-satisfied requirements → satisfied
    - Test verify_goal with one unmet requirement → not satisfied
    - Test verify_goal with zero requirements → not satisfied
    - Test verify_action uses ActionVerifier verdict
    - Test GATHER requirement with only GENERATED_CONTENT → UNMET
    - Test DELIVER requirement with only GENERATED_CONTENT → UNMET
    - Test engine persists verdicts to repository when provided
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.6_

- [x] 7. Checkpoint — Ensure all tests pass
  - Ensure all tests pass (`python -m pytest tests/friday/ -q`), ask the user if questions arise.

- [x] 8. Desktop environment stub
  - [x] 8.1 Create `friday/environments/desktop/__init__.py` with `DesktopEnvironment` placeholder
    - Implement `EnvironmentContract` + `EnvironmentRuntime`
    - `name` returns `"desktop.windows.placeholder"`
    - All interaction methods raise `NotImplementedError` or return empty/minimal responses
    - `observe()` returns `[]`; `health()` returns `{"status": "degraded", "reason": "not implemented"}`
    - Docstring must reference FAS Ch 23 with note "fleshed out in M7"
    - _Requirements: 8.2_

- [x] 9. Import-boundary and site-agnosticism tests
  - [x] 9.1 Create `tests/friday/test_m6_isolation.py` with import-boundary tests
    - Static test: parse AST of all files under `friday/kernel/` and `friday/deliberation/` and assert they do NOT import `playwright`, `friday.actions.browser_controller`, or `friday.environments.browser`
    - Static test: scan all files under `friday/environments/` and assert no hardcoded URL scheme literals (`http://`, `https://`, `file://`) and no known-application name constants
    - _Requirements: 6.2, 2.1, 2.3, 2.4_

  - [x] 9.2 Create `tests/friday/test_m6_gate.py` with the M6 Gate test (backend independence)
    - Register `StubEnvironment` with Kernel, submit goal, produce `DecisionRecord` via Deliberator
    - Register `BrowserEnvironment` (mocked controller) with Kernel, submit same goal, produce `DecisionRecord`
    - Assert both `DecisionRecord`s have identical structure (same fields, same considered-tuple shape)
    - Proves Kernel/Deliberation are backend-independent
    - _Requirements: 6.1, 6.2_

- [x] 10. Property-based tests
  - [x]* 10.1 Write property test for contract totality (Property 1)
    - **Property 1: Contract totality**
    - For every Action with capability in query_capabilities(), StubEnvironment.interact() returns ActionResult and never raises
    - Use Hypothesis to generate random Action objects with valid capabilities
    - **Validates: Requirements 1.2, 6.5**

  - [x]* 10.2 Write property test for observation uniformity (Property 2)
    - **Property 2: Observation uniformity**
    - For every environment, every element of observe() is an Observation with non-empty environment and object_type
    - Use Hypothesis to generate random scripted observations for StubEnvironment
    - **Validates: Requirements 1.3**

  - [x]* 10.3 Write property test for Evidence Law preservation (Property 4)
    - **Property 4: Evidence Law is never weakened**
    - For every requirement description and evidence bundle, engine.verify_requirement().is_satisfied == EvidenceVerifier().verify_one().satisfied
    - Use Hypothesis to generate random requirement strings and ExecutionEvidence bundles
    - **Validates: Requirements 3.2, 4.3**

  - [x]* 10.4 Write property test for no false completion (Property 5)
    - **Property 5: No false completion for GATHER/DELIVER**
    - For every evidence bundle containing only GENERATED_CONTENT artifacts, any GATHER or DELIVER requirement is UNMET
    - Use Hypothesis to generate evidence bundles of only generated content
    - **Validates: Requirements 4.1, 4.2**

  - [x]* 10.5 Write property test for goal completeness (Property 6)
    - **Property 6: Goal completeness**
    - verify_goal satisfied iff all requirements satisfied, and False when goal has zero requirements
    - Use Hypothesis to generate goals with varying requirement lists and evidence
    - **Validates: Requirements 3.3, 3.4**

  - [x]* 10.6 Write property test for evidence integrity (Property 7)
    - **Property 7: Evidence integrity**
    - For every repository record, the stored signature validates; mutating any field invalidates it
    - Use Hypothesis to generate random EvidenceArtifacts and mutations
    - **Validates: Requirements 5.1, 5.2**

  - [x]* 10.7 Write property test for checkpoint purity (Property 9)
    - **Property 9: Checkpoint purity**
    - For every EnvironmentRuntime, checkpoint() is JSON-serializable
    - Use json.dumps on checkpoint output with various runtime states
    - **Validates: Requirements 6.3**

  - [x]* 10.8 Write property test for query soundness (Property 10)
    - **Property 10: Query soundness**
    - For every ObjectQuery with object_type=t, every WorldObject returned has object_type==t
    - Use Hypothesis to generate queries and observation sets
    - **Validates: Requirements 1.4**

- [x] 11. Final checkpoint — Regression and integration
  - [x] 11.1 Run full regression suite and verify all 802+ existing tests pass
    - Execute `python -m pytest tests/friday/ -q`
    - Confirm zero failures introduced by M6
    - Fix any regressions before declaring M6 complete
    - _Requirements: 4.4, 8.1, 8.4_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The BrowserController (710 lines) is NEVER modified — only wrapped
- The EvidenceVerifier (crown jewel) is NEVER modified — only composed
- All tests run under `FRIDAY_DRY_RUN=1` — no real browser or I/O
- hypothesis library is used for all property-based tests

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["2.2", "4.1", "5.1"] },
    { "id": 4, "tasks": ["4.2", "5.2", "6.1"] },
    { "id": 5, "tasks": ["6.2", "8.1"] },
    { "id": 6, "tasks": ["9.1", "9.2"] },
    { "id": 7, "tasks": ["10.1", "10.2", "10.3", "10.4", "10.5", "10.6", "10.7", "10.8"] },
    { "id": 8, "tasks": ["11.1"] }
  ]
}
```
