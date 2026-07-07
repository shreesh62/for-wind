# Implementation Plan: M4-Gaps — Safety, Resources, Identity & Cognitive State

## Overview

This plan converts the approved M4-gaps design into incremental, code-focused steps. Each subsystem
is independent (safety, resources, identity, cognitive-state), so their pure cores build in parallel;
kernel wiring is layered on after each core. Everything wires/wraps existing code — the kernel event
bus, `ResourceContract`, `Goal` serialization shapes, and `CognitiveKernel.checkpoint/restore` — and
never rewrites them. All modules carry `"""Ch NN — ..."""` docstrings, contain no hardcoded app/site
names or URLs (Axiom 15), communicate only through kernel events (Ch 52), and run under
`FRIDAY_DRY_RUN=1`.

**Language:** Python 3.12. **Test command:** `python -m pytest tests/friday/ -q`.

## Tasks

- [ ] 1. Safety — `friday/safety/`
  - [ ] 1.1 Implement `SafetyPolicy` — `friday/safety/policy.py`
    - `"""Ch 35 — ..."""` docstring; frozen `SafetyPolicy` with `confirm_levels`, `forbidden_levels`,
      `irreversible_confidence_floor=0.85`; `requires_confirmation`, `is_forbidden`, `default()`
    - _Requirements: 1.1, 1.2, 1.3_
  - [ ] 1.2 Implement `PermissionManager` core — `friday/safety/permission.py`
    - `PermissionLevel(IntEnum)` (9 levels), `TrustZone(str,Enum)` (5), `Decision(str,Enum)` (4),
      frozen `PermissionRequest`/`PermissionVerdict`, `PermissionManager.evaluate`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [ ] 1.3 Implement `PermissionManager` kernel wiring (`attach` + emissions)
    - subscribe `action.requested`; publish `permission.granted`/`permission.denied`; defensive, never raises
    - _Requirements: 1.5, 1.6_
  - [ ] 1.4 Implement `SecretVault` — `friday/safety/vault.py`
    - keyring backend guarded by try/except; encrypted-file fallback; in-memory under DRY_RUN;
      `set/get/has/delete/keys`; no value in repr/str/keys
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [ ] 1.5 Create `friday/safety/__init__.py` exporting the public surface
    - _Requirements: 6.2_
  - [ ]* 1.6 Write unit + property tests for safety
    - **Property 1/2/3** (permission gating) — **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    - **Property 4/5** (vault no-leak + round-trip) — **Validates: Requirements 2.1, 2.2, 2.3**

- [ ] 2. Resources — `friday/resources/`
  - [ ] 2.1 Implement `Resource` + `ResourceKind` + `ResourceRegistry` — `types.py`, `registry.py`
    - `"""Ch 45 — ..."""`; `Resource(health())`, register/unregister/get/by_kind
    - _Requirements: 3.1_
  - [ ] 2.2 Implement `ResourceManager` core — `friday/resources/scheduler.py`
    - `"""Ch 46 — ..."""`; frozen `Allocation`; allocate/release/holder_of; exclusive single-holder;
      idempotent same-holder; unhealthy/unknown denied; FIFO wait order + next_holder on release
    - _Requirements: 3.2, 3.3, 3.4, 3.5_
  - [ ] 2.3 Implement `ResourceManager` kernel wiring (`attach` + emissions)
    - subscribe `resource.requested`/`resource.released`; publish `resource.allocated`/`released`/`denied`; never raises
    - _Requirements: 3.6_
  - [ ] 2.4 Create `friday/resources/__init__.py` exporting the public surface
    - _Requirements: 6.2_
  - [ ]* 2.5 Write property tests for resources
    - **Property 6** (exclusive never double-allocated) — **Validates: Requirements 3.2, 3.3**
    - **Property 7** (release frees exactly the holder) — **Validates: Requirements 3.4**

- [ ] 3. Identity — `friday/identity/`
  - [ ] 3.1 Implement `CognitiveIdentity` + kernel wiring — `friday/identity/identity.py`
    - `"""Ch 51 — ..."""`; identity_id/preferences/goal_states/last_checkpoint; set_preference,
      record_goal_state, checkpoint/restore (defensive, invents nothing); attach subscribes
      `goal.state_changed`/`kernel.checkpoint`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - [ ] 3.2 Create `friday/identity/__init__.py` exporting the public surface
    - _Requirements: 6.2_
  - [ ]* 3.3 Write property test for identity
    - **Property 8** (identity survives restart) — **Validates: Requirements 4.5, 4.6**

- [ ] 4. Cognitive State — `friday/cognition/state.py`
  - [ ] 4.1 Implement `CognitiveStateManager` + kernel wiring
    - `"""Ch 67 — ..."""`; `CognitiveMode`/`ThinkingDepth` enums; mutable `CognitiveState`;
      snapshot/enter_mode/set_focus/set_interruptible/set_thinking_depth/consume_budget (clamped);
      attach subscribes `goal.state_changed`/`action.executed`; never raises
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - [ ]* 4.2 Write property + unit tests for cognitive state
    - **Property 9** (reasoning budget in [0,1]) — **Validates: Requirements 5.4**

- [ ] 5. Checkpoint — cores complete
  - Ensure all tests pass.

- [ ] 6. Isolation, integration, determinism, and the M4 Gate
  - [ ]* 6.1 Write AST isolation tests — `tests/friday/test_m4_isolation.py`
    - safety imports only events + stdlib (+ guarded keyring); resources only events +
      kernel.contracts + stdlib; identity + cognitive-state only events + stdlib; docstrings; no
      app/site names or URLs
    - _Requirements: 6.1, 6.2, 6.3, 7.3_
  - [ ]* 6.2 Write kernel-event integration test — `tests/friday/test_m4_integration.py`
    - real kernel; attach all four; drive `action.requested`/`resource.requested`/
      `goal.state_changed`/`kernel.checkpoint`; assert `permission.*`/`resource.*` land + identity +
      cognitive-state update
    - _Requirements: 6.1, 7.2_
  - [ ]* 6.3 Write determinism property test — `tests/friday/test_m4_properties.py`
    - **Property 10** (determinism) — **Validates: Requirements 6.4, 6.5**
  - [ ]* 6.4 Write the M4 Gate — `tests/friday/test_m4_gate.py`
    - risky action gated; exclusive resource contended → exactly one holder; identity survives
      checkpoint→restore across fresh kernel; deterministic on replay
    - _Requirements: 6.5, 7.2_

- [ ] 7. Final regression checkpoint
  - Run `python -m pytest tests/friday/ -q`; ensure ≥ 995 existing tests plus all new M4 tests pass.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1", "4.1"] },
    { "id": 1, "tasks": ["1.2", "2.2"] },
    { "id": 2, "tasks": ["1.3", "1.4", "2.3"] },
    { "id": 3, "tasks": ["1.5", "2.4", "3.2"] },
    { "id": 4, "tasks": ["1.6", "2.5", "3.3", "4.2"] },
    { "id": 5, "tasks": ["6.1", "6.2", "6.3"] },
    { "id": 6, "tasks": ["6.4"] }
  ]
}
```

## Notes

- Tasks marked `*` are optional test sub-tasks; core implementation tasks are never optional.
- Existing code is wrapped/extended, never rewritten: the kernel event bus, `ResourceContract`,
  `Goal` serialization shapes, and kernel checkpoint/restore.
- Every subsystem communicates only through kernel events; the four subsystems never import one
  another. All tests run under `FRIDAY_DRY_RUN=1`.
