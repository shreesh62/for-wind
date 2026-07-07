# Requirements Document

M12 — Kernel-Backed Execution & Legacy Retirement

## Introduction

An exhaustive wiring audit established that the M1–M11 kernel substrate is **test-only**: the live
application (`friday/api/server.py`, `main.py`) executes goals entirely through the legacy
`FridayBridge → Operator → GoalExecutor` pipeline, and the kernel's `submit_goal` records a stub that
nothing executes. The technical-debt items TD-2/4/5/6/8 therefore cannot be safely *deleted* — the
kernel cannot yet run a real goal. M12 resolves this **build-then-retire**: it gives the kernel a real
execution surface that **delegates to the existing, proven `Operator`** (zero behavior change), wires
memory at that single seam (TD-6), and routes the live entry point through the kernel **behind an
opt-in flag** so the default behavior is byte-for-byte identical to today (TD-2/TD-8). The confirmed
dead code (`bridge.py::_execute_operator_step` and siblings) is already removed. The binding
constraint is **reversibility**: with the flag off, the system is exactly as it is now, and all 1166
existing tests stay green.

## Glossary

- **Legacy pipeline**: `FridayBridge → Operator → GoalExecutor` — the only working execution engine
  today.
- **Kernel-backed execution**: submitting a goal to the `CognitiveKernel` and having a registered
  runtime execute it via the `Operator`, emitting lifecycle events.
- **GoalExecutionRuntime**: a `RuntimeContract` that subscribes to `goal.created` and delegates
  execution to an injected operator factory.
- **Operator factory**: a callable `(goal_text) -> object with .run(goal) -> OperatorOutcome`, injected
  so the kernel package never imports `friday.operator`.
- **Memory sink**: a duck-typed `record_episode(dict) -> bool` seam, injected so the runtime never
  imports `friday.memory`.
- **Opt-in flag**: `BridgeConfig.use_kernel_execution` (env `FRIDAY_USE_KERNEL_EXECUTION`), default
  false — preserves legacy behavior.
- **Lifecycle events**: `goal.completed` / `goal.failed` published by the runtime.

## Requirements

### Requirement 1: Kernel goal execution via the proven Operator (TD-2/TD-4 foundation)

**User Story:** As the FRIDAY architecture, I want the kernel to actually execute a goal by delegating
to the existing Operator, so that the kernel path is real without re-implementing or risking the
working execution engine.

#### Acceptance Criteria

1. WHEN `GoalExecutionRuntime.execute_goal(goal_id, goal_text)` is called THEN it SHALL build an
   operator via the injected `operator_factory` and invoke its `.run(goal_text)` exactly once.
2. WHEN the operator returns an `OperatorOutcome` THEN the runtime SHALL map `completed`, `summary`,
   and `created_files` faithfully into a `GoalExecutionRecord`.
3. IF the operator factory or `.run` raises THEN `execute_goal` SHALL return a `GoalExecutionRecord`
   with `completed=False` and the error captured, and SHALL NOT propagate the exception.
4. WHEN a goal executes THEN the runtime SHALL emit exactly one lifecycle event — `goal.completed` on
   success or `goal.failed` on failure — via the kernel event bus.

### Requirement 2: Memory wiring at the execution seam (TD-6)

**User Story:** As FRIDAY, I want a completed goal to be recorded as a memory episode on the live path,
so that memory forms from real execution without the Operator/executor importing memory.

#### Acceptance Criteria

1. WHEN a goal completes AND a memory sink is present THEN the runtime SHALL record exactly one episode
   via `memory_sink.record_episode({...})`.
2. IF no memory sink is present THEN execution SHALL complete normally and record nothing.
3. IF the memory sink raises THEN execution SHALL still complete and the failure SHALL be swallowed
   (no propagation).

### Requirement 3: Backward-compatible bridge routing (TD-2/TD-8)

**User Story:** As a maintainer, I want the live entry point to optionally run through the kernel while
defaulting to the exact legacy behavior, so that the change is a pure superset and fully reversible.

#### Acceptance Criteria

1. WHEN `BridgeConfig.use_kernel_execution` is False (default) OR no kernel is wired THEN the
   multi-step path SHALL call the unchanged legacy `_execute_multi_step` and SHALL NOT touch the kernel.
2. WHEN `use_kernel_execution` is True AND a kernel is wired THEN the multi-step path SHALL call
   `_execute_via_kernel`, which submits the goal and returns a well-formed human-readable string.
3. IF `_execute_via_kernel` is called with no kernel present THEN it SHALL fall back to
   `_execute_multi_step` and SHALL NOT raise or return None.
4. WHEN M12 is added THEN Level-1 simple-action behavior (`_execute_simple_action` → `FridayEngine`)
   SHALL be unchanged.

### Requirement 4: Isolation, contract, and regression safety

**User Story:** As a maintainer, I want the new runtime to obey the kernel's isolation contract and the
suite to stay green.

#### Acceptance Criteria

1. WHEN `friday/kernel/execution.py` imports are scanned THEN it SHALL import only `friday.events*`,
   `friday.kernel.contracts*`, and standard-library modules — never `friday.operator`, `friday.memory`,
   `friday.bridge`, or `friday.executor`.
2. WHEN any `GoalExecutionRuntime` event handler runs THEN it SHALL read payload defensively and SHALL
   NOT raise into the kernel tick loop.
3. WHEN the runtime is registered THEN it SHALL implement every `RuntimeContract` member and its
   `checkpoint()`/`restore()` SHALL round-trip.
4. WHEN the full suite runs under `FRIDAY_DRY_RUN=1` THEN all pre-existing tests (≥ 1166) SHALL still
   pass and M12 SHALL add property, unit, isolation, integration, and bridge-compat tests.

### Requirement 5: Conventions

**User Story:** As a maintainer, I want M12 to follow established milestone conventions.

#### Acceptance Criteria

1. WHEN M12 modules are added THEN each SHALL carry a `"""Ch NN — ..."""` module docstring.
2. WHEN the M12 file set is scanned THEN no banned application/site name and no URL scheme literal
   SHALL appear in code (Axiom 15).

## Property-to-Requirement Mapping

| Correctness Property (design.md) | Validates Requirements |
|---|---|
| P1 Kernel execution delegates, never re-implements | 1.1, 1.2 |
| P2 Execution never raises | 1.3, 4.2 |
| P3 Lifecycle events emitted exactly once | 1.4 |
| P4 Memory sink optional and fail-safe | 2.1, 2.2, 2.3 |
| P5 Bridge default preserves legacy behavior | 3.1, 3.4 |
| P6 Bridge kernel path degrades safely | 3.2, 3.3 |
| P7 Runtime isolation (import boundary) | 4.1 |
| P8 RuntimeContract completeness | 4.3, 4.4 |
