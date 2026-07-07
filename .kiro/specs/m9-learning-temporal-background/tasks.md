# Implementation Plan: M9 — Learning, Temporal Reasoning, Long-Horizon Planning & Background Cognition

## Overview

This plan converts the approved M9 design into a series of incremental, code-focused steps for a
code-generation LLM. M9 adds four kernel-event-driven subsystems onto the existing M1–M8 substrate by
**wiring, wrapping, and extending** existing code — never rewriting it: the M8 `ReflectionEngine`
event stream, `friday/memory/procedural.py` (`ProceduralMemory`/`ActionPattern`), the
`friday/competence/model.py` decay precedent, the M3 `friday/goals/goal.py` `Goal.to_dict`/`from_dict`
serialization + `GoalManager`, the kernel `checkpoint()`/`restore()`, and the `RuntimeContract`.

Ordering is dependency-driven and validates functionality early through code:

1. **Learning pure cores first** (`friday/learning/`) — data models
   (`VerifiedExperience`/`DiscoveredPattern`/`Principle`/`ValidationResult`/`LearningStep`) →
   `PatternDiscovery` → `Generalizer` → `LearningValidator`, each directly unit/property testable,
   then the `LearningEngine` that wires them onto the M8 event stream and proposes procedural writes
   **only** via `memory.candidate` events.
2. **Temporal** (`friday/temporal/`) — `TemporalReasoner`, `KnowledgeAging`, `DeadlineTracker`;
   independent of learning and internally parallelizable.
3. **Long-Horizon** (`friday/horizon/`) — data models → `LongHorizonPlanner` with checkpoint/restore
   reusing M3 `Goal` serialization + kernel checkpoint semantics.
4. **Background** (`friday/background/`) — `BackgroundRuntime(RuntimeContract)`, depending on nothing
   but events + contracts; its gate behavior exercises Long-Horizon advancement.
5. **Checkpoints** after each major group (keep ≥ 890 tests green).
6. **Tests** — AST isolation/import-boundary, all 10 Hypothesis property tests, a kernel-event
   integration test, and the M9 Gate multi-session checkpoint→restore→background-advance simulation.
7. **Final regression checkpoint.**

Every pure core (`PatternDiscovery.observe` / `Generalizer.generalize` / `LearningValidator.validate`
/ `LearningEngine.ingest` / `TemporalReasoner.*` / `KnowledgeAging.freshness` /
`DeadlineTracker.evaluate` / `LongHorizonPlanner.checkpoint/restore`) is separated from kernel wiring
so it is directly unit- and property-testable under `FRIDAY_DRY_RUN=1`. `BackgroundRuntime` enforces
foreground preemption (any foreground event resets its idle counter). All new modules carry a
`"""Ch NN — ..."""` docstring, contain no hardcoded app/site names or URLs (Axiom 15), and
communicate only through kernel events (Ch 52); learning never imports `friday.memory.controller`/
`friday.memory.runtime`/`friday.competence.*`, and background imports only `friday.events` +
`friday.kernel.contracts`.

**Language:** Python 3.12 (the project language, used throughout the design). **Test command:**
`python -m pytest tests/friday/ -q`.

## Tasks

- [x] 1. Learning pure cores — `friday/learning/`
  - [x] 1.1 Create the learning data models and package surface
    - Add `friday/learning/models.py` with a `"""Ch 15 — ..."""` module docstring
    - Define frozen `VerifiedExperience` (`goal_id`, `capability`, `environment`,
      `outcome_signature`, `prediction_error`, `verified`, `competence_delta`, `logical_time`,
      `wall_time`)
    - Define frozen `DiscoveredPattern` (`signature`, `capability`, `environment`, `support`,
      `mean_prediction_error`), frozen `Principle` (`id`, `statement`, `applicability`,
      `source_signatures`, `support`, `confidence`) with `__post_init__` clamping `confidence` to
      `[0, 1]`, `ValidationStatus(str, Enum)` (`VALIDATED`/`REJECTED`), frozen `ValidationResult`
      (`status`, `principle_id`, `improvement`, `reason`), and frozen `LearningStep`
      (`discovered`, `generalized`, `validation`)
    - Define `CompetenceKey = Tuple[str, str]`
    - Extend `friday/learning/__init__.py` (currently only a docstring) to export the public surface
    - _Requirements: 1.4, 5.4, 7.3_

  - [x]* 1.2 Write unit tests for the learning data models
    - Assert `Principle.confidence` is clamped to `[0, 1]` and all records are immutable (frozen)
    - Assert `applicability`/`source_signatures` are tuples and carry no literal app/site name
    - Set `os.environ.setdefault("FRIDAY_DRY_RUN", "1")` before importing any `friday` module
    - _Requirements: 1.4, 5.4, 7.2_

  - [x] 1.3 Implement `PatternDiscovery` — `friday/learning/patterns.py`
    - Create `friday/learning/patterns.py` with a `"""Ch 15.5 — ..."""` module docstring
    - Implement `__init__(*, min_repetitions=3)`, `observe(experience) -> Optional[DiscoveredPattern]`,
      and `support(signature) -> int`
    - Bucket experiences by stable `signature = (capability, environment, outcome_signature)`; count
      ONLY records with `verified is True`; return `None` until `support >= min_repetitions`; the
      returned pattern's `support` equals the observed verified repetition count
    - _Requirements: 1.1, 1.2, 1.3_

  - [x]* 1.4 Write property test: patterns require repetition
    - **Property 2: Patterns require repetition**
    - **Validates: Requirements 1.2, 1.3**

  - [x] 1.5 Implement `Generalizer` — `friday/learning/generalization.py`
    - Create `friday/learning/generalization.py` with a `"""Ch 15.6/15.9 — ..."""` module docstring
    - Implement `generalize(pattern) -> Principle` producing an `applicability` broader than the
      source pattern context, preserving `source_signatures` + aggregate `support` as provenance, and
      expressing applicability by capability/environment class with NO literal app/site name
    - Implement `merge(principle, other) -> Principle` folding additional supporting evidence, widening
      applicability, and deriving `confidence` monotonically non-decreasing in accumulated support
    - _Requirements: 1.4, 1.5, 5.4_

  - [x]* 1.6 Write unit tests for `Generalizer`
    - Assert generalized `applicability` is broader than the source context and provenance is preserved
    - Assert `merge` yields confidence monotonically non-decreasing in support and no literal app/site
      name appears in any `statement`/`applicability`
    - _Requirements: 1.4, 1.5, 5.4, 7.2_

  - [x] 1.7 Implement `LearningValidator` — `friday/learning/validation.py`
    - Create `friday/learning/validation.py` with a `"""Ch 15.4/15.19 — ..."""` module docstring
    - Implement `__init__(*, min_improvement=0.05)` and
      `validate(principle, *, baseline, observed, verified) -> ValidationResult` returning `VALIDATED`
      iff `verified is True` AND `observed - baseline >= min_improvement`, else `REJECTED`; the result
      carries the signed `improvement` delta
    - Implement `should_unlearn(principle, current_confidence) -> bool` (the retire-floor unlearning
      predicate) taking a configurable `retire_floor`
    - _Requirements: 1.6, 1.10_

  - [x]* 1.8 Write unit tests for `LearningValidator`
    - Table-test `validate` across the verified × improvement matrix (unverified always `REJECTED`;
      improvement below `min_improvement` `REJECTED`; verified + sufficient improvement `VALIDATED`)
    - Assert `should_unlearn` fires exactly at/below the retire floor
    - _Requirements: 1.6, 1.10, 7.2_

- [x] 2. Learning Engine wiring — `friday/learning/engine.py`
  - [x] 2.1 Implement the pure `ingest()` pipeline core
    - Create `friday/learning/engine.py` with a `"""Ch 15 — ..."""` module docstring
    - Implement `LearningEngine.__init__(discovery=None, generalizer=None, validator=None, *,
      min_repetitions=3)` defaulting the three collaborators
    - Implement pure `ingest(experience) -> LearningStep`: drop any experience whose `verified` is not
      `True`, then run `PatternDiscovery` → `Generalizer` → `LearningValidator` in order and return a
      `LearningStep` recording the discovered pattern, generalized principle, and validation result;
      deterministic and side-effect free with respect to its return value
    - _Requirements: 1.1, 1.6_

  - [x] 2.2 Implement improvement tracking and unlearning
    - Implement `improvement(key: CompetenceKey) -> float` returning `0.0` for an unseen key and
      otherwise the signed difference between the latest and first observed confidence for that key,
      derived only from `competence.updated` evidence (never fabricated)
    - Implement `unlearn(principle_id, reason) -> Principle` retiring a validated principle whose
      confidence dropped below the retire floor, so it is no longer proposed for procedural promotion
    - _Requirements: 1.10, 1.11_

  - [x] 2.3 Implement Learning kernel wiring (`attach` + handlers + emissions)
    - Implement `attach(kernel)` subscribing to `reflection.completed`, `memory.integrated`, and
      `competence.updated` via `kernel.subscribe`
    - Implement `_on_reflection_completed`/`_on_memory_integrated`/`_on_competence_updated` converting
      M8 events into `VerifiedExperience` records and calling `ingest`; read fields defensively with
      `payload.get(...)` and skip the event without raising into the tick loop when a required field
      is absent
    - On a `VALIDATED` result emit a `learning.validated` event AND a `memory.candidate` event with
      `kind="pattern"` and `verified=True`; on `REJECTED` emit `learning.rejected` and emit NO
      procedural `memory.candidate`; on unlearning emit exactly one `learning.unlearned`; use
      `make_event` from `friday.events.event`
    - Emit `learning.pattern_discovered` when a pattern crosses the repetition threshold
    - Do NOT import `friday.memory.controller`/`friday.memory.runtime`/`friday.competence.*` and do NOT
      reference `FridayMemory`/`MemoryStore` (structural enforcement of Property 1)
    - _Requirements: 1.7, 1.8, 1.9, 1.12, 1.13, 5.1, 5.2_

  - [x]* 2.4 Write property test: learn only from verified experience
    - **Property 1: Learn only from verified experience**
    - **Validates: Requirements 1.1, 1.9**

  - [x]* 2.5 Write property test: validated before promotion
    - **Property 3: Validated before promotion**
    - **Validates: Requirements 1.6, 1.7, 1.8**

  - [x]* 2.6 Write property test: unlearning retires low-confidence principles
    - **Property 9: Unlearning retires low-confidence principles**
    - **Validates: Requirements 1.10**

  - [x]* 2.7 Write property test: measurable improvement is real
    - **Property 10: Measurable improvement is real**
    - **Validates: Requirements 1.11**

  - [x] 2.8 Finalize the learning public surface
    - Update `friday/learning/__init__.py` to export `LearningEngine`, `PatternDiscovery`,
      `Generalizer`, `LearningValidator`, and the data models
    - _Requirements: 5.2_

- [x] 3. Checkpoint — Learning complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Temporal reasoning — `friday/temporal/`
  - [x] 4.1 Implement `TemporalReasoner` — `friday/temporal/clock.py`
    - Create the `friday/temporal/` package (`__init__.py`) and `friday/temporal/clock.py` with a
      `"""Ch 49 — ..."""` module docstring
    - Implement `freshness(observed_at, now, *, ttl_seconds)`, `is_stale(observed_at, now, *,
      ttl_seconds)`, and `time_remaining(deadline_wall, now)` reading time ONLY from values carried on
      Kernel_Events (`logical_time`/`wall_time`) and constructing no new clock
    - _Requirements: 2.1_

  - [x] 4.2 Implement `KnowledgeAging` and `AgingItem` — `friday/temporal/aging.py`
    - Create `friday/temporal/aging.py` with a `"""Ch 9.22/49 — ..."""` module docstring
    - Define frozen `AgingItem` (`key`, `observed_at`, `freshness`)
    - Implement `__init__(*, half_life_seconds=86_400.0, stale_threshold=0.25)`,
      `freshness(observed_at, now)` as `0.5 ** ((now - observed_at) / half_life)` clamped to `[0, 1]`
      and equal to `1.0` when `now == observed_at` (reusing the `CompetenceModel` decay precedent), and
      `stale_items(items, now)` returning every item whose freshness is below `stale_threshold`
    - _Requirements: 2.1, 2.2, 2.3_

  - [x]* 4.3 Write property test: temporal decay is monotonic
    - **Property 4: Temporal decay is monotonic**
    - **Validates: Requirements 2.2**

  - [x] 4.4 Implement `DeadlineTracker` classification core — `friday/temporal/deadlines.py`
    - Create `friday/temporal/deadlines.py` with a `"""Ch 49 — ..."""` module docstring
    - Define `DeadlineState(str, Enum)` (`ON_TRACK`/`APPROACHING`/`MISSED`) and frozen `DeadlineStatus`
      (`goal_id`, `state`, `remaining_seconds`, `deadline_wall`)
    - Implement `__init__(*, approach_fraction=0.2)`, `register(goal_id, deadline_wall, *,
      created_wall)`, `evaluate(now_wall) -> List[DeadlineStatus]`, and `can_finish(goal_id, now_wall,
      *, est_seconds)`; classify `MISSED` when `now_wall > deadline_wall` and the goal is non-terminal,
      `APPROACHING` when `remaining <= approach_fraction * total_window` and not missed, else
      `ON_TRACK`; treat a non-positive window without dividing by zero (`MISSED` only when
      `now_wall > deadline_wall`); do NOT track goals without a deadline constraint
    - _Requirements: 2.4, 2.7, 2.8_

  - [x] 4.5 Implement `DeadlineTracker` kernel wiring (`attach` + emissions)
    - Implement `attach(kernel)` subscribing to `goal.created` and `goal.state_changed` and reading
      each deadline from the goal `constraints` deadline field
    - Publish `temporal.deadline_approaching` on an `APPROACHING` classification and
      `temporal.deadline_missed` on a `MISSED` classification via `make_event`; read fields defensively
      and never raise into the tick loop
    - _Requirements: 2.5, 2.6_

  - [x]* 4.6 Write property test: deadline detection
    - **Property 5: Deadline detection**
    - **Validates: Requirements 2.4, 2.5**

  - [x]* 4.7 Write unit tests for temporal edge cases
    - Assert `stale_items` returns exactly the items below `stale_threshold`
    - Assert non-positive / zero deadline windows never divide by zero and classify only on
      `now_wall > deadline_wall`; assert goals without a deadline constraint are not tracked
    - _Requirements: 2.3, 2.7, 2.8, 7.2_

- [x] 5. Checkpoint — Temporal complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Long-Horizon planning — `friday/horizon/`
  - [x] 6.1 Create the horizon package and planning data models
    - Create the `friday/horizon/` package (`__init__.py`) and `friday/horizon/planner.py` with a
      `"""Ch 42 — ..."""` module docstring
    - Define `HorizonLevel(str, Enum)` (`VISION`/`MISSION`/`PROJECT`/`MILESTONE`/`GOAL`), frozen
      `Milestone` (`id`, `text`, `goal_ids`, `prerequisites`, `reached=False`), frozen `Project`
      (`id`, immutable `vision`, ordered `milestones`) with `to_dict`/`from_dict`, and frozen
      `RoadmapRevision` (`add`, `remove`)
    - _Requirements: 3.1_

  - [x] 6.2 Implement `LongHorizonPlanner` roadmap operations
    - Implement `define_project(project) -> str`, `next_actionable(project_id) -> Optional[Milestone]`
      (next milestone whose prerequisites are complete), `advance(project_id, milestone_id) -> Project`
      marking a milestone reached ONLY after its verification point passes, and
      `revise_roadmap(project_id, revision) -> Project` evolving milestones while keeping the immutable
      `vision` unchanged and never mutating the Goal outcome
    - _Requirements: 3.1, 3.2, 3.4_

  - [x] 6.3 Implement checkpoint/restore persistence
    - Implement `checkpoint() -> Dict[str, Any]` producing JSON-serializable roadmap state (projects,
      milestones, goal ids) and `restore(state)` rehydrating roadmaps, reusing M3 `Goal.to_dict`/
      `from_dict` and the kernel checkpoint/restore semantics without rewriting them
    - Restore defensively: default missing fields to empty roadmaps and never invent goal ids or
      milestones from partial/truncated state
    - _Requirements: 3.5, 3.6, 3.8, 5.5_

  - [x] 6.4 Implement Long-Horizon kernel wiring (`attach` + emissions)
    - Implement `attach(kernel)` subscribing to `goal.created`, `goal.state_changed`, and
      `kernel.checkpoint`
    - On `advance`, publish `horizon.milestone_reached` and `horizon.project_advanced` via `make_event`
      once the verification point passes; read fields defensively and never raise into the tick loop
    - _Requirements: 3.3, 3.7_

  - [x]* 6.5 Write property test: long-horizon goal survives restart
    - **Property 7: Long-horizon goal survives restart**
    - **Validates: Requirements 3.5, 3.6, 6.1**

  - [x]* 6.6 Write unit tests for roadmap revision and partial restore
    - Assert `revise_roadmap` evolves milestones while `vision` stays unchanged
    - Assert `restore` from truncated state defaults to empty roadmaps and invents no goal ids
    - _Requirements: 3.2, 3.8, 7.2_

- [x] 7. Checkpoint — Long-Horizon complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Background cognition — `friday/background/`
  - [x] 8.1 Implement `BackgroundRuntime` contract + idle tracking
    - Create the `friday/background/` package (`__init__.py`) and `friday/background/runtime.py` with a
      `"""Ch 43 — ..."""` module docstring
    - Implement `BackgroundRuntime(RuntimeContract)` with `__init__(*, idle_ticks_required=5,
      max_work_per_tick=1)` and all `RuntimeContract` members (`name` → `"background"`, `initialize`,
      `tick`, `observe`, `receive`, `publish`, `checkpoint`, `restore`, `shutdown`, `health`) so the
      kernel can `register_runtime` it
    - `initialize(kernel)` subscribes to foreground-activity events (`goal.state_changed`,
      `action.executed`) rather than busy-polling; `receive` resets the idle counter on any
      foreground-activity event so foreground preempts background immediately
    - Import ONLY `friday.events`, `friday.kernel.contracts`, and standard-library modules
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 5.3_

  - [x] 8.2 Implement background work units and emissions
    - Implement `tick(logical_time)` performing at most `max_work_per_tick` `Background_Work_Unit`s
      only when no foreground activity occurred within the preceding `idle_ticks_required` ticks, and
      no work otherwise
    - Implement `_consolidate_memory`/`_apply_competence_decay`/`_check_freshness`/
      `_advance_long_horizon` as bounded, DRY_RUN-safe units; publish a `background.work_done` event
      describing the unit and propose any memory write ONLY through a `memory.candidate` event
    - Wrap each work unit in a guard that contains exceptions, reports a degraded reason via `health`,
      and never raises into the kernel tick loop
    - _Requirements: 4.3, 4.6, 4.7, 4.8_

  - [x]* 8.3 Write property test: background yields to foreground
    - **Property 6: Background yields to foreground**
    - **Validates: Requirements 4.2, 4.3, 4.4, 6.3**

  - [x]* 8.4 Write unit tests for the Background contract and degraded mode
    - Assert all `RuntimeContract` methods are present and `checkpoint()`/`restore()` round-trips
    - Assert a raising work unit is contained, `health()` reports degraded, and the tick loop survives
    - _Requirements: 4.1, 4.7, 7.2_

- [x] 9. Checkpoint — Background complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Isolation and import-boundary tests
  - [x]* 10.1 Write AST-based import-boundary/isolation tests
    - Create `tests/friday/test_m9_isolation.py` (extending the M8 AST pattern)
    - Assert `friday/learning/*.py` import none of `friday.memory.controller`, `friday.memory.runtime`,
      or any `friday.competence` module, and reference no `FridayMemory`/`MemoryStore` symbol
    - Assert `friday/background/runtime.py` imports only `friday.events`, `friday.kernel.contracts`,
      and standard-library modules
    - Assert no hardcoded application names, site names, or URLs in the M9 file set (Axiom 15)
    - Assert each new M9 module carries a `"""Ch NN — ..."""` docstring
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 7.3_

- [x] 11. Kernel-event integration and determinism tests
  - [x]* 11.1 Write kernel-event integration test
    - Create `tests/friday/test_m9_integration.py`: build a real `CognitiveKernel`, attach the M8
      producers plus the M9 `LearningEngine`, `DeadlineTracker`, and `LongHorizonPlanner`, and
      `register_runtime` the `BackgroundRuntime`
    - Drive `verification.completed`/`competence.updated`/`goal.*` events through `kernel.publish_event`
      and assert the expected `learning.*` / `temporal.*` / `horizon.*` / `background.work_done` events
      land on the event log in causal order, everything flowing through `subscribe`/`publish_event`
    - Run under `FRIDAY_DRY_RUN=1`
    - _Requirements: 5.1, 6.2, 7.2_

  - [x]* 11.2 Write property test: determinism
    - **Property 8: Determinism**
    - **Validates: Requirements 6.4, 6.5**

- [x] 12. The M9 Gate (multi-session simulation)
  - [x]* 12.1 Write the M9 Gate test
    - Create `tests/friday/test_m9_gate.py` wiring a real kernel with the M9 subsystems
    - Define a `Project` with a multi-milestone roadmap via `LongHorizonPlanner`; submit the
      long-horizon `Goal` and move it `active` → `suspended` (model the user leaving); drive verified
      experience so a milestone's verification point passes; `checkpoint()` the kernel (session boundary)
    - Construct a fresh kernel, `restore(path)`, and `LongHorizonPlanner.restore`; assert the identical
      set of goal ids, goal states, and reached milestones survive the session boundary (Property 7)
    - With the foreground idle, `tick()` the `BackgroundRuntime` repeatedly; assert it advances the
      suspended long-horizon goal and publishes `horizon.project_advanced` and `background.work_done`
    - Inject a `Foreground_Activity` event mid-run; assert the `BackgroundRuntime` yields immediately
      and performs no further work until the idle condition is met again (Property 6)
    - Assert the advancement is reconstructable deterministically from the durable Kernel event log and
      that re-running the gate with identical inputs produces identical ordered M9 event types
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.2_

- [x] 13. Final regression checkpoint
  - Run `python -m pytest tests/friday/ -q`; ensure ≥ 890 existing tests plus all new M9 tests pass.
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core
  implementation tasks are never optional.
- Pure cores (`PatternDiscovery.observe`, `Generalizer.generalize/merge`,
  `LearningValidator.validate/should_unlearn`, `LearningEngine.ingest`, `TemporalReasoner.*`,
  `KnowledgeAging.freshness`, `DeadlineTracker.evaluate/can_finish`,
  `LongHorizonPlanner.checkpoint/restore`) are implemented and tested before kernel wiring so they are
  directly unit- and property-testable.
- Existing code is wrapped/extended, never rewritten: the M8 `ReflectionEngine` event stream,
  `friday/memory/procedural.py`, the `friday/competence/model.py` decay precedent, the M3
  `friday/goals/goal.py` serialization + `GoalManager`, the kernel `checkpoint`/`restore`, and the
  `RuntimeContract`.
- Learning never imports `friday.memory.controller`/`friday.memory.runtime`/`friday.competence.*`; the
  only sanctioned learning → memory path is a `memory.candidate` emission. Background imports only
  `friday.events` + `friday.kernel.contracts`.
- All ten design Correctness Properties (1–10) are realized as Hypothesis property tests, each
  annotated with its property number and validated requirement clauses.
- Every task references specific requirement acceptance criteria for traceability, and all tests run
  under `FRIDAY_DRY_RUN=1`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "4.1", "6.1", "8.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "4.2", "6.2", "8.2"] },
    { "id": 2, "tasks": ["1.4", "1.5", "4.3", "4.4", "6.3"] },
    { "id": 3, "tasks": ["1.6", "1.7", "4.5", "6.4"] },
    { "id": 4, "tasks": ["1.8", "2.1", "4.6", "4.7", "6.5", "6.6", "8.3", "8.4"] },
    { "id": 5, "tasks": ["2.2"] },
    { "id": 6, "tasks": ["2.3", "2.8"] },
    { "id": 7, "tasks": ["2.4", "2.5", "2.6", "2.7", "10.1"] },
    { "id": 8, "tasks": ["11.1", "11.2"] },
    { "id": 9, "tasks": ["12.1"] }
  ]
}
```
