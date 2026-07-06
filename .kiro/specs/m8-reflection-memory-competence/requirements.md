# Requirements Document

## Introduction

Milestone 8 (M8) closes the FRIDAY General Computer Operator learning loop. Milestones 1–7 built a
persistent, event-driven cognitive substrate (kernel, world model, goal manager, deliberator that
emits predicted outcomes, environment/capability runtimes, verification engine, exploration engine)
with 871 passing tests, but FRIDAY still cannot compare what it predicted against what actually
happened, its 7-module memory system is orphaned, competence is never aggregated by context or
decayed, and recovery is a single per-requirement diagnoser rather than a full loop.

M8 delivers four kernel-event-driven subsystems that **wire, wrap, and extend** existing code
without rewrites: a Reflection Engine (FAS Ch 13), a Memory Runtime (Ch 14), a Competence Model
(Ch 28), and a Recovery Engine (Ch 34). Every subsystem communicates only through kernel-published
events (Ch 52); subsystems never call each other directly. All new modules carry `"""Ch NN — ..."""`
docstrings and run deterministically under `FRIDAY_DRY_RUN=1` so the existing test suite stays green.

These requirements are derived from the approved M8 design document and are traceable to its four
components, its M8 Gate, and its eight correctness properties. A property-to-requirement mapping is
provided at the end of this document.

## Glossary

- **Reflection_Engine**: The subsystem (`friday/cognition/reflection.py`, `ReflectionEngine`) that
  compares predictions to observed reality, answers the 5 Questions across multiple scales,
  calibrates confidence, and emits `memory.candidate` events. It never writes long-term memory.
- **Memory_Runtime**: The subsystem (`friday/memory/runtime.py`, `MemoryRuntime`) that implements
  the `RuntimeContract`, wraps the existing `FridayMemory`, and decides accept/reject/merge/forget
  for memory candidates.
- **Competence_Model**: The subsystem (`friday/competence/model.py`, `CompetenceModel`) that
  aggregates evidence-backed competence keyed by `(capability, environment)`, decays it, gates
  risky actions, and maintains a competence graph.
- **Recovery_Engine**: The subsystem (`friday/recovery/engine.py`, `RecoveryEngine`) that wraps the
  existing `RepairDiagnoser` into the full Ch 34.4 failure→recovery loop.
- **Kernel**: The M1 `CognitiveKernel`, owning the event bus, clock, and append-only event store.
- **Kernel_Event**: A dot-namespaced `Event` published on and delivered through the Kernel event bus.
- **Predicted_Outcome**: The M4 `PredictedOutcome` (`expected_beliefs`, `confidence`, `reversible`)
  carried by an action before it is taken.
- **Prediction_Error**: A score in `[0, 1]` measuring the divergence between a Predicted_Outcome's
  expected beliefs and the observed beliefs; `0` means an exact match.
- **Five_Questions**: The FAS Ch 13.5 reflection questions (reality changed as expected, progress
  increased, assumptions wrong, new knowledge gained, behavior should change).
- **Reflection_Scale**: One of the four scales at which reflection runs — micro (per action), task,
  goal, session (Ch 13.13).
- **Memory_Candidate**: A `memory.candidate` Kernel_Event proposing a learning to be integrated,
  carrying at minimum `verified`, `kind`, `content`, `context_hash`, `competence_delta`, and
  `source_goal_id` fields.
- **Verified_Experience**: A Memory_Candidate whose `verified` field is `True`, indicating the
  triggering experience was verification-backed.
- **Memory_Decision**: One of `ACCEPT`, `REJECT`, `MERGE`, `FORGET` produced by the Memory_Runtime
  for a Memory_Candidate.
- **Contradicting_Observation**: A current confident belief in the World Model that conflicts with a
  Memory_Candidate's content.
- **FridayMemory**: The existing 7-module memory controller (`friday/memory/controller.py`) wrapped
  by the Memory_Runtime.
- **CompetenceRecord**: The existing evidence-backed, Laplace-smoothed record
  (`friday/kernel/contracts/capability.py`) with `confidence` clamped to `[0, 1]`.
- **Competence_Key**: The `(capability, environment)` tuple keying a competence node.
- **Risk_Level**: One of `observe`, `reversible`, `modify`, `irreversible`, each mapped to a
  minimum confidence gate.
- **Failure_Class**: A member of the Ch 34.3 taxonomy (`transient`, `precondition`, `capability`,
  `environmental`, `blocked`, `irrecoverable`, `unknown`).
- **Recovery_Level**: A member of the Ch 34.5 escalation ladder (`micro`, `local`, `environmental`,
  `strategic`, `human`, `architectural`).
- **Rollback_Kind**: A member of the Ch 34.9 Action Rollback Contract set (`undo`, `rollback`,
  `compensation`, `none`).
- **Recovery_Plan**: The frozen recovery decision produced by the Recovery_Engine, preserving the
  original goal id and proposing an alternative strategy.
- **Irreversible_Action**: An action whose Predicted_Outcome has `reversible` false; recovering it
  requires higher confidence.
- **M8_Gate**: The end-to-end acceptance oracle demonstrating the closed learning loop through the
  Kernel event log.
- **DRY_RUN**: The `FRIDAY_DRY_RUN=1` execution mode in which no real filesystem, LLM, or OS surface
  is touched.

## Requirements

### Requirement 1: Reflection Engine

**User Story:** As a FRIDAY cognitive architect, I want a Reflection_Engine that compares predictions
to reality and proposes learnings without writing memory, so that the operator learns from prediction
errors while keeping memory integration under a single decision authority.

#### Acceptance Criteria

1. THE Reflection_Engine SHALL emit learnings only as `memory.candidate` Kernel_Events and SHALL
   perform no direct write to FridayMemory or any long-term memory store.
2. WHEN a `verification.completed` Kernel_Event carries a Predicted_Outcome and observed beliefs,
   THE Reflection_Engine SHALL compute a Prediction_Error in the closed interval `[0, 1]`.
3. WHEN the observed beliefs exactly match the Predicted_Outcome expected beliefs, THE
   Reflection_Engine SHALL compute a Prediction_Error equal to `0`.
4. WHEN a non-empty Predicted_Outcome has no overlap with the observed beliefs, THE
   Reflection_Engine SHALL compute a Prediction_Error equal to `1`.
5. WHEN the Reflection_Engine reflects on a prediction/observation pair, THE Reflection_Engine SHALL
   answer the Five_Questions and record them in an immutable ReflectionRecord.
6. THE Reflection_Engine SHALL support reflection at each Reflection_Scale of micro, task, goal, and
   session.
7. WHEN the Reflection_Engine attaches to the Kernel, THE Reflection_Engine SHALL subscribe to
   `action.executed`, `verification.completed`, and `goal.state_changed` Kernel_Events.
8. WHEN the triggering experience is verification-backed, THE Reflection_Engine SHALL set the
   `verified` field of the emitted Memory_Candidate to `True`, and WHEN the triggering experience is
   not verification-backed, THE Reflection_Engine SHALL set the `verified` field to `False`.
9. WHEN the Reflection_Engine calibrates confidence, THE Reflection_Engine SHALL compute a
   calibration error equal to the mean absolute difference between predicted confidence and observed
   accuracy in the closed interval `[0, 1]`.
10. IF an incoming Kernel_Event lacks `goal_id`, prediction, or observed beliefs, THEN THE
    Reflection_Engine SHALL skip reflection for that event and SHALL NOT raise into the Kernel tick
    loop.

### Requirement 2: Memory Wiring

**User Story:** As a FRIDAY cognitive architect, I want a Memory_Runtime that wraps the existing
FridayMemory behind the kernel RuntimeContract and decides what enters long-term memory, so that only
verified experience is retained and memory never overrides reality.

#### Acceptance Criteria

1. WHEN the Memory_Runtime receives a Memory_Candidate whose `verified` field is not `True`, THEN THE
   Memory_Runtime SHALL return a Memory_Decision of `REJECT` and SHALL perform no storage call to
   FridayMemory.
2. WHEN the Memory_Runtime receives a Memory_Candidate that conflicts with a Contradicting_Observation,
   THEN THE Memory_Runtime SHALL return a Memory_Decision of `REJECT` regardless of the candidate's
   `verified` field.
3. WHEN the Memory_Runtime receives a Verified_Experience that does not conflict with any
   Contradicting_Observation, THE Memory_Runtime SHALL return a Memory_Decision of `ACCEPT` or
   `MERGE` and SHALL delegate storage to the existing FridayMemory.
4. THE Memory_Runtime SHALL implement the RuntimeContract members so that the Kernel can register it
   via `register_runtime`.
5. WHEN the Memory_Runtime initializes with the Kernel, THE Memory_Runtime SHALL subscribe to
   `memory.candidate` Kernel_Events.
6. WHEN the Memory_Runtime completes a Memory_Decision, THE Memory_Runtime SHALL publish a
   `memory.integrated` Kernel_Event for accepted or merged candidates and a `memory.rejected`
   Kernel_Event for rejected candidates.
7. THE Memory_Runtime SHALL delegate all storage to the existing FridayMemory `record_turn`,
   `record_pattern`, and `remember_fact` operations and SHALL NOT reimplement the memory tiers.
8. WHILE the Kernel is ticking, THE Memory_Runtime SHALL apply forgetting and decay on the configured
   decay interval without modifying World Model observations.
9. IF FridayMemory construction or backing storage is unavailable under DRY_RUN, THEN THE
   Memory_Runtime SHALL degrade to in-memory no-op storage, SHALL report a `degraded` status through
   `health`, and SHALL continue publishing Memory_Decisions.

### Requirement 3: Competence Model

**User Story:** As a FRIDAY cognitive architect, I want a Competence_Model that aggregates
evidence-backed competence per capability and environment, so that risky actions are gated on
demonstrated ability and stale competence decays rather than being fabricated.

#### Acceptance Criteria

1. FOR EACH Competence_Key and any sequence of recorded outcomes, THE Competence_Model SHALL report a
   confidence in the closed interval `[0, 1]` equal to the Laplace-smoothed CompetenceRecord
   confidence computed purely from the recorded successes and attempts.
2. WHILE no new outcome is recorded for a Competence_Key between two ticks, THE Competence_Model SHALL
   keep the effective confidence monotonically non-increasing over time and SHALL NOT increase
   confidence or add successes through decay.
3. WHEN the Competence_Model receives a `verification.completed` Kernel_Event, THE Competence_Model
   SHALL fold the verified outcome into the CompetenceRecord for its `(capability, environment)`
   Competence_Key and SHALL publish a `competence.updated` Kernel_Event.
4. THE Competence_Model SHALL derive every competence value solely from recorded attempts and
   successes and SHALL NOT derive any competence value from an LLM or any non-evidence source.
5. WHEN gating an action of a given Risk_Level, THE Competence_Model SHALL permit the action only if
   the Competence_Key confidence is greater than or equal to the confidence gate for that Risk_Level.
6. FOR ANY two Risk_Levels where the first is less risky than the second, THE Competence_Model SHALL
   assign a confidence gate to the first that is less than or equal to the confidence gate assigned to
   the second.
7. WHEN the Competence_Model attaches to the Kernel, THE Competence_Model SHALL subscribe to
   `verification.completed` Kernel_Events.
8. THE Competence_Model SHALL maintain a competence graph whose nodes are Competence_Keys and SHALL
   expose a read-only view of that graph.

### Requirement 4: Recovery Engine

**User Story:** As a FRIDAY cognitive architect, I want a Recovery_Engine that turns a failure into an
alternative strategy while preserving the goal, so that the operator recovers from failures safely and
escalates irreversible actions it is not competent to attempt.

#### Acceptance Criteria

1. WHEN the Recovery_Engine produces a Recovery_Plan for a failure on a goal, THE Recovery_Engine
   SHALL set the Recovery_Plan goal id equal to the input goal id and SHALL carry that same goal id on
   the emitted `recovery.proposed` Kernel_Event.
2. IF a failure is on an Irreversible_Action and the available competence is less than the irreversible
   confidence floor, THEN THE Recovery_Engine SHALL choose no automatic alternative and SHALL escalate
   the Recovery_Level to `human` or higher.
3. THE Recovery_Engine SHALL require a confidence to attempt recovery on an Irreversible_Action that is
   greater than or equal to the confidence required to attempt recovery on a reversible action.
4. WHEN the Recovery_Engine diagnoses a failure, THE Recovery_Engine SHALL delegate diagnosis to the
   existing RepairDiagnoser and SHALL map the resulting cause into a Failure_Class of the Ch 34.3
   taxonomy.
5. WHEN the Recovery_Engine builds a Recovery_Plan, THE Recovery_Engine SHALL generate recovery
   alternatives ordered by estimated utility and SHALL assign each alternative a Recovery_Level and a
   Rollback_Kind.
6. WHEN the Recovery_Engine attaches to the Kernel, THE Recovery_Engine SHALL subscribe to
   `verification.completed` Kernel_Events and SHALL publish a `recovery.proposed` Kernel_Event for the
   Deliberator to re-enter.

### Requirement 5: Kernel-Event Isolation

**User Story:** As a FRIDAY platform maintainer, I want the M8 subsystems to communicate only through
kernel events and to wrap existing modules rather than rewrite them, so that the architecture stays
decoupled, portable, and regression-safe.

#### Acceptance Criteria

1. THE Reflection_Engine, Memory_Runtime, Competence_Model, and Recovery_Engine SHALL exchange
   information only through Kernel_Events and SHALL NOT call one another directly.
2. THE Reflection_Engine module SHALL NOT import the memory, competence, or recovery subsystem
   modules.
3. THE Competence_Model and Recovery_Engine modules SHALL NOT import the FridayMemory controller
   module.
4. THE M8 subsystem modules SHALL contain no hardcoded application names, site names, or URLs.
5. THE Memory_Runtime SHALL wrap the existing 7 FridayMemory modules, THE Competence_Model SHALL wrap
   the existing CompetenceRecord, and THE Recovery_Engine SHALL wrap the existing RepairDiagnoser,
   without rewriting them.

### Requirement 6: The M8 Gate

**User Story:** As a FRIDAY cognitive architect, I want a closed learning loop provable through the
kernel event log, so that I can verify a prediction mismatch leads to reflection, memory integration,
competence update, and measurable improvement on a repeated task.

#### Acceptance Criteria

1. WHEN an `action.executed` carrying a Predicted_Outcome is followed by a `verification.completed`
   whose observed beliefs differ from the prediction, THE Reflection_Engine SHALL compute a
   Prediction_Error greater than `0` and emit a Verified_Experience Memory_Candidate.
2. WHEN the M8_Gate scenario runs, THE Kernel event log SHALL contain, in causal order,
   `action.executed`, then `verification.completed`, then `memory.candidate`, then
   `memory.integrated`, and SHALL contain `competence.updated` following `verification.completed`.
3. WHEN a task for a `(capability, environment)` Competence_Key succeeds after an earlier failure for
   the same Competence_Key, THE Competence_Model SHALL report a confidence strictly greater than the
   confidence recorded after the earlier failure.
4. WHEN the M8_Gate scenario runs to completion, THE Memory_Runtime SHALL make the wrapped FridayMemory
   return a non-empty learned context for the repeated task where the context was previously empty.
5. WHILE running under DRY_RUN, WHEN the M8_Gate scenario is executed twice with identical inputs, THE
   M8_Gate SHALL produce an identical ordered sequence of M8 Kernel_Event types.

### Requirement 7: Non-Regression and Module Hygiene

**User Story:** As a FRIDAY platform maintainer, I want M8 to preserve all existing tests and follow
module conventions, so that the new subsystems integrate without breaking the substrate built in
M1–M7.

#### Acceptance Criteria

1. WHILE running the full FRIDAY test suite, THE M8 subsystems SHALL keep the existing test count of at
   least 871 tests passing.
2. WHILE any M8 test module runs, THE M8 test suite SHALL execute under DRY_RUN so that no real
   filesystem, LLM, or OS surface is touched.
3. THE M8 subsystem modules SHALL each carry a module docstring in the `"""Ch NN — ..."""` form.

## Property-to-Requirement Mapping

The following mapping finalizes the placeholder `**Validates: Requirements X.Y**` lines in the design
document's Correctness Properties section.

- **Property 1** (Reflection never writes long-term memory directly) → **Requirement 1.1**
- **Property 2** (Memory candidates integrated only from verified experience) → **Requirement 2.1**
- **Property 3** (Competence is in [0, 1] and evidence-derived) → **Requirement 3.1, 3.4**
- **Property 4** (Competence decay is monotonic non-increasing without new evidence) → **Requirement 3.2**
- **Property 5** (Recovery preserves the goal id) → **Requirement 4.1**
- **Property 6** (Irreversible-action confidence gate is monotonic) → **Requirement 3.6, 4.2, 4.3**
- **Property 7** (Memory never overrides a contradicting observation) → **Requirement 2.2**
- **Property 8** (Prediction error is a bounded score) → **Requirement 1.2, 1.3, 1.4**
