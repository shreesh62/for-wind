# Implementation Plan: M7 — Desktop Runtime, Motor System, Capabilities & Exploration

## Overview

This plan converts the M7 design into incremental, test-backed coding tasks that make FRIDAY a general
computer operator. It builds bottom-up along the dependency chain: the Capability layer first (the
`CapabilityContract` ABC and data models that motor and exploration depend on), then the independent
desktop managers, then the closed-loop `MotorSystem`, then the `DesktopEnvironment` that replaces the
placeholder, then the `ExplorationEngine` (which works only against the abstract contract). Contract
conformance, import-boundary/site-agnosticism, the M7 Gate, and the 11 property-based tests follow, with
checkpoints ensuring the 854 pre-existing tests stay green throughout.

Implementation language: **Python 3.12** (as used in the design). All new modules carry a
`"""Ch NN — ..."""` docstring, all tests run under `FRIDAY_DRY_RUN=1` with `pyautogui`/`win32`/UIA/OCR/
clipboard mocked, and the reused actuators (`SystemActions`, `DesktopChromeController`, `BrowserController`,
`EvidenceVerifier`/`UnifiedVerificationEngine`) are wrapped, never modified.

## Tasks

- [ ] 1. Build the full Capability layer (contract, data models, base helper)
  - [ ] 1.1 Replace the CapabilityContract stub with the full ABC and data models
    - In `friday/kernel/contracts/capability.py`, replace the 3-method stub with the full
      `CapabilityContract` ABC declaring all nine members: `id`, `version`, `confidence`, `preconditions`,
      `expected_outcome`, `execute` (async), `verify`, `recover`, `update_competence`
    - Add `Condition` (with `holds(world)`), `WorldStateDelta` (with `as_predicted_world()`), and
      `CompetenceRecord` (Laplace-smoothed `confidence` property clamped to `[0,1]`) data models
    - Module docstring must begin `"""Ch 16 — ..."""`
    - _Requirements: 4.1, 4.2, 4.3, 8.3_

  - [ ] 1.2 Implement BaseCapability helper
    - Create `friday/capabilities/contracts.py` with `BaseCapability` implementing `confidence` and
      `update_competence` on top of a `CompetenceRecord` so concrete capabilities only implement
      domain-specific methods
    - Ensure a success folds in confidence no lower than prior, a failure no higher than prior
    - Module docstring must begin `"""Ch 16 — ..."""`
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 8.3_

  - [ ]* 1.3 Write property test for capability confidence bounds & monotonic evidence
    - **Property 7: Capability confidence bounds & monotonic evidence**
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5**
    - Add to `tests/friday/test_m7_properties.py` using Hypothesis to generate success/failure sequences

  - [ ] 1.4 Implement CapabilityRegistry with legacy coexistence
    - Create `friday/capabilities/registry.py` with `CapabilityRegistry`: `register`, `unregister`, `get`,
      `find_for(verb, min_confidence)` sorted by descending confidence, `record_outcome`,
      `promote_candidate`
    - Add TD-5 coexistence: `import_tool_metadata(tool_registry)` adopting legacy `ToolRegistry` entries as
      low-confidence unwired descriptors, and `as_tool_view()` returning a capability→names map shaped like
      `ToolRegistry.list_capabilities()`
    - Do NOT modify `friday/tools/registry.py`; import and adapt it
    - Module docstring must begin `"""Ch 16 — ..."""`
    - _Requirements: 4.6, 4.7, 4.8, 4.9, 8.3_

  - [ ]* 1.5 Write unit tests for CapabilityContract and CapabilityRegistry
    - Test registration, `find_for` confidence ranking, competence updates, `promote_candidate`, and
      legacy `import_tool_metadata`/`as_tool_view` shape parity
    - _Requirements: 4.1, 4.6, 4.7, 4.8, 4.9_

- [ ] 2. Checkpoint - Capability layer
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Implement the desktop managers (independent, wrap reused actuators)
  - [ ] 3.1 Implement DisplayManager and Monitor
    - Create `friday/environments/desktop/display_manager.py` with frozen `Monitor` dataclass (`index`,
      `bounds`, `work_area`, `dpi`, `scale`, `is_primary`) and `DisplayManager`: `monitors`, `primary`,
      `monitor_at(x, y)`, `to_physical(x, y, monitor)`, `to_logical(x, y, monitor)`
    - `monitor_at` must resolve the owning monitor before a physical transform is returned
    - Round-trip `to_logical(to_physical(x, y, m), m)` must equal `(x, y)` within ±1px
    - Module docstring must begin `"""Ch 30 — ..."""`; mock `win32`/monitor enumeration under DRY_RUN
    - _Requirements: 2.3, 2.4, 8.2, 8.3_

  - [ ]* 3.2 Write property test for DPI round-trip
    - **Property 11: DPI round-trip**
    - **Validates: Requirements 2.3**
    - Generate monitor/DPI configs and logical points with Hypothesis in `tests/friday/test_m7_properties.py`

  - [ ] 3.3 Implement ClipboardManager and ClipboardEntry
    - Create `friday/environments/desktop/clipboard.py` with `ClipboardEntry` and `ClipboardManager`
      (`history_limit=25`): `read`, `write(text)` recording a history entry and returning an
      `ActionResult`, `history()` newest-first and length `<= history_limit` (oldest evicted),
      `clear_history`
    - Under `FRIDAY_DRY_RUN=1` back the clipboard with an in-memory buffer (no real OS clipboard I/O)
    - Module docstring must begin `"""Ch 30 — ..."""`
    - _Requirements: 2.5, 2.6, 2.7, 8.2, 8.3_

  - [ ]* 3.4 Write property test for clipboard history bound
    - **Property 10: Clipboard history bound**
    - **Validates: Requirements 2.6, 2.7**
    - Generate sequences of `write` calls with Hypothesis; assert bound and newest-first ordering

  - [ ] 3.5 Implement SessionManager, PowerState, SessionSnapshot
    - Create `friday/environments/desktop/session.py` with `PowerState` enum
      (`ACTIVE/IDLE/LOCKED/UNKNOWN`), `SessionSnapshot`, and `SessionManager`
      (`allow_session_control=False`): `power_state`, `is_locked`, `snapshot`, `restore(snapshot)`,
      `lock()`
    - `lock()` while control disabled returns `ActionResult.blocked` with error
      `"session_control_disabled"` and applies no state change
    - `restore(snapshot)` re-focuses and repositions only windows recorded in the snapshot
    - Module docstring must begin `"""Ch 30 — ..."""`
    - _Requirements: 2.8, 2.9, 8.2, 8.3_

  - [ ] 3.6 Implement WindowManager and WindowInfo (wraps SystemActions)
    - Create `friday/environments/desktop/window_manager.py` with `WindowInfo` and `WindowManager`
      (accepts an injected `SystemActions`): `enumerate`, `active_window`, `focus(title_substring)` →
      `SystemActions.focus_window`, `launch(app_name)` → `SystemActions.launch_app`, `resize`, `move`,
      `minimize`, `restore`
    - Every window operation returns an `ActionResult` whose `ActionEvidence` reports `window_changed`
    - `launch`/`focus` take the app name/title from call arguments; no hardcoded application identifier
    - Do NOT modify `friday/actions/system.py`; inject and wrap it
    - Module docstring must begin `"""Ch 30 — ..."""`
    - _Requirements: 2.1, 2.2, 8.2, 8.3_

  - [ ]* 3.7 Write unit tests for the four managers
    - Test window ops produce `window_changed` evidence, session `lock` gating, and manager behavior
      against mocked `pyautogui`/`win32`/clipboard backends under DRY_RUN
    - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.8, 2.9_

- [ ] 4. Checkpoint - Desktop managers
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement the closed-loop Motor System
  - [ ] 5.1 Implement motor data models and MotorBackend
    - Create `friday/capabilities/motor.py` scaffolding: `MotionProfile` enum
      (`PRECISE/FAST/SMOOTH/SAFE`), frozen `TargetLock`, `MotorStep`, `MotorResult` (with
      `to_action_result()`), and a `MotorBackend` wrapping `pyautogui` (mocked under DRY_RUN)
    - Clamp `TargetLock.confidence` to `[0,1]`; define `PROFILE_PARAMS` step fractions/settle/reacquire
    - Module docstring must begin `"""Ch 31 — ..."""`
    - _Requirements: 3.1, 8.2, 8.3_

  - [ ] 5.2 Implement acquire_target with UIA-over-OCR preference
    - Add `MotorSystem.__init__(sensors, display, backend, max_steps=12, arrival_tolerance=3)` and
      `acquire_target(description, world)`: return `None` when nothing matches, else a `TargetLock` whose
      `center` lies inside `bbox` and whose `confidence ∈ [0,1]`
    - When a target is present in both UIA and OCR sources, select the UIA source
    - Acquisition is read-only (RiskLevel.OBSERVE), no side effects
    - _Requirements: 3.1, 3.2_

  - [ ] 5.3 Implement move_to closed loop through DisplayManager
    - Implement `move_to(target, profile=PRECISE)`: observe cursor, predict a fraction of the remaining
      vector, move via `DisplayManager.to_physical` (never a direct coordinate call), observe, record a
      `MotorStep`, loop to `max_steps`
    - For PRECISE/SAFE with a stationary target, residuals are non-increasing; on success final cursor is
      within `arrival_tolerance` of center
    - On arrival re-observe the target; if absent report `success=False` with error `"target_lost"`
    - For SAFE, re-acquire each step: if the target moved and a fresh lock is obtainable, correct and bring
      residual within tolerance; if not obtainable, report `success=False`
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 3.9_

  - [ ]* 5.4 Write property test for closed-loop convergence
    - **Property 4: Closed-loop convergence**
    - **Validates: Requirements 3.3, 3.4**
    - Use a scripted `MotorBackend` + scripted sensor; assert non-increasing residuals and arrival-or-error

  - [ ]* 5.5 Write property test for closed-loop correction
    - **Property 5: Closed-loop correction**
    - **Validates: Requirements 3.5, 3.6**
    - Script a target that moves by δ mid-move under SAFE; assert re-acquire+arrival, else `success=False`

  - [ ] 5.6 Implement click, type_text, scroll_to_visible terminal actions
    - Build on `move_to`: move first, perform the terminal action, then observe the after-state and
      populate `ActionEvidence` (`state_changed`, `text_appeared`, etc.)
    - `scroll_to_visible` loops scrolling until the target enters a monitor work area or the scroll budget
      is exhausted
    - _Requirements: 3.8, 3.9_

  - [ ]* 5.7 Write unit tests for terminal motor actions and evidence
    - Assert arrival verification, evidence population, and `MotorResult.to_action_result()` bridging with
      scripted backend/sensor under DRY_RUN
    - _Requirements: 3.7, 3.8_

- [ ] 6. Checkpoint - Motor System
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement the DesktopEnvironment (replaces the placeholder)
  - [ ] 7.1 Implement DesktopEnvironment runtime with sensor fusion and route table
    - Create `friday/environments/desktop/runtime.py` with `DesktopEnvironment(EnvironmentRuntime,
      EnvironmentContract)` accepting injected managers, `MotorSystem`, and sensors
    - `name` returns `"desktop.windows"`; `observe()` fuses UIA + OCR into ranked `List[Observation]`
      (each with `object_type`, `bbox`, `confidence`) with UIA ranked above OCR by higher confidence
    - `interact(action)` dispatches via a dict route table keyed by capability verb (`click`, `type`,
      `scroll`, `press`, `focus_window`, `launch`, `read`, `copy`, `paste`) — no if/elif chains —
      delegating motion to `MotorSystem` and window/clipboard verbs to managers; returns `ActionResult`
      with populated `ActionEvidence` (`has_evidence` true on state-changing success)
    - Implement `verify`, `query_objects`, `query_capabilities` (abstract verbs only), `pause`, `resume`,
      `shutdown`, `health`; never raise for a generated `Action`/`ObjectQuery`
    - Module docstring must begin `"""Ch 30 — ..."""`
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 8.3_

  - [ ] 7.2 Wire DesktopEnvironment as the package export (replace placeholder)
    - Update `friday/environments/desktop/__init__.py` to export `DesktopEnvironment` from `runtime.py`,
      removing the placeholder implementation
    - Confirm the environment is registrable/tickable by the Kernel exactly like `BrowserEnvironment`
    - _Requirements: 1.1, 1.2_

  - [ ]* 7.3 Write property test for Evidence Law preservation
    - **Property 9: Evidence Law preserved**
    - **Validates: Requirements 1.6, 8.4**
    - Assert every successful desktop `ActionResult` has `evidence.has_evidence == True` and verification
      routes through `UnifiedVerificationEngine`

  - [ ]* 7.4 Extend the shared contract-conformance suite to DesktopEnvironment
    - **Property 1: Contract conformance (Desktop ≡ Browser at the boundary)**
    - **Validates: Requirements 1.1, 1.2, 1.9**
    - Extend the M6 parametrized `environment_contract_suite` (from `test_m6_*`) to run against
      `DesktopEnvironment` with mocked sensors in `tests/friday/test_m7_desktop_contract.py`; assert
      identical result types and no exceptions for generated `Action`/`ObjectQuery`

  - [ ]* 7.5 Write unit tests for observe fusion and route dispatch
    - Test UIA-over-OCR confidence ranking, dict-route dispatch coverage, and `name == "desktop.windows"`
    - _Requirements: 1.3, 1.4, 1.5, 1.7, 1.8_

- [ ] 8. Checkpoint - Desktop Environment (run full suite, confirm 854 green)
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Implement the Exploration Engine (abstract-contract only)
  - [ ] 9.1 Implement exploration data models and ObjectGraph
    - Create `friday/environments/unknown/__init__.py` and `friday/environments/unknown/object_graph.py`
      with `RiskLevel` enum (`OBSERVE=0<HOVER=1<CLICK=2<MODIFY=3<DELETE=4`), `ObjectNode`, `Affordance`,
      `Experiment`, `ExplorationResult`, `Principle`, `Procedure`, `CapabilityCandidate`, and `ObjectGraph`
      (`add_from_observation`, `infer_types`, `confidence_for`, `update_from_result`, `overall_confidence`,
      `nodes`)
    - Type inference must be generic (no app-specific rules); import only abstract contracts, never
      `DesktopEnvironment`/`BrowserEnvironment`
    - Module docstrings must begin `"""Ch 66 — ..."""` / `"""Ch 25 — ..."""`
    - _Requirements: 5.1, 6.5, 8.3_

  - [ ] 9.2 Implement AffordanceInferrer
    - Create `friday/environments/unknown/affordances.py` with `AffordanceInferrer.infer(node, graph)`
      mapping generic object types to candidate `Affordance`s with attached `RiskLevel` and
      `min_confidence_required`, driven by generic signals only (control type, visible-text semantics)
    - Module docstring must begin `"""Ch 66 — ..."""`
    - _Requirements: 5.1, 6.5, 8.3_

  - [ ] 9.3 Implement SafeExperimentPlanner with monotonic risk gate
    - Create `friday/environments/unknown/experiment.py` with `RISK_CONFIDENCE_GATE`
      (`OBSERVE→0.0, HOVER→0.2, CLICK→0.5, MODIFY→0.75, DELETE→0.9`), `plan(graph)` returning experiments
      sorted by ascending `RiskLevel`, and `is_permitted(experiment, node_confidence)` requiring
      `node_confidence >= gate[risk]`
    - A DELETE-risk experiment must never be permitted while node confidence `< 0.9`
    - Module docstring must begin `"""Ch 25 — ..."""`
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 6.5, 8.3_

  - [ ]* 9.4 Write property test for risk gate monotonicity
    - **Property 3: Risk gate is monotonic in risk**
    - **Validates: Requirements 5.4**
    - Assert `∀ a < b: RISK_CONFIDENCE_GATE[a] <= RISK_CONFIDENCE_GATE[b]`

  - [ ] 9.5 Implement DemonstrationRecorder principle extraction
    - Create `friday/environments/unknown/demonstration.py` with `DemonstrationRecording`,
      `DemonstrationRecorder` (`start`, `record_event`, `stop`), and `extract_principles(recording)`
      producing coordinate-free `Principle`s (non-empty `target_descriptor`, no raw pixel coordinate)
    - Module docstring must begin `"""Ch 25 — ..."""`
    - _Requirements: 5.7, 5.8, 6.5, 8.3_

  - [ ]* 9.6 Write property test for principle extraction (no coordinates)
    - **Property 8: Demonstration extracts principles, not coordinates**
    - **Validates: Requirements 5.7, 5.8**
    - Generate demonstration event streams; assert non-empty descriptors, no pixel coords, and that
      replay against a re-scaled/re-positioned graph resolves the same semantic targets

  - [ ] 9.7 Implement ExplorationEngine orchestration
    - Create `friday/environments/unknown/exploration.py` with `ExplorationEngine(inferrer, planner,
      registry, max_experiments=20, confidence_target=0.75)`: `explore(environment)`,
      `learn_from_demonstration(recording)`, `generate_capability_candidate(exploration)`
    - `explore` builds the `ObjectGraph` from `environment.observe()`, infers affordances, executes
      permitted experiments in non-decreasing risk order (skipped experiments recorded in
      `result.notes`), reports overall confidence in `[0,1]`, and terminates at the confidence target or
      budget exhaustion — using only `EnvironmentContract` calls with no environment-type branch
    - Module docstring must begin `"""Ch 25 — ..."""`
    - _Requirements: 5.1, 5.2, 5.3, 5.6, 5.9, 6.3, 6.5, 8.3_

  - [ ]* 9.8 Write property test for risk-ladder monotonicity
    - **Property 2: Risk-ladder monotonicity**
    - **Validates: Requirements 5.2, 5.5**
    - Generate synthetic `ObjectGraph`s; assert executed-experiment risks are non-decreasing and no
      DELETE-risk experiment runs below 0.9 confidence

  - [ ]* 9.9 Write unit tests for ExplorationEngine termination and candidate generation
    - Test budget exhaustion, confidence-target termination, skip notes, and
      `generate_capability_candidate` promotion into the `CapabilityRegistry`
    - _Requirements: 5.1, 5.6, 5.9, 4.9_

- [ ] 10. Checkpoint - Exploration Engine
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Enforce site-agnosticism and import boundaries
  - [ ]* 11.1 Extend import-boundary tests for M7
    - In `tests/friday/test_m7_isolation.py`, assert Kernel/Deliberation packages import none of
      `friday.environments.desktop.*`, `pyautogui`, or `win32`, and that `friday.environments.unknown.*`
      imports neither `DesktopEnvironment` nor `BrowserEnvironment` concretely (only abstract contracts)
    - Reuse the AST import-parsing pattern from `test_m6_isolation.py`
    - _Requirements: 6.4, 6.5_

  - [ ]* 11.2 Extend site-agnosticism source scan and exploration-agnosticism test
    - **Property 6: Site/app-agnosticism (Axiom 15)**
    - **Validates: Requirements 6.1, 6.2, 6.3**
    - Extend the repo-wide source scan over `friday/` (excluding legacy quarantine) to cover all M7 modules
      (no hardcoded `http(s)://` URL, no app-name conditional branch, no per-app handler/agent class), and
      assert `explore(E1)` and `explore(E2)` run the same algorithm with no environment-type branch

- [ ] 12. Implement the M7 Gate
  - [ ]* 12.1 Build UnknownAppStubEnvironment fixture and the M7 Gate test
    - In `tests/friday/test_m7_gate.py`, add `UnknownAppStubEnvironment` (subclass of
      `EnvironmentContract`) scripting a small novel interface with generic labels and a hidden success
      state reachable only by a specific sequence
    - Issue a goal, let `ExplorationEngine.explore()` build understanding via safe experiments, then
      complete the goal through the same contract calls; assert the interaction path contains zero
      environment-specific code and the success state is reached with supporting evidence
    - _Requirements: 7.1, 7.2, 7.3, 6.3_

- [ ] 13. Final regression checkpoint
  - Run `python -m pytest tests/friday/ -q`; confirm all 854 pre-existing tests remain green and all new
    M7 tests pass under `FRIDAY_DRY_RUN=1`.
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 8.1, 8.2, 8.4_

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP, but they encode
  the design's 11 correctness properties and the M7 Gate — the acceptance oracle.
- Each task references specific granular requirements clauses for traceability.
- Checkpoints (tasks 2, 4, 6, 8, 10, 13) ensure incremental validation and that the 854-test regression
  oracle stays green.
- Reused actuators are wrapped, never modified: `SystemActions` (`system.py`), `DesktopChromeController`
  (`desktop_chrome.py`), `BrowserController`, and the `EvidenceVerifier`/`UnifiedVerificationEngine`.
- All new modules carry a `"""Ch NN — ..."""` docstring; all OS surfaces (`pyautogui`, `win32`/UIA, OCR,
  clipboard) are mocked under `FRIDAY_DRY_RUN=1`.
- Property tests use Hypothesis; place them in `tests/friday/test_m7_properties.py` unless a property is
  more naturally a contract/gate test.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "3.1", "3.3", "3.5"] },
    { "id": 2, "tasks": ["1.3", "1.4", "3.2", "3.4", "3.6"] },
    { "id": 3, "tasks": ["1.5", "3.7", "5.1"] },
    { "id": 4, "tasks": ["5.2"] },
    { "id": 5, "tasks": ["5.3"] },
    { "id": 6, "tasks": ["5.4", "5.5", "5.6"] },
    { "id": 7, "tasks": ["5.7", "7.1"] },
    { "id": 8, "tasks": ["7.2", "7.3", "7.4", "7.5", "9.1"] },
    { "id": 9, "tasks": ["9.2", "9.3", "9.5"] },
    { "id": 10, "tasks": ["9.4", "9.6", "9.7"] },
    { "id": 11, "tasks": ["9.8", "9.9", "11.1", "11.2"] },
    { "id": 12, "tasks": ["12.1"] }
  ]
}
```
