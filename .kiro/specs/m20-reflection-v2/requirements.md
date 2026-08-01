# Requirements Document

M20 — Reflection v2 (Layered Reflection)

## Introduction

The v2.1 traceability matrix marks **A2.10 Layered reflection (5 layers)** as *Partial* —
the existing `friday/cognition/reflection.py::ReflectionEngine` reflects at four *scales*
(micro/task/goal/session) and correctly emits only `memory.candidate` events (Reflection
proposes; Memory decides — Ch 13.16/14.8), but the normative five-**layer** hierarchy of
FAS §A2.10.1 is not formalized. That hierarchy is:

`Immediate` (per action) → `Session` (per goal/session) → `Long-Term` (across sessions) →
`Skill` (per capability, feeds the §A2.5 skill pipeline) → `Architectural` (evaluates
whether the architecture itself still serves the user and proposes structural change).

This milestone delivers the five-layer model **additively** over the existing engine and
kernel event bus. It reuses the current pure `reflect()` core, the `ReflectionRecord`, and
the `memory.candidate` mechanism — introducing no second reflection system and no direct
memory writes. Each layer reflects at a distinct temporal/abstraction scope and PROPOSES
(emits candidates / structured proposal events); none writes long-term memory directly. The
higher layers (Long-Term, Skill, Architectural) are new consumers that aggregate the stream
of per-goal reflections into cross-session, per-capability, and architectural insights.

## Glossary

- **Reflection layer**: one of the five normative levels at which reflection operates,
  distinguished by scope (single action → whole architecture).
- **Immediate layer**: reflection on a single action's predicted-vs-observed outcome
  (the existing micro scale).
- **Session layer**: reflection over a goal/session (the existing goal/session scale).
- **Long-Term layer**: reflection across sessions — aggregates recurring prediction-error
  and calibration trends over many goals.
- **Skill layer**: per-capability reflection — summarizes how a capability is performing
  and feeds the §A2.5 skill-evolution pipeline as a candidate signal.
- **Architectural layer**: meta-reflection that evaluates whether the architecture still
  serves the user (e.g. persistent miscalibration or a chronically failing domain) and
  emits a structural-change *proposal*.
- **Proposes, not decides**: every layer emits `memory.candidate` and/or a structured
  `reflection.*` proposal event; it never writes memory or mutates other subsystems.
- **ReflectionRecord**: the existing immutable per-reflection record (reused as the input
  stream the higher layers aggregate).

## Requirements

### Requirement 1: Five-layer taxonomy

**User Story:** As the architecture, I want reflection organized into the five normative
layers so each operates at its correct scope.

#### Acceptance Criteria
1. THE system SHALL define a `ReflectionLayer` taxonomy with exactly five members:
   `IMMEDIATE`, `SESSION`, `LONG_TERM`, `SKILL`, `ARCHITECTURAL`.
2. THE `IMMEDIATE` and `SESSION` layers SHALL map to the existing engine's per-action and
   per-goal/session reflection without changing that engine's current outputs.
3. THE taxonomy SHALL be ordered (immediate → architectural) so a layer's scope is
   comparable, and SHALL be JSON-projectable for events/logging.

### Requirement 2: Long-Term layer (across sessions)

**User Story:** As FRIDAY, I want to notice trends across many sessions so recurring
mistakes are recognized rather than re-derived each time.

#### Acceptance Criteria
1. THE Long-Term layer SHALL consume the stream of `reflection.completed` events and
   maintain a bounded, per-(capability, environment) aggregate of prediction-error and
   calibration over time.
2. WHEN a recurring adverse trend crosses a configurable threshold (e.g. mean prediction
   error above a bound over at least N samples) THEN the layer SHALL emit a
   `reflection.longterm` proposal event describing the trend (never a memory write).
3. THE aggregate SHALL be bounded (oldest samples evicted) so memory use never grows
   without limit.
4. THE layer's handlers SHALL never raise into the event bus (malformed events ignored).

### Requirement 3: Skill layer (per capability)

**User Story:** As the skill-evolution pipeline (§A2.5), I want per-capability reflection
signals so a capability that is maturing or regressing is surfaced as a candidate.

#### Acceptance Criteria
1. THE Skill layer SHALL aggregate reflections per capability and compute a per-capability
   summary (sample count, mean prediction error, verified-experience rate).
2. WHEN a capability accumulates sufficient verified low-error experience THEN the layer
   SHALL emit a `reflection.skill` proposal event flagging it as a skill-pipeline candidate
   (a proposal only — promotion remains the pipeline's/Memory's decision).
3. THE layer SHALL expose a query returning the current per-capability summaries.
4. THE layer SHALL be bounded and its handlers SHALL never raise into the bus.

### Requirement 4: Architectural layer (meta)

**User Story:** As the maintainer, I want FRIDAY to flag when the architecture itself may no
longer serve the user, as an explicit proposal for human review.

#### Acceptance Criteria
1. THE Architectural layer SHALL evaluate cross-layer signals (e.g. persistent
   miscalibration across many capabilities, or a chronically failing domain) and SHALL emit
   a `reflection.architectural` proposal event when a configurable meta-threshold is crossed.
2. THE emitted proposal SHALL be advisory only — it SHALL NOT mutate any subsystem, change
   any default, or write memory; it is surfaced for human/observability review.
3. THE layer SHALL be bounded and its handlers SHALL never raise into the bus.

### Requirement 5: Reflection proposes, memory decides (invariant preserved)

**User Story:** As the architecture, I require the Ch 13.16/14.8 invariant to hold across
all five layers.

#### Acceptance Criteria
1. NO reflection layer SHALL import `friday.memory.*` / `friday.competence.*` /
   `friday.recovery.*`, reference `FridayMemory`/`MemoryStore`, or write long-term memory
   directly (mirrors the existing engine's isolation).
2. EVERY layer's only side effects SHALL be emitting `memory.candidate` and/or structured
   `reflection.*` proposal events on the kernel bus.
3. THE existing `ReflectionEngine` outputs (`memory.candidate`, `reflection.completed`)
   SHALL be unchanged by this milestone (additive only).

### Requirement 6: Replay-safe, event-driven integration

**User Story:** As the FRIDAY kernel, I want the layers wired via events so they are
replay-compatible and safe.

#### Acceptance Criteria
1. EVERY emitted `reflection.*` proposal payload SHALL be JSON-serializable so the
   append-only `EventStore` stays replay-compatible.
2. THE higher layers SHALL attach to a kernel via a single reusable wiring helper
   (consistent with the M24 `attach_reactive_loop` pattern), attaching only when enabled.
3. THE layers SHALL be inert without a kernel (no-op), and a wiring failure SHALL degrade
   safely without crashing bootstrap.

### Requirement 7: Additive, safe integration

**User Story:** As the maintainer, I want Reflection v2 wired so it changes no default
behavior and never breaks hermetic tests.

#### Acceptance Criteria
1. THE higher layers SHALL be attached only within the guarded kernel-execution path so
   hermetic tests/benchmarks perform no unbidden I/O.
2. THE default (flag-off) path SHALL be byte-unchanged in behavior.
3. THE full existing test suite SHALL remain green (zero failures).

### Requirement 8: Verification artifacts

**User Story:** As the maintainer, I require every milestone to ship its evidence.

#### Acceptance Criteria
1. THE milestone SHALL include property/unit tests covering the taxonomy, each new layer's
   aggregation + threshold-triggered proposal, the proposes-not-decides isolation invariant,
   bounded storage, and defensive handlers.
2. THE milestone SHALL include a deterministic, hermetic reflection benchmark (layered
   proposal behavior over synthetic reflection streams) that is NOT recorded into the
   committed competence baseline.
3. THE milestone SHALL update the FAS (A2.10 → Built), the traceability matrix, and produce
   an after-milestone architecture review, with a full-suite checkpoint (zero failures).
