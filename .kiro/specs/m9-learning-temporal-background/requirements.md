# Requirements Document

## Introduction

Milestone 9 (M9) extends the FRIDAY General Computer Operator so it can **improve durably over
repeated experience, reason about time, plan across sessions, and make progress while the user is
away.** Milestones 1–8 built and verified (890 passing tests) a persistent, event-driven cognitive
substrate: a `CognitiveKernel` owning the clock / event bus / event store / checkpoints, a
`WorldModel`, a `GoalManager` over a `GoalGraph`, a `Deliberator`, uniform environment/runtime
contracts, evidence-backed competence, a verification engine, and the M8 learning-signal loop
(`ReflectionEngine`, `MemoryRuntime`, `CompetenceModel`, `RecoveryEngine`). What M8 still cannot do
is notice that the *same* verified experience has recurred, lift a specific lesson into a reusable
principle, age stale knowledge, track a deadline, or make progress once the foreground is idle.

M9 closes those four gaps with four new kernel-event-driven subsystems that **wire, wrap, and
extend** existing code rather than rewrite it: a Learning_Engine (FAS Ch 15), a Temporal_Reasoner
family (Ch 9.22, Ch 49), a Long_Horizon_Planner (Ch 42), and a Background_Runtime (Ch 43). Every
subsystem communicates only through kernel-published events (Ch 52); subsystems never call one
another directly, learning never imports memory or competence internals, and background imports only
events and contracts. Like M8 Reflection, learning never writes memory directly — it proposes
procedural writes only through `memory.candidate` events, keeping the Memory_Runtime the single
decision authority. All new modules carry `"""Ch NN — ..."""` docstrings, contain no hardcoded
application or site names or URLs (Axiom 15), and run deterministically under `FRIDAY_DRY_RUN=1` so
the existing test suite stays green.

These requirements are derived from the approved M9 design document and are traceable to its nine
components, its M9 Gate, and its ten correctness properties. A property-to-requirement mapping is
provided at the end of this document.

## Glossary

- **Kernel**: The M1 `CognitiveKernel`, owning the event bus, clock, append-only event store, and
  checkpoint/restore.
- **Kernel_Event**: A dot-namespaced `Event` published on and delivered through the Kernel event bus,
  carrying `logical_time` (Lamport tick) and `wall_time` (epoch seconds at emission).
- **Kernel_Clock**: The logical and wall clock carried on every `Event` (`logical_time` +
  `wall_time`); M9 reads this clock and never constructs its own.
- **Learning_Engine**: The kernel-attached subsystem (`friday/learning/engine.py`, `LearningEngine`)
  that orchestrates the discover → generalize → validate pipeline over M8 events and proposes
  procedural-memory writes only through `memory.candidate` events.
- **Pattern_Discovery**: The component (`friday/learning/patterns.py`, `PatternDiscovery`) that
  detects a Discovered_Pattern from repeated Verified_Experience.
- **Generalizer**: The component (`friday/learning/generalization.py`, `Generalizer`) that lifts a
  Discovered_Pattern into a transferable Principle.
- **Learning_Validator**: The component (`friday/learning/validation.py`, `LearningValidator`) that
  promotes a Principle only after verified, measurable improvement, and supplies the unlearning
  predicate.
- **Verified_Experience**: A `VerifiedExperience` record consumed by learning, carrying `goal_id`,
  `capability`, `environment`, `outcome_signature`, `prediction_error`, `verified`,
  `competence_delta`, `logical_time`, and `wall_time`; only records whose `verified` field is `True`
  may enter the learning pipeline.
- **Discovered_Pattern**: A `DiscoveredPattern` backed by repeated Verified_Experience sharing an
  outcome signature, whose `support` is at least `min_repetitions`.
- **Outcome_Signature**: The stable key `(capability, environment, outcome)` used to group repeated
  Verified_Experience for pattern discovery.
- **Min_Repetitions**: The configurable threshold (default 3) of verified repetitions required before
  a Discovered_Pattern is emitted for an Outcome_Signature.
- **Principle**: A `Principle` — a generalized, transferable learning lifted from one or more
  patterns, carrying `id`, `statement` (no literal app/site names), `applicability`,
  `source_signatures`, `support`, and `confidence` clamped to `[0, 1]`.
- **Validation_Result**: A `ValidationResult` with status `VALIDATED` or `REJECTED`, the signed
  `improvement` delta, and a reason.
- **Min_Improvement**: The configurable minimum improvement delta (default 0.05) required to promote
  a Principle.
- **Retire_Floor**: The confidence threshold below which a previously validated Principle is retired
  through unlearning.
- **Learning_Step**: A `LearningStep` audit record describing what one `ingest` did (optional
  discovered pattern, generalized principle, and validation result).
- **Competence_Key**: The `(capability, environment)` tuple keying competence evidence.
- **Temporal_Reasoner**: The component (`friday/temporal/clock.py`, `TemporalReasoner`) that computes
  freshness, staleness, and time-remaining over the Kernel_Clock.
- **Deadline_Tracker**: The component (`friday/temporal/deadlines.py`, `DeadlineTracker`) that tracks
  goal deadlines and emits approaching/missed events.
- **Knowledge_Aging**: The component (`friday/temporal/aging.py`, `KnowledgeAging`) that decays
  knowledge freshness over time and flags stale items, reusing the Competence_Model half-life decay
  precedent `0.5 ** (elapsed / half_life)`.
- **Deadline_Status**: A `DeadlineStatus` classifying a tracked goal as `ON_TRACK`, `APPROACHING`, or
  `MISSED` at a given wall time, with `remaining_seconds` and `deadline_wall`.
- **Approach_Fraction**: The configurable fraction (default 0.2) of the total deadline window at or
  below which remaining time is classified `APPROACHING`.
- **Aging_Item**: An `AgingItem` (`key`, `observed_at`, `freshness`) evaluated by Knowledge_Aging.
- **Stale_Threshold**: The freshness value below which an Aging_Item is flagged stale and a candidate
  for refresh.
- **Long_Horizon_Planner**: The kernel-attached subsystem (`friday/horizon/planner.py`,
  `LongHorizonPlanner`) that owns the Ch 42 planning hierarchy, evolves roadmaps, gates milestones on
  verification points, and persists context across sessions.
- **Horizon_Level**: One of `VISION`, `MISSION`, `PROJECT`, `MILESTONE`, or `GOAL` in the Ch 42
  planning hierarchy.
- **Project**: A `Project` (`id`, immutable `vision`, ordered `milestones`) registered with the
  Long_Horizon_Planner.
- **Milestone**: A `Milestone` (`id`, `text`, `goal_ids`, `prerequisites`, `reached`) treated as a
  verification point within a Project's roadmap.
- **Roadmap_Revision**: A `RoadmapRevision` (`add`, `remove`) applied to evolve a Project's roadmap
  without changing its immutable vision.
- **Verification_Point**: A verification signal (`verification.completed` / `goal.state_changed`)
  that must pass before a Milestone is marked reached.
- **Goal**: The M3 `Goal` with an immutable outcome (Axiom 1), a `GoalState`, and
  `to_dict`/`from_dict` serialization reused for cross-session survival.
- **Background_Runtime**: The subsystem (`friday/background/runtime.py`, `BackgroundRuntime`)
  implementing the Runtime_Contract that performs opportunistic background cognition when the
  foreground is idle.
- **Runtime_Contract**: The M1 `RuntimeContract` (`friday/kernel/contracts/runtime.py`) that the
  Background_Runtime implements so the Kernel can `register_runtime` and `tick` it.
- **Foreground_Activity**: A foreground-progress Kernel_Event (for example `goal.state_changed`,
  `action.executed`) whose arrival resets the Background_Runtime idle counter.
- **Idle_Ticks_Required**: The configurable number of consecutive idle ticks (default 5) required
  before the Background_Runtime performs a work unit.
- **Max_Work_Per_Tick**: The configurable upper bound (default 1) on background work units performed
  in a single tick.
- **Background_Work_Unit**: A bounded, DRY_RUN-safe opportunistic operation performed by the
  Background_Runtime (memory consolidation, competence-decay check, freshness check, or long-horizon
  advancement).
- **Reflection_Engine**: The M8 `ReflectionEngine` producing `reflection.completed` and
  `memory.candidate` events consumed by learning.
- **Memory_Runtime**: The M8 `MemoryRuntime`, the single decider that accepts or rejects
  `memory.candidate` events and emits `memory.integrated` / `memory.rejected`.
- **Competence_Model**: The M8 `CompetenceModel` producing `competence.updated` events consumed by
  learning and knowledge aging.
- **M9_Gate**: The end-to-end acceptance oracle demonstrating that a multi-session long-horizon goal
  advances across a session boundary while the foreground is idle, reconstructable from the event log.
- **DRY_RUN**: The `FRIDAY_DRY_RUN=1` execution mode in which no real filesystem, LLM, or OS surface
  is touched.

## Requirements

### Requirement 1: Learning Engine

**User Story:** As a FRIDAY cognitive architect, I want a Learning_Engine that discovers patterns from
repeated verified experience, generalizes them into transferable principles, and promotes learnings
only after validated improvement, so that the operator improves durably from evidence while memory
integration stays under a single decision authority.

#### Acceptance Criteria

1. WHEN the Learning_Engine ingests an experience whose `verified` field is not `True`, THEN THE
   Learning_Engine SHALL exclude that experience from pattern discovery, generalization, and
   promotion.
2. WHEN the Pattern_Discovery has observed fewer than Min_Repetitions Verified_Experience records for
   an Outcome_Signature, THE Pattern_Discovery SHALL return no Discovered_Pattern for that
   Outcome_Signature.
3. WHEN the count of Verified_Experience records sharing an Outcome_Signature reaches Min_Repetitions,
   THE Pattern_Discovery SHALL return a Discovered_Pattern whose `support` equals the observed
   verified repetition count.
4. WHEN the Generalizer generalizes a Discovered_Pattern, THE Generalizer SHALL produce a Principle
   whose `applicability` is broader than the source pattern context, SHALL preserve the source
   pattern signatures and aggregate support as provenance, and SHALL express applicability by
   capability and environment class without any literal application or site name.
5. WHEN the Generalizer merges additional supporting evidence into a Principle, THE Generalizer SHALL
   derive the Principle confidence monotonically non-decreasing in accumulated support.
6. THE Learning_Validator SHALL return a Validation_Result of `VALIDATED` only WHEN the triggering
   experience is verified AND the observed value minus the baseline value is greater than or equal to
   Min_Improvement, and SHALL otherwise return `REJECTED`.
7. WHEN the Learning_Validator returns `VALIDATED` for a Principle, THE Learning_Engine SHALL emit a
   `learning.validated` Kernel_Event and a `memory.candidate` Kernel_Event with `kind` equal to
   `pattern` and `verified` equal to `True`.
8. WHEN the Learning_Validator returns `REJECTED` for a Principle, THE Learning_Engine SHALL emit a
   `learning.rejected` Kernel_Event and SHALL emit no procedural `memory.candidate` for that Principle.
9. THE Learning_Engine SHALL propose procedural-memory writes only through `memory.candidate`
   Kernel_Events and SHALL perform no direct write to any long-term memory store.
10. WHEN the confidence of a validated Principle decays below the Retire_Floor, THE Learning_Engine
    SHALL emit exactly one `learning.unlearned` Kernel_Event for that Principle and SHALL no longer
    propose that Principle for procedural promotion.
11. WHEN the Learning_Engine reports improvement for a Competence_Key derived from `competence.updated`
    evidence, THE Learning_Engine SHALL report `0.0` for a Competence_Key never observed and SHALL
    otherwise report the signed difference between the latest and first observed confidence for that
    Competence_Key.
12. WHEN the Learning_Engine attaches to the Kernel, THE Learning_Engine SHALL subscribe to
    `reflection.completed`, `memory.integrated`, and `competence.updated` Kernel_Events.
13. IF an incoming Kernel_Event lacks a field the Learning_Engine requires, THEN THE Learning_Engine
    SHALL skip processing for that event and SHALL NOT raise into the Kernel tick loop.

### Requirement 2: Temporal Reasoning

**User Story:** As a FRIDAY cognitive architect, I want a Temporal_Reasoner, Deadline_Tracker, and
Knowledge_Aging that reason about deadlines and knowledge freshness using the kernel clock, so that
the operator ages stale knowledge and reacts to time without inventing a private clock.

#### Acceptance Criteria

1. THE Temporal_Reasoner, Deadline_Tracker, and Knowledge_Aging SHALL read time only from the
   `logical_time` and `wall_time` carried on Kernel_Events and SHALL NOT construct a new clock.
2. FOR ANY fixed observation time and half-life, WHILE the current time increases, THE Knowledge_Aging
   SHALL compute a freshness value that is monotonically non-increasing, remains within the closed
   interval `[0, 1]`, and equals `1.0` when the current time equals the observation time.
3. WHEN Knowledge_Aging evaluates a set of Aging_Items at a given time, THE Knowledge_Aging SHALL
   return every Aging_Item whose freshness is below the Stale_Threshold as a candidate for refresh.
4. WHEN the Deadline_Tracker evaluates a tracked goal at a given wall time, THE Deadline_Tracker SHALL
   classify the goal `MISSED` if the wall time is greater than the deadline wall time and the goal is
   non-terminal, `APPROACHING` if the remaining time is less than or equal to Approach_Fraction times
   the total window and the goal is not missed, and `ON_TRACK` otherwise.
5. WHEN the Deadline_Tracker classifies a tracked goal as `APPROACHING`, THE Deadline_Tracker SHALL
   publish a `temporal.deadline_approaching` Kernel_Event, and WHEN the Deadline_Tracker classifies a
   tracked goal as `MISSED`, THE Deadline_Tracker SHALL publish a `temporal.deadline_missed`
   Kernel_Event.
6. WHEN the Deadline_Tracker attaches to the Kernel, THE Deadline_Tracker SHALL subscribe to
   `goal.created` and `goal.state_changed` Kernel_Events and SHALL read each deadline from the goal
   `constraints` deadline field.
7. IF a goal carries no deadline constraint, THEN THE Deadline_Tracker SHALL NOT track that goal.
8. IF a goal deadline window is non-positive, THEN THE Deadline_Tracker SHALL evaluate the goal
   without dividing by zero and SHALL classify it `MISSED` only when the current wall time is greater
   than the deadline wall time.

### Requirement 3: Long-Horizon Planning

**User Story:** As a FRIDAY cognitive architect, I want a Long_Horizon_Planner that owns the
Vision-to-Goal hierarchy, evolves roadmaps, gates milestones on verification, and persists context
across sessions, so that multi-session goals survive restarts and progress toward an immutable vision.

#### Acceptance Criteria

1. THE Long_Horizon_Planner SHALL maintain the planning hierarchy of Vision, Mission, Project,
   Milestone, and Goal.
2. WHEN the Long_Horizon_Planner applies a Roadmap_Revision to a Project, THE Long_Horizon_Planner
   SHALL evolve the Project milestone roadmap while keeping the Project vision unchanged.
3. WHEN the Long_Horizon_Planner is asked to advance a Milestone, THE Long_Horizon_Planner SHALL mark
   the Milestone reached only after its Verification_Point passes and SHALL publish a
   `horizon.milestone_reached` Kernel_Event and a `horizon.project_advanced` Kernel_Event.
4. THE Long_Horizon_Planner SHALL treat the immutable Goal outcome as never mutated and SHALL evolve
   only roadmap structure and milestone or goal state.
5. WHEN the Long_Horizon_Planner checkpoints, THE Long_Horizon_Planner SHALL produce a
   JSON-serializable roadmap state containing projects, milestones, and goal ids.
6. WHEN the Kernel is restored and the Long_Horizon_Planner restores from a checkpoint, THE
   Long_Horizon_Planner SHALL reproduce the identical set of goal ids, goal states, and reached
   milestones present at checkpoint time.
7. WHEN the Long_Horizon_Planner attaches to the Kernel, THE Long_Horizon_Planner SHALL subscribe to
   `goal.created`, `goal.state_changed`, and `kernel.checkpoint` Kernel_Events.
8. IF the Long_Horizon_Planner restores from partial or truncated state, THEN THE Long_Horizon_Planner
   SHALL default missing fields to empty roadmaps and SHALL NOT invent goal ids or milestones.

### Requirement 4: Background Cognition

**User Story:** As a FRIDAY cognitive architect, I want a Background_Runtime that performs opportunistic
work only when the foreground is idle and always yields to foreground activity, so that the operator
makes progress while the user is away without ever competing with foreground work.

#### Acceptance Criteria

1. THE Background_Runtime SHALL implement the Runtime_Contract members so that the Kernel can register
   it via `register_runtime`.
2. WHEN the Background_Runtime is ticked and Foreground_Activity has occurred within the preceding
   Idle_Ticks_Required ticks, THE Background_Runtime SHALL perform no Background_Work_Unit on that
   tick.
3. WHEN the Background_Runtime is ticked and no Foreground_Activity has occurred within the preceding
   Idle_Ticks_Required ticks, THE Background_Runtime SHALL perform at most Max_Work_Per_Tick
   Background_Work_Units.
4. WHEN the Background_Runtime receives a Foreground_Activity Kernel_Event, THE Background_Runtime
   SHALL reset its idle counter so that foreground work preempts background work immediately.
5. WHEN the Background_Runtime is initialized with the Kernel, THE Background_Runtime SHALL subscribe
   to foreground-activity Kernel_Events rather than busy-polling.
6. WHEN the Background_Runtime performs a Background_Work_Unit, THE Background_Runtime SHALL publish a
   `background.work_done` Kernel_Event describing the unit performed and SHALL propose any memory
   write only through a `memory.candidate` Kernel_Event.
7. IF a Background_Work_Unit raises an exception, THEN THE Background_Runtime SHALL contain the
   exception, SHALL report a degraded reason through `health`, and SHALL NOT raise into the Kernel
   tick loop.
8. WHILE running under DRY_RUN, THE Background_Runtime SHALL perform bounded no-op-safe work and SHALL
   continue to publish auditable Kernel_Events.

### Requirement 5: Kernel-Event Isolation

**User Story:** As a FRIDAY platform maintainer, I want the M9 subsystems to communicate only through
kernel events and to wrap existing modules rather than reach into them, so that the architecture stays
decoupled, portable, and regression-safe.

#### Acceptance Criteria

1. THE Learning_Engine, Temporal_Reasoner family, Long_Horizon_Planner, and Background_Runtime SHALL
   exchange information only through Kernel_Events and SHALL NOT call one another directly.
2. THE Learning_Engine modules SHALL NOT import `friday.memory.controller`, `friday.memory.runtime`,
   or any `friday.competence` module, and SHALL NOT reference `FridayMemory` or `MemoryStore`.
3. THE Background_Runtime module SHALL import only `friday.events`, `friday.kernel.contracts`, and
   standard-library modules.
4. THE M9 subsystem modules SHALL contain no hardcoded application names, site names, or URLs.
5. THE Long_Horizon_Planner SHALL reuse the existing M3 `Goal` serialization and the Kernel
   checkpoint and restore operations for cross-session persistence without rewriting them.

### Requirement 6: The M9 Gate

**User Story:** As a FRIDAY cognitive architect, I want a multi-session long-horizon goal to advance
while the user is away, provable through the kernel event log, so that I can verify checkpoint and
restore across a session boundary, background advancement while idle, and deterministic reconstruction.

#### Acceptance Criteria

1. WHEN a Project with a multi-milestone roadmap is checkpointed and the Kernel is subsequently
   restored, THE Long_Horizon_Planner SHALL reproduce the identical goal ids, goal states, and reached
   milestones across the session boundary.
2. WHILE the foreground is idle after restore, WHEN the Background_Runtime is ticked, THE
   Background_Runtime SHALL advance the suspended long-horizon goal and SHALL publish a
   `horizon.project_advanced` Kernel_Event and a `background.work_done` Kernel_Event.
3. WHEN a Foreground_Activity Kernel_Event is injected during background advancement, THE
   Background_Runtime SHALL yield immediately and perform no further Background_Work_Unit until the
   idle condition is met again.
4. WHILE running under DRY_RUN, WHEN the same ordered event log is replayed through the M9 subsystems,
   THE M9 subsystems SHALL produce identical emitted Kernel_Event types and payloads modulo event id
   and wall time and identical internal state.
5. WHEN the M9_Gate scenario runs to completion, THE advancement of the long-horizon goal SHALL be
   reconstructable from the durable Kernel event log.

### Requirement 7: Non-Regression and Module Hygiene

**User Story:** As a FRIDAY platform maintainer, I want M9 to preserve all existing tests and follow
module conventions, so that the new subsystems integrate without breaking the substrate built in
M1–M8.

#### Acceptance Criteria

1. WHILE running the full FRIDAY test suite, THE M9 subsystems SHALL keep the existing test count of at
   least 890 tests passing.
2. WHILE any M9 test module runs, THE M9 test suite SHALL execute under DRY_RUN so that no real
   filesystem, LLM, or OS surface is touched.
3. THE M9 subsystem modules SHALL each carry a module docstring in the `"""Ch NN — ..."""` form.

## Property-to-Requirement Mapping

The following mapping finalizes the placeholder `- Validates: _[placeholder]_` lines in the design
document's Correctness Properties section.

- **Property 1** (Learn only from verified experience) → **Requirement 1.1, 1.9**
- **Property 2** (Patterns require repetition) → **Requirement 1.2, 1.3**
- **Property 3** (Validated before promotion) → **Requirement 1.6, 1.7, 1.8**
- **Property 4** (Temporal decay is monotonic) → **Requirement 2.2**
- **Property 5** (Deadline detection) → **Requirement 2.4, 2.5**
- **Property 6** (Background yields to foreground) → **Requirement 4.2, 4.3, 4.4, 6.3**
- **Property 7** (Long-horizon goal survives restart) → **Requirement 3.5, 3.6, 6.1**
- **Property 8** (Determinism) → **Requirement 6.4, 6.5**
- **Property 9** (Unlearning retires low-confidence principles) → **Requirement 1.10**
- **Property 10** (Measurable improvement is real) → **Requirement 1.11**
