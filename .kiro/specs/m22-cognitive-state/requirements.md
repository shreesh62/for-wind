# Requirements Document

M22 — Cognitive State Manager (completion)

## Introduction

The v2.1 traceability matrix marks **A2.12 Cognitive State Manager** as *Partial*. The
existing `friday/cognition/state.py::CognitiveStateManager` already tracks mode, focus,
attention, interruptibility, thinking depth, reasoning budget, urgency, and active goal, is
kernel-attached (updates focus/mode from `goal.state_changed` / `action.executed`), and is
queryable via `snapshot()`. Per FAS §A2.12.1 the full mental-state model additionally
requires **Cognitive Load** and a **Background cognition state**, coverage of all four
engagement modes (idle / exploration / execution / conversation) driven from events, and it
must be genuinely *queryable by every other subsystem* (e.g. the Event System deciding
whether to surface an interruption now; Deliberation sizing reasoning depth to the moment).
It is the capstone coordinator of Architecture v2.1 — built last because it coordinates the
subsystems that now exist (Deliberation, Resources, Reflection).

This milestone completes A2.12 **additively** over the existing manager: it adds the missing
`cognitive_load` and `background_active` state, drives exploration/conversation modes from
events (not just execution), exposes a small query surface the Event System / Deliberation
can consult (interruptibility decision + a suggested reasoning depth), and wires the manager
into the guarded kernel-execution bootstrap so it is live and queryable. It preserves the
manager's isolation invariant (imports only `friday.events` + stdlib; updated purely from the
event stream; handlers never raise) and introduces no duplicate state store — the World Model
remains the model of external reality; this remains the model of FRIDAY's own mind.

This milestone also trues up the v2.1 traceability matrix, which is stale: **A2.1** (World
Model v2), **A2.2** (Environment Intelligence / fingerprints), **A2.3** (Deliberation v2 /
expanded utility + recovery contracts), and **A2.6** (Resource Manager v2 / economics +
reallocation) are all implemented in the codebase but still shown Partial/Absent.

## Glossary

- **Cognitive State Manager**: the single authority for FRIDAY's own mind-state (distinct
  from the World Model's model of reality).
- **Cognitive Load**: a `0..1` estimate of how heavily loaded the operator currently is
  (rises with committed attention / active work, decays toward idle).
- **Background cognition state**: whether background (non-foreground) cognition is currently
  active (e.g. reflection/consolidation running while idle).
- **Engagement mode**: one of `IDLE, EXPLORATION, EXECUTION, CONVERSATION`.
- **Interruptibility decision**: a query answering whether an interruption of a given
  urgency should be surfaced now, given the current state.
- **Snapshot**: an immutable copy of the current state any subsystem may read.

## Requirements

### Requirement 1: Complete the mind-state model

**User Story:** As the architecture, I want the full FAS §A2.12.1 mind-state represented so
FRIDAY knows what it is doing, not merely what it is doing it for.

#### Acceptance Criteria
1. THE `CognitiveState` SHALL include a `cognitive_load` field in `[0, 1]` (clamped) and a
   `background_active` boolean, in addition to the existing fields.
2. THE snapshot SHALL remain an immutable copy (callers cannot mutate internals) and SHALL
   be JSON-projectable for events/logging.
3. THE additions SHALL be additive — existing fields, methods, defaults, and the
   `snapshot()` return contract SHALL be unchanged.

### Requirement 2: Cognitive load tracking

**User Story:** As Deliberation and the Event System, I want a load signal so decisions can
account for how busy the operator is.

#### Acceptance Criteria
1. THE manager SHALL expose a way to set/adjust `cognitive_load`, always clamped to `[0, 1]`.
2. WHEN focus is set with an attention level THEN `cognitive_load` SHALL reflect the
   committed attention (higher attention ⇒ higher load), and WHEN the operator returns to
   idle THEN load SHALL decrease.
3. THE load value SHALL never leave `[0, 1]` under any sequence of updates.

### Requirement 3: Full engagement-mode coverage from events

**User Story:** As FRIDAY, I want my mode to reflect what I am actually doing, driven by the
event stream.

#### Acceptance Criteria
1. THE manager SHALL enter `EXECUTION` on action execution (existing behavior, preserved).
2. THE manager SHALL enter `EXPLORATION` when an exploration signal is observed on the bus
   (e.g. an exploration/experiment event) and `CONVERSATION` when a conversation/user-input
   signal is observed, driven purely from events.
3. THE manager SHALL be able to return to `IDLE` when work completes (e.g. a goal reaches a
   terminal state), and background cognition state SHALL be updated accordingly.
4. THE event handlers SHALL read payloads defensively and SHALL never raise into the tick
   loop.

### Requirement 4: Queryable coordination surface

**User Story:** As the Event System and Deliberation, I want to consult the cognitive state
so interruptions and reasoning depth respect the moment.

#### Acceptance Criteria
1. THE manager SHALL expose `should_interrupt(urgency)` returning whether an interruption of
   the given urgency should be surfaced now, honoring `interruptible` and current load
   (a sufficiently urgent interruption may still surface; a low-urgency one SHALL be
   deferred while non-interruptible or highly loaded).
2. THE manager SHALL expose a `suggested_thinking_depth()` (or equivalent) derived from
   current load / budget so Deliberation can size reasoning depth to the moment.
3. THESE queries SHALL be pure reads (no mutation) and SHALL be deterministic for a given
   state.

### Requirement 5: Additive, safe integration

**User Story:** As the maintainer, I want the manager wired so it changes no default
behavior, is replay-compatible, and never breaks hermetic tests.

#### Acceptance Criteria
1. THE manager SHALL preserve its isolation: it SHALL import only `friday.events` + stdlib,
   SHALL be updated purely from the kernel event stream, and its handlers SHALL never raise.
2. THE manager SHALL be attached within the guarded kernel-execution path and exposed for
   query (e.g. `kernel.cognitive_state`); it SHALL be inert without a kernel and degrade
   safely on wiring failure.
3. THE default (flag-off) path SHALL be byte-unchanged and the full existing test suite
   SHALL remain green (zero failures).

### Requirement 6: Verification artifacts and traceability true-up

**User Story:** As the maintainer, I require every milestone to ship its evidence, and I want
the v2.1 traceability matrix to reflect reality.

#### Acceptance Criteria
1. THE milestone SHALL include property/unit tests covering the new fields + clamping, load
   tracking bounds, mode coverage from events, the interruptibility + reasoning-depth
   queries, the isolation invariant, and defensive handlers.
2. THE milestone SHALL update the FAS (A2.12 → Built) and correct the v2.1 traceability
   matrix so that A2.1, A2.2, A2.3, A2.6, and A2.12 reflect their true Built state, with a
   short note citing the implementing modules for each corrected row.
3. THE milestone SHALL produce an after-milestone architecture review with a full-suite
   checkpoint (zero failures).
