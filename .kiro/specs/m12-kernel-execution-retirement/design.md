# Design Document: M12 — Kernel-Backed Execution & Legacy Retirement

## Overview

The M1–M11 kernel substrate (`CognitiveKernel`, event bus, world model, goal graph, deliberator,
capability registry, verification engine, evolution/plugins/benchmarks/federation) is **fully built
and green (1166 tests)** — but an exhaustive wiring audit revealed it is **test-only**. Both live
entry points — `friday/api/server.py` (the uvicorn server) and `main.py` (gated legacy loop) — run
goals entirely through the legacy pipeline `FridayBridge → Operator → GoalExecutor`. The kernel is
never constructed at runtime. `submit_goal` merely records a stub and emits `goal.created`; nothing
executes it.

This means the technical debt items TD-2/4/5/6/8 cannot be *deleted* safely — the kernel cannot yet
run a real end-to-end goal, and the legacy pipeline is the only working execution engine. The correct,
low-risk resolution is **build-then-retire**, not delete:

1. **Build a kernel-backed execution surface** (`friday/kernel/execution.py`) — a
   `GoalExecutionRuntime(RuntimeContract)` that subscribes to `goal.created`, **delegates execution to
   the existing, proven `Operator`** (zero behavior change), and emits `goal.completed` / `goal.failed`
   lifecycle events carrying the `OperatorOutcome`. This makes the kernel able to actually run goals
   — through the code that already works — for the first time.

2. **Wire memory at that single seam (TD-6)** — the runtime records each completed goal as a
   `memory.candidate`-style episode via an injected, optional memory sink, so memory forms on the
   live path without the `Operator`/`GoalExecutor` importing memory (preserving their isolation).

3. **Route the live entry point through the kernel behind a flag (TD-2/TD-8)** — `FridayBridge` gains
   an optional `kernel` collaborator. When present and `BridgeConfig.use_kernel_execution` is true, the
   multi-step path submits the goal to the kernel and awaits the lifecycle event instead of
   constructing an `Operator` inline. When absent (default), behavior is **byte-for-byte the legacy
   path** — a pure superset, fully backward compatible.

4. **Retire only the confirmed-dead code (TD-2)** — the orphaned parallel dispatchers in `bridge.py`
   (`_execute_operator_step` / `_run_multi_step_browser` / `_execute_browser_step`) are already removed.
   `core.py::FridayEngine` remains the Level-1 verifier (it is *not* dead — it is the live simple-action
   path); it is left intact.

**What M12 deliberately does NOT do:** it does not delete `Operator`, `GoalExecutor`, or `core.py`;
it does not rewrite the executor's dispatch (TD-5) or force the kernel to be the only path. Those are
larger behavior-changing efforts deferred until the kernel-backed path has proven itself in
production. M12's gate is *reversibility*: with the flag off, the system is identical to today.

All new code carries `"""Ch NN — ..."""` docstrings, communicates through kernel events (Ch 52), and
all tests run under `FRIDAY_DRY_RUN=1` so the 1166 existing tests stay green.

---

## Architecture

```mermaid
graph TD
    subgraph Live["Live entry points"]
        API[friday/api/server.py — uvicorn]
        MAIN[main.py — gated]
    end

    subgraph Bridge["FridayBridge (superset — flag-gated)"]
        ROUTE[_handle_friday]
        LEGACY[_execute_multi_step\nlegacy: builds Operator inline]
        KPATH[_execute_via_kernel\nNEW: submit_goal + await lifecycle]
        ROUTE --> KPATH
        ROUTE -. flag off .-> LEGACY
    end

    subgraph Kernel["CognitiveKernel (M1)"]
        BUS[(Event Bus)]
        GER[GoalExecutionRuntime : RuntimeContract]
    end

    subgraph Proven["Existing proven engine (unchanged)"]
        OP[Operator.run → OperatorOutcome]
        EX[GoalExecutor]
        OP --> EX
    end

    MEM[MemorySink (optional, injected)]

    API --> ROUTE
    MAIN --> ROUTE
    KPATH -- submit_goal --> BUS
    BUS -- goal.created --> GER
    GER -- delegates --> OP
    GER -- goal.completed / goal.failed --> BUS
    GER -- record episode --> MEM
    KPATH -- awaits lifecycle event --> BUS
```

**Isolation rule (Ch 52).** The `GoalExecutionRuntime` is a first-class `RuntimeContract` the kernel
`register_runtime`s. It communicates outward only via `publish_event`. It holds a reference to an
`Operator` *factory* (a callable), not to the bridge, so it stays decoupled. Memory is an injected
sink (duck-typed `record_episode`), so the runtime never imports `friday.memory` directly — mirroring
the M8 "learning proposes, memory decides" boundary.

---

## How M12 Plugs Into Existing Code (real signatures)

**CognitiveKernel (M1) — `friday/kernel/kernel.py`**
```python
class CognitiveKernel:
    def register_runtime(self, runtime: RuntimeContract) -> None
    def submit_goal(self, goal_text: str, constraints: Optional[dict] = None) -> str  # emits goal.created
    def subscribe(self, pattern: str, handler) -> str
    def publish_event(self, event: Event) -> None
    def query_goals(self) -> List[dict]
    def health(self) -> dict
```

**RuntimeContract (M1) — `friday/kernel/contracts/runtime.py`** (GoalExecutionRuntime implements this)
```python
class RuntimeContract(ABC):
    @property
    def name(self) -> str: ...
    def initialize(self, kernel) -> None: ...
    def tick(self, logical_time: int) -> None: ...
    def observe(self) -> List[Dict[str, Any]]: ...
    def receive(self, event: Event) -> None: ...
    def publish(self, event: Event) -> None: ...
    def checkpoint(self) -> Dict[str, Any]: ...
    def restore(self, state: Dict[str, Any]) -> None: ...
    def shutdown(self) -> None: ...
    def health(self) -> Dict[str, Any]: ...
```

**Operator (existing, unchanged) — `friday/operator.py`**
```python
class Operator:
    def __init__(self, model_router=None, browser_controller=None, max_iterations=2, browser_strategy=None)
    def run(self, goal: str) -> OperatorOutcome   # .completed, .summary, .created_files, .evidence
```

**FridayBridge (existing) — `friday/bridge.py`** — `_execute_multi_step(text, automation)` currently
builds an `Operator` inline. M12 adds an alternate `_execute_via_kernel(text)` chosen by config.

---

## Components and Interfaces

### Component 1: GoalExecutionRuntime (`friday/kernel/execution.py`)

**Purpose**: The missing link that lets the kernel actually execute a goal — by delegating to the
existing `Operator`. Subscribes to `goal.created`, runs the operator, emits lifecycle events, and
records an episode to an optional memory sink.

**Interface**:
```python
class GoalExecutionRuntime(RuntimeContract):
    """Ch 17/18/20 — executes kernel goals by delegating to the proven Operator."""

    def __init__(
        self,
        operator_factory: Callable[[str], Any],   # goal_text -> object with .run(goal)->OperatorOutcome
        *,
        memory_sink: Optional[Any] = None,          # duck-typed: .record_episode(dict) -> None
    ) -> None: ...

    @property
    def name(self) -> str: ...                        # "goal_execution"

    def initialize(self, kernel) -> None:
        """Store the kernel and subscribe to goal.created (Ch 52)."""

    def execute_goal(self, goal_id: str, goal_text: str) -> "GoalExecutionRecord":
        """Pure-ish core: build an operator via the factory, run it, map the
        OperatorOutcome to a GoalExecutionRecord. Never raises — a failure is a
        record with completed=False and the error captured."""

    # RuntimeContract members (tick/observe/publish/checkpoint/restore/shutdown/health)
    def _on_goal_created(self, event) -> None:
        """Reflect a goal.created event into execute_goal, then emit goal.completed
        / goal.failed and record an episode. Never raises into the tick loop."""
```

**Responsibilities**:
- Delegate execution to the injected `operator_factory` — never re-implement execution logic.
- Emit `goal.completed` (payload: `goal_id, summary, created_files, completed=True`) or `goal.failed`
  (payload: `goal_id, error`) via `make_event`.
- Record a completed goal to `memory_sink.record_episode({...})` when a sink is present; a missing or
  throwing sink never breaks execution.
- **Import boundary**: imports only `friday.events`, `friday.kernel.contracts`, and stdlib. It does
  NOT import `friday.operator`, `friday.memory`, or the bridge — the operator arrives as a factory and
  memory as a sink, injected by the wiring layer.

### Component 2: MemorySink adapter (`friday/kernel/memory_sink.py`)

**Purpose**: A thin, optional adapter that lets the runtime persist an episode without the kernel
package importing `friday.memory`. The concrete sink is constructed by the wiring layer (server) and
injected.

**Interface**:
```python
class MemorySink:
    """Ch 14 — a minimal episode-recording seam (duck-typed record_episode)."""

    def __init__(self, friday_memory: Any = None) -> None: ...
    def record_episode(self, episode: dict) -> bool:
        """Record a completed-goal episode. Returns True on success, False on
        no-op/failure. NEVER raises. Under a missing backend this is a no-op."""
```

**Responsibilities**:
- Bridge the runtime to whatever memory backend exists (`FridayMemory`) via duck typing.
- Fail safe: no backend, or a backend error, yields `False` and never propagates.

### Component 3: Bridge kernel routing (`friday/bridge.py` — additive)

**Purpose**: Let the live entry point run multi-step goals through the kernel when configured, while
preserving the exact legacy path as the default.

**Interface** (additive, no signature changes to existing public methods):
```python
@dataclass
class BridgeConfig:
    # ... existing fields ...
    use_kernel_execution: bool = False   # NEW: opt-in; default preserves legacy behavior

class FridayBridge:
    def __init__(self, ..., kernel: Optional[Any] = None) -> None: ...   # NEW optional collaborator

    def _execute_via_kernel(self, text: str) -> str:
        """Submit the goal to the kernel and await the goal.completed/goal.failed
        lifecycle event; format the same human-readable string the legacy path
        returns. Falls back to the legacy path if no kernel is wired."""
```

**Responsibilities**:
- When `use_kernel_execution` is true AND a kernel is wired, `_handle_friday`'s multi-step branch calls
  `_execute_via_kernel`; otherwise it calls the unchanged `_execute_multi_step`.
- `_execute_via_kernel` degrades to `_execute_multi_step` when no kernel is present (never errors).
- No change to Level-1 (`_execute_simple_action` → `FridayEngine`) behavior.

### Component 4: Server wiring (`friday/api/server.py` — additive)

**Purpose**: Construct a real `CognitiveKernel`, register the `GoalExecutionRuntime` with an operator
factory + memory sink, and pass the kernel into the bridge — behind the same opt-in flag.

**Responsibilities**:
- Build the kernel, register the runtime, and inject the kernel into `FridayBridge`.
- Keep the flag default off so the shipped server behaves exactly as today unless explicitly enabled
  via `FRIDAY_USE_KERNEL_EXECUTION=1`.

---

## Event Vocabulary

| Event type | Direction | Producer → Consumer | Key payload fields |
|---|---|---|---|
| `goal.created` | consumed | Kernel.submit_goal → GoalExecutionRuntime | `goal_id, text` |
| `goal.completed` | produced | GoalExecutionRuntime | `goal_id, summary, created_files, completed` |
| `goal.failed` | produced | GoalExecutionRuntime | `goal_id, error` |

---

## Data Models

```python
from dataclasses import dataclass, field
from typing import Tuple

@dataclass(frozen=True)
class GoalExecutionRecord:
    """The outcome of executing one kernel goal via the Operator."""
    goal_id: str
    goal_text: str
    completed: bool
    summary: str = ""
    created_files: Tuple[str, ...] = ()
    error: str = ""
```

---

## Correctness Properties

Verified with property/unit tests under `FRIDAY_DRY_RUN=1`.

### Property 1: Kernel goal execution delegates, never re-implements

`GoalExecutionRuntime.execute_goal` invokes the injected `operator_factory` exactly once per goal and
maps its `OperatorOutcome` faithfully (`completed`, `summary`, `created_files` preserved).
**Validates: Requirements 1.1, 1.2**

### Property 2: Execution never raises

For any operator factory — including one whose `.run` raises — `execute_goal` returns a
`GoalExecutionRecord` (with `completed=False` and the error captured) and never propagates an
exception. `_on_goal_created` never raises into the kernel tick loop.
**Validates: Requirements 1.3, 4.2**

### Property 3: Lifecycle events are emitted exactly once

A successful goal emits exactly one `goal.completed` and zero `goal.failed`; a failed goal emits
exactly one `goal.failed` and zero `goal.completed`.
**Validates: Requirements 1.4**

### Property 4: Memory sink is optional and fail-safe

With no sink, execution completes normally and records nothing. With a throwing sink, execution still
completes and the failure is swallowed (returns without raising). With a working sink, exactly one
episode is recorded per completed goal.
**Validates: Requirements 2.1, 2.2, 2.3**

### Property 5: Bridge default preserves legacy behavior

With `use_kernel_execution=False` (default) OR no kernel wired, `_handle_friday`'s multi-step path
calls `_execute_multi_step` (the legacy Operator path) and never touches the kernel.
**Validates: Requirements 3.1, 3.4**

### Property 6: Bridge kernel path degrades safely

`_execute_via_kernel` with no kernel present falls back to `_execute_multi_step` and returns a
well-formed string (never raises, never returns None).
**Validates: Requirements 3.2, 3.3**

### Property 7: Runtime isolation (import boundary)

`friday/kernel/execution.py` imports only `friday.events*`, `friday.kernel.contracts*`, and stdlib —
never `friday.operator`, `friday.memory`, `friday.bridge`, or `friday.executor`.
**Validates: Requirements 4.1**

### Property 8: RuntimeContract completeness

`GoalExecutionRuntime` implements every `RuntimeContract` member; `checkpoint()`/`restore()`
round-trips; `health()` reports a status dict; a raising handler is contained and reported degraded.
**Validates: Requirements 4.3, 4.4**

---

## Error Handling

- **Operator factory raises / operator.run raises**: caught in `execute_goal`; returns a record with
  `completed=False, error=<str>`. The runtime then emits `goal.failed`.
- **Memory sink missing or raises**: `record_episode` returns `False` / is skipped; execution and
  event emission are unaffected.
- **No kernel wired but flag on**: `_execute_via_kernel` falls back to `_execute_multi_step` (the
  legacy path) so the user still gets a result.
- **Event emission failure**: guarded like every other runtime — emission never raises into the tick
  loop; a failure is recorded in `health()` degraded reasons.
- **goal.created with missing fields**: `_on_goal_created` reads payload defensively with `.get(...)`
  and skips a goal lacking a `goal_id`/`text` without raising.
- **Backward compatibility**: every new parameter (`kernel`, `use_kernel_execution`, `memory_sink`)
  defaults to a value that reproduces today's behavior, so the existing 1166 tests are unaffected.

---

## Testing Strategy

- **Unit tests** (`tests/friday/test_m12_units.py`): `execute_goal` maps a stub operator's outcome;
  a throwing operator yields a failed record; `MemorySink` no-op without backend, records with one,
  swallows a throwing backend; `GoalExecutionRecord` immutability.
- **Property tests** (`tests/friday/test_m12_properties.py`): the 8 correctness properties via
  Hypothesis/parametrization under `FRIDAY_DRY_RUN=1`.
- **Isolation test** (`tests/friday/test_m12_isolation.py`): AST scan — `execution.py` imports only
  the allowed prefixes; module has a `"""Ch NN — ..."""` docstring; no banned app/site name or URL
  literal.
- **Integration test** (`tests/friday/test_m12_integration.py`): a real `CognitiveKernel` +
  registered `GoalExecutionRuntime` with a stub operator factory; `submit_goal` → the runtime executes
  → `goal.completed` lands on the event log with the mapped summary; a failing factory → `goal.failed`.
- **Bridge backward-compat test** (`tests/friday/test_m12_bridge_compat.py`): a `FridayBridge` with
  default config (no kernel) routes multi-step to the legacy path exactly as before; with a kernel +
  flag, it routes through `_execute_via_kernel` and returns a well-formed string.
- **Regression**: full suite stays green (≥ 1166 + new tests) under `python -m pytest tests/friday/ -q`.
