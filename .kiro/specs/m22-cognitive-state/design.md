# Design: M22 — Cognitive State Manager (completion)

## Overview

M22 completes FAS §A2.12 additively over the existing
`friday/cognition/state.py::CognitiveStateManager`. The manager already models mode / focus /
attention / interruptibility / thinking-depth / reasoning-budget / urgency / active-goal and
is kernel-attached + queryable via `snapshot()`. This milestone adds the two missing
mind-state elements (Cognitive Load, Background cognition state), completes engagement-mode
coverage from the event stream (exploration + conversation + return-to-idle, not just
execution), and adds a small pure query surface (`should_interrupt`, `suggested_thinking_depth`)
so the Event System and Deliberation can consult the state. It is then wired into the guarded
bootstrap as `kernel.cognitive_state`. The manager's isolation invariant is preserved: it
imports only `friday.events` + stdlib, is updated purely from events, and its handlers never
raise into the tick loop. No duplicate state store is introduced — this remains the model of
FRIDAY's own mind, distinct from the World Model.

## Architecture

```
   kernel events                         queries (pure reads)
   ─────────────                         ────────────────────
   action.executed ──▶ EXECUTION         Event System ──▶ should_interrupt(urgency)
   exploration.* ─────▶ EXPLORATION      Deliberation ──▶ suggested_thinking_depth()
   conversation/input ▶ CONVERSATION     any subsystem ─▶ snapshot()
   goal.state_changed ▶ focus / IDLE
        │
        ▼
   CognitiveStateManager  (single mind-state authority; kernel.cognitive_state)
   state: mode, focus, active_goal, attention, interruptible, thinking_depth,
          reasoning_budget, urgency, + cognitive_load, + background_active
```

### Modified / new components

| Component | File | Change |
|---|---|---|
| Mind-state | `friday/cognition/state.py` | add `cognitive_load` + `background_active`; load tracking; mode coverage; query surface (additive) |
| Bootstrap | `friday/api/server.py` | attach + expose `kernel.cognitive_state` in the guarded path |
| Docs/matrix | `docs/architecture/*` | A2.12 → Built; true up stale A2.1/A2.2/A2.3/A2.6 rows |

## Components and Interfaces

### C1 — `CognitiveState` (extend the dataclass, additive)
Add two defaulted fields AFTER the existing ones (preserving order/defaults):
`cognitive_load: float = 0.0` (0..1) and `background_active: bool = False`. Add a
`to_dict()` returning a JSON-safe projection (enums as `.value`) for events/logging
(Requirement 1.2). `snapshot()` continues to return an immutable `dataclasses.replace` copy.

### C2 — Cognitive load tracking (`CognitiveStateManager`)
- `set_load(value)` / `adjust_load(delta)` — always `_clamp01` (Requirement 2.1, 2.3).
- `set_focus(goal_id, *, attention=1.0)` (existing) additionally sets `cognitive_load` from
  the committed attention (higher attention ⇒ higher load); returning to idle lowers it
  (Requirement 2.2). Implemented so the existing `set_focus` signature/behavior for
  focus/attention is preserved and load is an additive side effect.

### C3 — Engagement-mode coverage from events
- Preserve `_on_action_executed` → `EXECUTION` and `_on_goal_state_changed` → focus.
- Extend `_on_goal_state_changed`: when a goal reaches a terminal state (e.g.
  `completed`/`failed`/`abandoned`) and no other goal is active, return to `IDLE`, clear
  focus, and lower load (Requirement 3.3).
- `attach(kernel)` additionally subscribes to a generic exploration signal and a
  conversation/user-input signal, entering `EXPLORATION` / `CONVERSATION` respectively
  (Requirement 3.2). Signals are matched on generic event types already present on the bus
  (e.g. `exploration.*` and a conversation/user-input event); handlers read defensively and
  never raise (Requirement 3.4). `background_active` is set when background cognition
  (e.g. reflection while idle) is indicated and cleared when foreground work resumes.

### C4 — Query surface (pure reads)
- `should_interrupt(urgency: float) -> bool` (Requirement 4.1): returns `True` when the
  operator is `interruptible`; when NOT interruptible, returns `True` only if `urgency`
  exceeds a documented high-urgency threshold that also scales with `cognitive_load`
  (higher load ⇒ higher bar). Pure; deterministic for a given state.
- `suggested_thinking_depth() -> ThinkingDepth` (Requirement 4.2): derived from
  `reasoning_budget` / `cognitive_load` — low budget or high load ⇒ `SHALLOW`, ample budget
  and low load ⇒ `DEEP`, else `NORMAL`. Pure; no mutation.

### C5 — Bootstrap wiring (`friday/api/server.py`)
Within the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block, construct a
`CognitiveStateManager`, `attach(kernel)`, and expose it as `kernel.cognitive_state`.
Additive; default path byte-unchanged; wiring failure logged with structured context, never
crashes bootstrap (Requirement 5.2).

## Data Models

- `CognitiveState` — extended with `cognitive_load` + `background_active` (C1); no new store.
  `to_dict()` is JSON-safe. Enums `CognitiveMode` / `ThinkingDepth` unchanged.

## Correctness Properties

### Property 1: state additions + clamping + immutable snapshot
`cognitive_load` is always in `[0, 1]` under any sequence of `set_load`/`adjust_load`/focus
changes; `background_active` is a bool; `snapshot()` returns an independent copy; `to_dict()`
JSON-serializes.
**Validates: Requirements 1.1, 1.2, 2.1, 2.3**

### Property 2: load reflects engagement
Focusing with higher attention yields load ≥ focusing with lower attention; returning to
idle does not increase load.
**Validates: Requirements 2.2**

### Property 3: mode coverage from events
An action event ⇒ EXECUTION; an exploration signal ⇒ EXPLORATION; a conversation signal ⇒
CONVERSATION; a terminal goal state with nothing else active ⇒ IDLE + cleared focus.
Malformed events never raise and never corrupt state.
**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

### Property 4: interruptibility query
`should_interrupt` returns True when interruptible; when not interruptible it returns True
only for urgency above the load-scaled threshold; it never mutates state and is deterministic.
**Validates: Requirements 4.1, 4.3**

### Property 5: reasoning-depth query
`suggested_thinking_depth` returns SHALLOW under low budget / high load and DEEP under ample
budget / low load; pure and deterministic.
**Validates: Requirements 4.2, 4.3**

### Property 6: isolation preserved
`friday/cognition/state.py` imports only `friday.events` + stdlib (no goals/world/
deliberation/memory/competence imports); the manager mutates only its own state and emits
nothing that isn't already event-driven; without a kernel it is a usable in-memory object.
**Validates: Requirements 5.1**

## Error Handling

Structured-error-model compliant (A2.14.2): every event handler catches narrowly and
degrades to a no-op, never raising into the bus (mirrors the existing handlers). Bootstrap
wiring is guarded and logged. `BaseException` propagates. No silent blanket swallow without a
justifying comment.

## Testing Strategy

Hypothesis property tests (≥100 examples, tagged `# Feature: m22-cognitive-state, Property N`)
for Properties 1–6 using a fake/real `CognitiveKernel` and synthetic event streams. No
separate benchmark is required (this is a coordinator, not a measured capability); the
existing capability benchmarks remain the scorecard. Full regression suite must stay green
(zero failures).

## Traceability

- FAS Ch 67; v2.1 amendment **A2.12 — Cognitive State Manager** (Partial → Built).
- Matrix true-up: A2.1 (`friday/world/*` M15), A2.2 (`friday/perception/fingerprint*.py`),
  A2.3 (`friday/deliberation/expanded_utility.py` + `recovery_contract.py`), A2.6
  (`friday/resources/economics.py` + `scheduler.py`) corrected Partial/Absent → Built.
- No duplicate mind-state store; no application-specific logic (Axiom 15); updated purely
  from the kernel event stream (Ch 52).
