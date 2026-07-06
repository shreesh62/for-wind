# Requirements Document

## Introduction

Milestone 7 (M7) is the milestone that makes FRIDAY a *general* computer operator. Milestones M1–M6
established a persistent cognitive substrate (Kernel, World Model, Goals, Deliberation, Intent) and a
uniform `EnvironmentContract` with a live `BrowserEnvironment`, but FRIDAY still could not operate
arbitrary software: the desktop runtime was a placeholder, there was no closed-loop motor control,
capabilities were a three-method stub, and there was no way to make sense of an interface FRIDAY had
never seen.

M7 delivers four tightly-coupled subsystems built on the M1–M6 contracts: a real Desktop Runtime, a
closed-loop Motor System, a full Capability layer, and an Exploration Engine. The binding thesis
constraint (Axiom 15, FAS Ch 63) is that there is **zero application-specific code** anywhere in M7 —
applications are environments, capabilities are universal, and no interface knowledge is hardcoded. The
milestone is proven by the M7 Gate: completing a goal on never-before-seen software through exploration,
with no environment-specific code on the interaction path.

This requirements document is derived from the approved M7 design document. It captures the design intent
as verifiable EARS requirements and preserves the design's 11 correctness properties by ensuring each can
reference at least one acceptance criterion. Requirements map to FAS Chapters 16, 25, 30, 31, and 66.

## Glossary

- **FRIDAY**: The general computer operator system being built; the parent of all M7 subsystems.
- **Desktop_Environment**: The Windows desktop runtime that implements the full `EnvironmentContract` and
  `EnvironmentRuntime`, observing via UIA + OCR sensors and interacting via the Motor System.
- **Environment_Contract**: The uniform abstract interface (`observe`, `interact`, `verify`,
  `query_objects`, `query_capabilities`, `pause`, `resume`, `shutdown`, `health`, `name`) every
  environment implements. Callers describe what they want, never where or how.
- **Browser_Environment**: The M6 reference implementation of the `Environment_Contract`.
- **Window_Manager**: The M7 component that enumerates, focuses, launches, resizes, moves, minimizes, and
  restores windows, wrapping the reused `SystemActions`.
- **Display_Manager**: The M7 component providing multi-monitor geometry, DPI, and coordinate scaling,
  including logical↔physical coordinate transforms.
- **Clipboard_Manager**: The M7 component that reads/writes the system clipboard and keeps a bounded
  history of entries.
- **Session_Manager**: The M7 component that observes session/power state and performs gated,
  high-risk session control (lock) and safe window-set restore.
- **Motor_System**: The M7 closed-loop cursor/keyboard controller that acquires a re-verifiable target,
  moves incrementally with observation and correction, and verifies arrival.
- **Target_Lock**: A resolved, re-verifiable handle on a target object, containing its bounding box,
  physical center, monitor index, acquisition confidence, and perception source.
- **Motion_Profile**: The movement style (`PRECISE`, `FAST`, `SMOOTH`, `SAFE`) trading speed against
  precision and safety.
- **Motor_Result**: The outcome of a closed-loop motor operation, containing the step record, final lock,
  evidence, and any error; convertible to an `ActionResult`.
- **Arrival_Tolerance**: The maximum physical-pixel distance between the final cursor position and the
  target center that still counts as arrival.
- **Capability_Contract**: The abstract base class defining a reusable, composable, evidence-tracked unit
  of competence, with nine members (`id`, `version`, `confidence`, `preconditions`, `expected_outcome`,
  `execute`, `verify`, `recover`, `update_competence`).
- **Capability_Registry**: The registry of executable capabilities with wired handlers, queryable by
  abstract verb and ranked by evidence-backed confidence.
- **Legacy_Tool_Registry**: The pre-existing planning-metadata-only `tools/registry.py` retained during
  the TD-5 migration and adapted via `import_tool_metadata` / `as_tool_view`.
- **Exploration_Engine**: The M7 component that makes unknown software learnable through safe,
  risk-ordered experimentation, operating only against the abstract `Environment_Contract`.
- **Object_Graph**: A graph of inferred interface objects (`ObjectNode`s) built from any environment's
  observations, with generic typed edges and per-node confidence.
- **Affordance_Inferrer**: The component that maps generic object types to candidate affordances with an
  attached risk level and minimum required confidence.
- **Safe_Experiment_Planner**: The component that orders experiments up the risk ladder and gates each by
  a monotonic confidence table.
- **Demonstration_Recorder**: The component that watches a user and extracts coordinate-free principles
  from raw demonstration events.
- **Risk_Level**: The safety ladder ordinal for interactions: `OBSERVE(0) < HOVER(1) < CLICK(2) <
  MODIFY(3) < DELETE(4)`.
- **Risk_Confidence_Gate**: The monotonic mapping from `Risk_Level` to the minimum node confidence
  required to run an experiment at that risk (`OBSERVE→0.0, HOVER→0.2, CLICK→0.5, MODIFY→0.75,
  DELETE→0.9`).
- **Action_Result**: The universal outcome contract every action returns, carrying status, target, and
  `Action_Evidence`.
- **Action_Evidence**: The proof of a state change (before/after hashes and change signals) required for
  a verified success.
- **Evidence_Law**: The rule that a successful state-changing `Action_Result` must carry evidence
  (`has_evidence == True`); no unverified successes are permitted.
- **Unified_Verification_Engine**: The M6 verification engine through which all action verification flows.
- **Kernel**: The cognitive kernel that ticks environments; part of the M1–M5 cognition layer.
- **Deliberation**: The planning layer that requests abstract capabilities from environments.
- **M7_Gate**: The acceptance test in which a goal is completed on a never-before-seen
  `UnknownAppStubEnvironment` through exploration with zero environment-specific interaction code.
- **DRY_RUN_Mode**: The test mode enabled by `FRIDAY_DRY_RUN=1`, in which `pyautogui`, `win32`/UIA, OCR,
  and clipboard backends are mocked and no real OS I/O occurs.
- **FAS**: The FRIDAY Architecture Specification; referenced by chapter in module docstrings.

## Requirements

### Requirement 1: Desktop Runtime

**User Story:** As a system integrator, I want a real Windows Desktop Environment that implements the same
uniform contract as the Browser Environment, so that FRIDAY can operate any desktop application without
the Kernel or Deliberation learning that a new environment type exists.

#### Acceptance Criteria

1. THE Desktop_Environment SHALL implement every member of the Environment_Contract and the
   EnvironmentRuntime interface, matching the member set implemented by the Browser_Environment.
2. WHEN a shared environment-conformance test that passes for the Browser_Environment is applied to the
   Desktop_Environment, THE Desktop_Environment SHALL pass that test with identical result types.
3. WHEN `observe` is invoked, THE Desktop_Environment SHALL return a list of Observation objects fused
   from UIA elements and OCR text regions, each carrying an object type, a bounding box, and a confidence
   value.
4. WHILE UIA and OCR sensors are available, THE Desktop_Environment SHALL rank UIA-sourced observations
   above OCR-sourced observations by assigning UIA observations a higher confidence value.
5. WHEN `interact` is invoked with an abstract Action, THE Desktop_Environment SHALL dispatch the Action
   through a dictionary route table keyed by capability verb and return an Action_Result.
6. WHEN `interact` completes a state-changing Action successfully, THE Desktop_Environment SHALL return an
   Action_Result whose Action_Evidence reports `has_evidence` as true.
7. WHEN `name` is read, THE Desktop_Environment SHALL return the stable identifier `"desktop.windows"`.
8. WHEN `query_capabilities` is invoked, THE Desktop_Environment SHALL return abstract capability verbs
   only.
9. WHEN any Environment_Contract member is invoked with a generated Action or ObjectQuery, THE
   Desktop_Environment SHALL return the declared result type without raising an exception.

### Requirement 2: Desktop Managers

**User Story:** As a desktop runtime, I want dedicated managers for windows, display geometry, clipboard,
and session state, so that lifecycle and OS concerns are handled with evidence and safe defaults.

#### Acceptance Criteria

1. WHEN a window operation (`focus`, `launch`, `resize`, `move`, `minimize`, `restore`) is invoked, THE
   Window_Manager SHALL return an Action_Result whose Action_Evidence reports `window_changed`.
2. WHEN `launch` or `focus` is invoked, THE Window_Manager SHALL take the application name or window title
   from the call arguments rather than from any hardcoded application identifier.
3. WHEN `to_physical` is applied to a logical point and then `to_logical` is applied to the result for the
   same monitor, THE Display_Manager SHALL return coordinates equal to the original logical point within a
   tolerance of ±1 pixel.
4. WHEN a physical move is requested at a coordinate, THE Display_Manager SHALL resolve the owning monitor
   before returning the transformed physical coordinate.
5. WHEN `write` is invoked on the Clipboard_Manager, THE Clipboard_Manager SHALL record a history entry
   and return an Action_Result.
6. WHILE entries are being written, THE Clipboard_Manager SHALL keep the history length less than or equal
   to the configured history limit by evicting the oldest entry.
7. WHEN `history` is invoked, THE Clipboard_Manager SHALL return entries ordered newest-first.
8. IF `lock` is invoked WHILE session control is not enabled, THEN THE Session_Manager SHALL return a
   blocked Action_Result with error `"session_control_disabled"` and SHALL apply no state change.
9. WHEN `restore` is invoked with a session snapshot, THE Session_Manager SHALL re-focus and reposition
   only the windows recorded in that snapshot.

### Requirement 3: Motor System

**User Story:** As the interaction layer, I want closed-loop cursor and keyboard control, so that FRIDAY
moves by observing, predicting, correcting, and verifying arrival rather than issuing blind coordinate
clicks.

#### Acceptance Criteria

1. WHEN `acquire_target` is invoked with a non-empty description and a valid observed world, THE
   Motor_System SHALL return either no lock when no object matches or a Target_Lock whose center lies
   inside its bounding box and whose confidence is within `[0.0, 1.0]`.
2. WHEN `acquire_target` resolves a target present in both UIA and OCR sources, THE Motor_System SHALL
   select the UIA source in preference to the OCR source.
3. WHILE moving toward a stationary target using the PRECISE or SAFE Motion_Profile, THE Motor_System
   SHALL record a step sequence in which the residual distance to the target center is non-increasing.
4. WHEN a move toward a stationary target completes, THE Motor_System SHALL either report success with the
   final cursor within the Arrival_Tolerance of the target center or report `success` as false with an
   explicit error.
5. WHILE moving using the SAFE Motion_Profile, IF the target moves mid-move and a fresh lock is
   obtainable, THEN THE Motor_System SHALL re-acquire the target and bring the final residual within the
   Arrival_Tolerance.
6. WHILE moving using the SAFE Motion_Profile, IF the target moves mid-move and no fresh lock is
   obtainable, THEN THE Motor_System SHALL report `success` as false.
7. WHEN a move completes, THE Motor_System SHALL re-observe the target and, IF the target is absent, SHALL
   report `success` as false with error `"target_lost"`.
8. WHEN `click`, `type_text`, or `scroll_to_visible` is invoked, THE Motor_System SHALL move to the target
   first, then perform the terminal action, then observe the after-state and populate Action_Evidence.
9. THE Motor_System SHALL perform every physical move through the Display_Manager coordinate transform
   rather than through a direct coordinate call.

### Requirement 4: Capabilities

**User Story:** As a capability layer, I want a full capability contract and an executable registry with
evidence-backed confidence, so that competence is measured, ranked, and migrated from legacy metadata
without breaking existing planning.

#### Acceptance Criteria

1. THE Capability_Contract SHALL declare all nine members: `id`, `version`, `confidence`, `preconditions`,
   `expected_outcome`, `execute`, `verify`, `recover`, and `update_competence`.
2. WHEN `confidence` is read for any Capability_Contract, THE Capability_Contract SHALL return a value
   within `[0.0, 1.0]`.
3. WHEN `update_competence` is invoked with an outcome, THE Capability_Contract SHALL compute confidence
   as a pure function of the successes and attempts counts.
4. WHEN a successful outcome is folded in through `update_competence`, THE Capability_Contract SHALL
   produce a confidence value no lower than the prior confidence value.
5. WHEN a failed outcome is folded in through `update_competence`, THE Capability_Contract SHALL produce a
   confidence value no higher than the prior confidence value.
6. WHEN `find_for` is invoked with an abstract verb, THE Capability_Registry SHALL return the matching
   capabilities sorted by descending confidence.
7. WHEN `import_tool_metadata` is invoked with the Legacy_Tool_Registry, THE Capability_Registry SHALL
   adopt the legacy tool entries as low-confidence, unwired capability descriptors.
8. WHEN `as_tool_view` is invoked, THE Capability_Registry SHALL return a capability-to-names map shaped
   like the Legacy_Tool_Registry capability listing.
9. WHEN `promote_candidate` is invoked with a capability candidate, THE Capability_Registry SHALL register
   a corresponding executable Capability_Contract.

### Requirement 5: Exploration Engine

**User Story:** As a general operator, I want an exploration engine that safely probes unknown interfaces
and learns coordinate-free principles from demonstration, so that FRIDAY can understand and operate
software it has never seen.

#### Acceptance Criteria

1. WHEN `explore` is invoked on an environment, THE Exploration_Engine SHALL build an Object_Graph from
   the environment observations and infer affordances for each node before planning experiments.
2. WHEN experiments are executed during `explore`, THE Exploration_Engine SHALL execute them in
   non-decreasing Risk_Level order.
3. IF an experiment's Risk_Level requires more confidence than the node's current confidence provides,
   THEN THE Safe_Experiment_Planner SHALL not permit that experiment to execute and SHALL record the skip
   in the result notes.
4. WHEN comparing any two risk levels where the first is lower than the second, THE Safe_Experiment_Planner
   SHALL require a Risk_Confidence_Gate value for the first that is less than or equal to the value for the
   second.
5. THE Safe_Experiment_Planner SHALL not permit a DELETE-risk experiment to execute while node confidence
   is below `0.9`.
6. WHEN `explore` returns, THE Exploration_Engine SHALL report an overall confidence value within
   `[0.0, 1.0]`.
7. WHEN `extract_principles` is invoked on a demonstration recording, THE Demonstration_Recorder SHALL
   produce principles that each have a non-empty target descriptor and contain no raw pixel coordinate.
8. WHEN a derived procedure is replayed against a re-scaled or re-positioned Object_Graph, THE
   Exploration_Engine SHALL resolve the same semantic targets as in the original demonstration.
9. WHEN `explore` reaches the confidence target or exhausts the experiment budget, THE Exploration_Engine
   SHALL terminate and return an exploration result.

### Requirement 6: Site-Agnosticism and Kernel Isolation

**User Story:** As the architect, I want to enforce zero application-specific code and strict import
boundaries, so that generality is structurally guaranteed rather than assumed.

#### Acceptance Criteria

1. WHEN the repo-wide source scan runs over `friday/` excluding the legacy quarantine, THE FRIDAY source
   SHALL contain no hardcoded `http` or `https` site URL.
2. WHEN the repo-wide source scan runs over `friday/` excluding the legacy quarantine, THE FRIDAY source
   SHALL contain no application-name conditional branch and no per-application handler or agent class.
3. WHEN `explore` is run against two distinct Environment_Contract implementations, THE Exploration_Engine
   SHALL execute the same algorithm without any environment-type conditional branch.
4. WHEN the import-boundary test runs, THE Kernel and Deliberation packages SHALL import none of the
   desktop modules, `pyautogui`, or `win32`.
5. WHEN the import-boundary test runs, THE Exploration_Engine package SHALL import neither the
   Desktop_Environment nor the Browser_Environment concretely, importing only the abstract contracts.

### Requirement 7: The M7 Gate

**User Story:** As a project stakeholder, I want FRIDAY to complete a goal on never-before-seen software
through exploration, so that generality is demonstrated end to end.

#### Acceptance Criteria

1. WHEN a goal is issued against a never-before-seen `UnknownAppStubEnvironment`, THE Exploration_Engine
   SHALL build an understanding of the interface through safe experiments before the goal is attempted.
2. WHEN the goal is attempted after exploration, THE FRIDAY interaction path SHALL use only
   Environment_Contract calls and SHALL contain no environment-specific code.
3. WHEN the goal is completed, THE FRIDAY SHALL reach the interface success state with supporting
   evidence.

### Requirement 8: Non-regression and DRY_RUN Discipline

**User Story:** As a maintainer, I want the existing test suite to stay green and all new tests to run
without real OS I/O, so that M7 adds capability without eroding the regression oracle.

#### Acceptance Criteria

1. WHEN the full test suite runs after M7 is added, THE FRIDAY test suite SHALL keep all 854 pre-existing
   tests passing.
2. WHILE `DRY_RUN_Mode` is enabled, THE FRIDAY test surfaces SHALL mock `pyautogui`, `win32`/UIA, OCR, and
   the clipboard backend so that no real OS input, window manipulation, or clipboard I/O occurs.
3. THE FRIDAY M7 modules SHALL each carry a module docstring beginning with an FAS chapter reference in the
   form `"""Ch NN — ..."""`.
4. WHEN a successful desktop Action_Result is produced, THE Unified_Verification_Engine SHALL remain the
   path through which the action is verified.
