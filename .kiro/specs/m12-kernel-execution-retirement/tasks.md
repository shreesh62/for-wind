# Implementation Plan: M12 — Kernel-Backed Execution & Legacy Retirement

## Overview

Build-then-retire, maximum care. M12 gives the kernel a real execution surface by **delegating to the
existing, proven `Operator`** (zero behavior change), wires memory at that seam, and routes the live
entry point through the kernel behind an **opt-in flag** whose default reproduces today's behavior
byte-for-byte. Nothing is deleted except the already-removed dead code. Every step is additive and
reversible; the 1166 existing tests must stay green at every checkpoint.

Ordering is dependency-driven:

1. **Data model + runtime core** (`friday/kernel/execution.py`) — `GoalExecutionRecord` +
   `GoalExecutionRuntime` delegating to an injected operator factory. Directly unit/property testable
   with a stub factory (no real Operator needed).
2. **Memory sink** (`friday/kernel/memory_sink.py`) — optional, fail-safe episode recorder.
3. **Bridge routing** (`friday/bridge.py`, additive) — opt-in `_execute_via_kernel` + `kernel` param +
   `use_kernel_execution` flag; legacy path unchanged and default.
4. **Server wiring** (`friday/api/server.py`, additive) — construct kernel, register runtime, inject.
5. **Tests** — unit, 8 properties, isolation, integration, bridge backward-compat.
6. **Final regression checkpoint** (keep ≥ 1166 green).

Every core method (`execute_goal`, `MemorySink.record_episode`) is separated from kernel wiring so it
is directly testable under `FRIDAY_DRY_RUN=1`. All new modules carry `"""Ch NN — ..."""` docstrings,
contain no hardcoded app/site names or URLs (Axiom 15). `execution.py` imports ONLY `friday.events`,
`friday.kernel.contracts`, and stdlib — the operator arrives as a factory, memory as a sink.

**Language:** Python 3.12. **Test command:** `python -m pytest tests/friday/ -q`.

## Tasks

- [ ] 1. Kernel execution runtime — `friday/kernel/execution.py`
  - [ ] 1.1 Implement GoalExecutionRecord and GoalExecutionRuntime core
    - Create `friday/kernel/execution.py` with a `"""Ch 17/18/20 — ..."""` module docstring
    - Define frozen `GoalExecutionRecord(goal_id, goal_text, completed, summary="", created_files=(),
      error="")`
    - Implement `GoalExecutionRuntime(RuntimeContract)`: `__init__(operator_factory, *,
      memory_sink=None)`, `name` → `"goal_execution"`, all `RuntimeContract` members, and pure-ish
      `execute_goal(goal_id, goal_text) -> GoalExecutionRecord` that builds an operator via the factory,
      calls `.run(goal_text)`, and maps `OperatorOutcome` (`completed`/`summary`/`created_files`)
      faithfully; on any exception returns `completed=False` with the error captured (never raises)
    - Implement `initialize(kernel)` (store kernel + subscribe to `goal.created`) and `_on_goal_created`
      (defensive `.get`, run `execute_goal`, emit `goal.completed`/`goal.failed` via `make_event`,
      record an episode via the sink; never raise into the tick loop)
    - Implement `checkpoint()`/`restore()` (round-trip a small counter of executed goals), `health()`,
      `tick`/`observe`/`publish`/`receive`/`shutdown`
    - Import ONLY `friday.events`, `friday.kernel.contracts`, stdlib
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.1, 4.2, 4.3, 5.1_

  - [ ]* 1.2 Write property + unit tests for the runtime core
    - **Property 1: Kernel goal execution delegates, never re-implements**
    - **Property 2: Execution never raises**
    - **Property 3: Lifecycle events are emitted exactly once**
    - **Property 8: RuntimeContract completeness**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 4.2, 4.3**

- [ ] 2. Memory sink — `friday/kernel/memory_sink.py`
  - [ ] 2.1 Implement the optional fail-safe MemorySink
    - Create `friday/kernel/memory_sink.py` with a `"""Ch 14 — ..."""` docstring
    - Implement `MemorySink(friday_memory=None)` with `record_episode(episode: dict) -> bool` that
      returns False (no-op) when no backend, records via a duck-typed backend method when present
      (try `record_turn`/`add_episode`/`record_episode` defensively), and NEVER raises
    - Import only stdlib (backend arrives injected; no `friday.memory` import)
    - _Requirements: 2.1, 2.2, 2.3, 5.1_

  - [ ]* 2.2 Write property tests for the memory sink
    - **Property 4: Memory sink is optional and fail-safe**
    - **Validates: Requirements 2.1, 2.2, 2.3**

- [ ] 3. Bridge kernel routing (additive) — `friday/bridge.py`
  - [ ] 3.1 Add opt-in kernel routing without changing legacy defaults
    - Add `use_kernel_execution: bool = False` to `BridgeConfig`
    - Add an optional `kernel=None` parameter to `FridayBridge.__init__` (store as `self._kernel`);
      default None so all existing construction sites are unchanged
    - Implement `_execute_via_kernel(self, text) -> str`: if `self._kernel` is None, return
      `self._execute_multi_step(text, None)` (fallback); otherwise `submit_goal`, await the
      `goal.completed`/`goal.failed` lifecycle event (subscribe a one-shot collector before submit),
      and format the same style of human-readable string the legacy path returns
    - In `_handle_friday`'s multi-step/complex branches, call `_execute_via_kernel` ONLY when
      `self._config.use_kernel_execution and self._kernel is not None`; otherwise call the unchanged
      `_execute_multi_step`
    - Do NOT change `_execute_simple_action` (Level-1 FridayEngine path)
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 3.2 Write bridge backward-compatibility tests
    - **Property 5: Bridge default preserves legacy behavior**
    - **Property 6: Bridge kernel path degrades safely**
    - Add `tests/friday/test_m12_bridge_compat.py`: default bridge (no kernel) routes multi-step to the
      legacy path and never constructs a kernel; `_execute_via_kernel` with no kernel falls back and
      returns a non-empty string
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

- [ ] 4. Server wiring (additive) — `friday/api/server.py`
  - [ ] 4.1 Wire the kernel + runtime behind the opt-in flag
    - In `create_app()`, when `os.getenv("FRIDAY_USE_KERNEL_EXECUTION") == "1"`: construct a
      `CognitiveKernel`, build a `GoalExecutionRuntime` with an operator factory
      `lambda goal: Operator(model_router=model_router, ...)` and a `MemorySink(friday_memory)`,
      `register_runtime` it, `start()` the kernel, and pass `kernel=kernel` +
      `BridgeConfig(use_kernel_execution=True)` into `FridayBridge`
    - When the flag is unset (default), construct the bridge exactly as today (no kernel) — behavior
      unchanged
    - Guard the whole kernel-wiring block in try/except so a wiring failure falls back to the legacy
      bridge and never prevents the server from starting
    - _Requirements: 3.1, 4.4_

- [ ] 5. Tests — isolation, integration
  - [ ]* 5.1 Write the AST isolation test
    - Add `tests/friday/test_m12_isolation.py` mirroring prior isolation tests: `execution.py` imports
      only `friday.events` / `friday.kernel.contracts` / stdlib (NOT operator/memory/bridge/executor);
      each M12 module has a `"""Ch NN — ..."""` docstring; no banned app/site name or URL literal
    - **Property 7: Runtime isolation (import boundary)**
    - **Validates: Requirements 4.1, 5.1, 5.2**

  - [ ]* 5.2 Write the kernel-event integration test
    - Add `tests/friday/test_m12_integration.py`: a real `CognitiveKernel` + registered
      `GoalExecutionRuntime` with a STUB operator factory (returns a canned OperatorOutcome-shaped
      object); `submit_goal("do X")` → the runtime executes → assert a `goal.completed` event lands on
      the bus with the mapped summary; a factory whose `.run` raises → assert `goal.failed`; assert a
      `MemorySink` with a recording stub captured exactly one episode
    - _Requirements: 1.4, 2.1, 4.2_

- [ ] 6. Final regression checkpoint
  - [ ] 6.1 Run the full suite and confirm green
    - Run `python -m pytest tests/friday/ -q`; confirm ≥ 1166 pre-existing tests plus the new M12 tests
      pass under `FRIDAY_DRY_RUN=1`
    - _Requirements: 4.4_

## Notes

- Tasks marked `*` are test tasks and may run alongside or right after their implementation task.
- All work is additive: new files under `friday/kernel/`, additive-only edits to `bridge.py` and
  `api/server.py`. No existing public signature changes; every new parameter defaults to today's
  behavior. `Operator`, `GoalExecutor`, and `core.py` are NOT deleted or modified.
- The M12 gate is REVERSIBILITY: with `FRIDAY_USE_KERNEL_EXECUTION` unset, the app is byte-for-byte
  identical to today, and the existing 1166 tests are unaffected.
- Deeper retirements (rewriting the executor's if/elif dispatch to use CapabilityRegistry — TD-5;
  deleting the legacy Operator once the kernel path is proven in production) are deliberately deferred
  beyond M12; they change behavior and must not be bundled with this reversible foundation.
- All tests set `os.environ.setdefault("FRIDAY_DRY_RUN", "1")` before importing any `friday` module.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "2.2", "3.1"] },
    { "id": 2, "tasks": ["3.2", "4.1", "5.1"] },
    { "id": 3, "tasks": ["5.2"] },
    { "id": 4, "tasks": ["6.1"] }
  ]
}
```
