# Requirements Document

## Introduction

The Universal Action Layer is the foundational actuation layer for FRIDAY, a General Purpose Computer Operator. It introduces `friday/actions/primitives.py`: a set of atomic, environment-agnostic primitive actions that every higher-level capability composes from. Today, action code is duplicated per environment (a browser click and a desktop click are separate implementations). The Universal Action Layer collapses these into single primitives whose API is identical regardless of environment. Each primitive resolves the correct environment adapter at runtime from the current perception state, targets elements semantic-first (DOM > UIA > OCR > Vision > Pixels), and returns the existing `ActionResult` contract with evidence.

This is Priority 1 of ADR-021 (the General Operator direction). The litmus test for every requirement is: "Does this make FRIDAY better at completing ARBITRARY goals?" The layer is backend/engine only for v1; no frontend work is in scope. The target environment is Windows-only with Python 3.12.

This document defines WHAT the Universal Action Layer must do. Implementation choices (specific class structures, adapter wiring details) are deferred to design.

## Glossary

- **Universal_Action_Layer**: The subsystem implemented in `friday/actions/primitives.py` that exposes atomic primitive actions with environment-agnostic APIs.
- **Primitive**: A single atomic action exposed by the Universal_Action_Layer (for example `click`, `type_text`, `scroll`). Primitives are the smallest composable unit of action.
- **Environment_Adapter**: A component that executes a primitive against a specific environment. The adapters in scope are Browser_Adapter (Playwright DOM), Desktop_Adapter (Windows UI Automation), Desktop_Actions (OS-level desktop interaction), and Vision_Adapter (coordinate/pixel fallback).
- **Browser_Adapter**: The Environment_Adapter that executes primitives in a browser via the Playwright session managed by `BrowserController`.
- **Desktop_Adapter**: The Environment_Adapter that executes primitives against Windows desktop applications via Windows UI Automation (UIA).
- **Vision_Adapter**: The Environment_Adapter of last resort that executes primitives using screen coordinates derived from OCR, vision, or raw pixels.
- **Adapter_Resolver**: The component within the Universal_Action_Layer that selects the Environment_Adapter for a primitive invocation based on the current WorldState and the target. The resolver applies a preference order but does not bind a Target to a single environment.
- **Desktop_Actions**: OS-level desktop interaction (foreground window control, keystrokes, and coordinate-based pointer actions) used when a Target supports desktop control but is not available as a Windows UIA element.
- **WorldState**: The authoritative perception snapshot defined in `friday/perception/world_state.py`, the single source of truth about the current environment.
- **Target**: A description of what a primitive acts on, expressed semantically (for example the visible text or role of an element) rather than as raw coordinates.
- **ActionResult**: The universal outcome contract defined in `friday/actions/result.py`, including status, evidence, timing, and repair hints.
- **ActionEvidence**: The evidence object attached to an ActionResult that records observable state change (defined in `friday/actions/result.py`).
- **Semantic_Source**: A perception source that provides structured element data, namely Browser DOM or Windows UIA.
- **Perception_Priority**: The semantic-first ordering DOM > UIA > OCR > Vision > Pixels defined in `friday/perception/priority.py` (ADR-014).
- **Resolution_Preference**: The ordered preference the Adapter_Resolver applies when more than one Environment_Adapter can act on a Target: (1) Browser DOM, (2) Windows UIA, (3) Desktop_Actions, (4) OCR, (5) Vision. The preference is a default ranking, not an exclusive routing rule.
- **Tool_Registry**: The capability registry defined in `friday/tools/registry.py` that the planner queries to find tools for a capability.
- **Caller**: Any higher-level capability, tool, planner, or operator code that invokes a Primitive.

## Requirements

### Requirement 1: Environment-Agnostic Primitive API

**User Story:** As a capability author, I want to call a single primitive regardless of environment, so that I can write action logic once instead of duplicating it per environment.

#### Acceptance Criteria

1. THE Universal_Action_Layer SHALL expose the following Primitives with identical call signatures across all environments: `click`, `double_click`, `right_click`, `type_text`, `press_key`, `press_hotkey`, `scroll`, `drag`, `switch_window`, `wait_for`, `observe`, and `verify`.
2. WHEN a Caller invokes a Primitive, THE Universal_Action_Layer SHALL accept the Target without requiring the Caller to specify an environment.
3. WHEN a Caller invokes a Primitive, THE Universal_Action_Layer SHALL determine the environment from the current WorldState and the Target.
4. THE Universal_Action_Layer SHALL provide one implementation per Primitive that serves all environments through Environment_Adapter resolution.

### Requirement 2: Runtime Adapter Resolution

**User Story:** As the operator engine, I want each primitive to resolve to an environment adapter at runtime using a preference order, so that the same action works in a browser, on the desktop, or via vision fallback while remaining free to choose the most reliable path.

#### Acceptance Criteria

1. WHEN a Primitive is invoked, THE Adapter_Resolver SHALL select an Environment_Adapter using the current WorldState and the Resolution_Preference.
2. WHEN a Target is available from more than one Environment_Adapter, THE Adapter_Resolver SHALL select the Environment_Adapter highest in the Resolution_Preference.
3. THE Adapter_Resolver SHALL treat the Resolution_Preference as a default ranking and SHALL keep every Environment_Adapter available for selection regardless of the current environment.
4. WHERE the Target cannot be resolved from a Semantic_Source, THE Adapter_Resolver SHALL select a lower-ranked Environment_Adapter that can act on the Target.
5. IF the Adapter_Resolver cannot select any Environment_Adapter for the Target, THEN THE Universal_Action_Layer SHALL return an ActionResult with status FAILED and a repair hint identifying the unresolved Target.

### Requirement 3: Semantic-First Targeting

**User Story:** As a system maintainer, I want primitives to prefer semantic targeting over coordinates, so that actions are reliable and resilient to visual changes (ADR-014), while still allowing coordinate fallback when semantics are unavailable.

#### Acceptance Criteria

1. WHEN the Adapter_Resolver resolves a Target, THE Adapter_Resolver SHALL evaluate perception sources in the order Browser DOM, then Windows UIA, then Desktop_Actions, then OCR, then Vision.
2. WHEN a Target is available from more than one perception source, THE Adapter_Resolver SHALL select the source highest in the Resolution_Preference.
3. WHERE a Target resolves to a Semantic_Source, THE Universal_Action_Layer SHALL execute the Primitive using semantic element data rather than screen coordinates.
4. THE Universal_Action_Layer SHALL use raw screen coordinates only when no Semantic_Source and no OCR or Vision source can resolve the Target.
5. WHEN a Primitive completes, THE Universal_Action_Layer SHALL record the perception source used in the ActionResult metadata.

### Requirement 4: Adaptive Adapter Re-Routing

**User Story:** As the General Operator, I want primitives to switch to a different adapter when the preferred one fails or is unavailable, so that I choose the fastest and most reliable path to goal completion rather than being bound to one environment.

#### Acceptance Criteria

1. IF the Browser_Adapter returns an ActionResult with status FAILED for a Target, THEN THE Adapter_Resolver SHALL select the next available Environment_Adapter in the Resolution_Preference that can act on the Target.
2. IF verification of a Primitive's outcome fails, THEN THE Universal_Action_Layer SHALL allow re-routing the Primitive to a different Environment_Adapter.
3. IF the browser context is unavailable, THEN THE Adapter_Resolver SHALL select a non-browser Environment_Adapter that can act on the Target.
4. WHERE a Target appears as a native Windows control that escapes the browser DOM, including a browser dialog, a file picker, a login or profile selector, or a permission prompt, THE Adapter_Resolver SHALL select the Desktop_Adapter or Desktop_Actions for that Target.
5. IF no remaining Environment_Adapter can act on the Target after re-routing, THEN THE Universal_Action_Layer SHALL return an ActionResult with status FAILED and a repair hint listing the adapters that were attempted.

### Requirement 5: ActionResult Contract Compliance

**User Story:** As the operator engine, I want every primitive to return an ActionResult, so that outcomes are uniform, verifiable, and usable by the repair loop.

#### Acceptance Criteria

1. WHEN a Primitive completes for any reason, THE Universal_Action_Layer SHALL return an ActionResult as defined in `friday/actions/result.py`.
2. WHEN a state-changing Primitive succeeds, THE Universal_Action_Layer SHALL attach ActionEvidence that records the observed state change.
3. IF a Primitive fails, THEN THE Universal_Action_Layer SHALL return an ActionResult with an error category and at least one repair hint.
4. WHEN a Primitive executes, THE Universal_Action_Layer SHALL record the start time, completion time, and duration in the ActionResult.
5. IF a Primitive does not complete within its configured time bound, THEN THE Universal_Action_Layer SHALL return an ActionResult with status TIMEOUT.
6. WHEN a Primitive completes within its configured time bound, THE Universal_Action_Layer SHALL return a status other than TIMEOUT.

### Requirement 6: Observation Primitive

**User Story:** As a capability author, I want an observe primitive that returns current environment state, so that I can reason about the environment before and after acting.

#### Acceptance Criteria

1. WHEN the `observe` Primitive is invoked, THE Universal_Action_Layer SHALL return a current WorldState snapshot.
2. WHEN the `observe` Primitive builds a WorldState, THE Universal_Action_Layer SHALL populate the WorldState from available perception sources following Perception_Priority.
3. THE `observe` Primitive SHALL return an ActionResult that references the produced WorldState.
4. IF no perception source is available, THEN THE `observe` Primitive SHALL return an ActionResult with status FAILED and a repair hint indicating perception is unavailable.
5. IF the produced WorldState lacks a perception source from a Semantic_Source and contains no OCR or Vision data, THEN THE `observe` Primitive SHALL return an ActionResult with status FAILED and a repair hint indicating perception quality is insufficient.

### Requirement 7: Verification Primitive

**User Story:** As the operator engine, I want a verify primitive that checks whether a condition was met, so that I can confirm outcomes and trigger repair when conditions are unmet.

#### Acceptance Criteria

1. WHEN the `verify` Primitive is invoked with a condition, THE Universal_Action_Layer SHALL evaluate the condition against a current WorldState.
2. IF the condition is satisfied, THEN THE `verify` Primitive SHALL return an ActionResult with status SUCCESS and ActionEvidence supporting the verdict.
3. IF the condition is not satisfied, THEN THE `verify` Primitive SHALL return an ActionResult with status FAILED and a reason describing the unmet condition.
4. WHEN the `verify` Primitive evaluates a condition, THE Universal_Action_Layer SHALL use the existing verification components in `friday/verification/verifier.py` to produce the verdict.

### Requirement 8: Wait Primitive

**User Story:** As a capability author, I want a wait_for primitive, so that I can pause until an expected condition holds before proceeding.

#### Acceptance Criteria

1. WHEN the `wait_for` Primitive is invoked with a condition and a time bound, THE Universal_Action_Layer SHALL poll the WorldState until the condition is satisfied or the time bound elapses.
2. WHEN the time bound elapses while the condition is unsatisfied, THE `wait_for` Primitive SHALL stop polling.
3. WHEN the condition is satisfied before the time bound elapses, THE `wait_for` Primitive SHALL return an ActionResult with status SUCCESS.
4. IF the time bound elapses before the condition is satisfied, THEN THE `wait_for` Primitive SHALL return an ActionResult with status TIMEOUT and a repair hint.

### Requirement 9: Pointer Primitives

**User Story:** As a capability author, I want pointer primitives (click, double_click, right_click, scroll, drag), so that I can interact with elements consistently across environments.

#### Acceptance Criteria

1. WHEN the `click` Primitive is invoked with a Target, THE Universal_Action_Layer SHALL resolve the Target through the Adapter_Resolver and execute a single click via the selected Environment_Adapter.
2. WHEN the `double_click` Primitive is invoked with a Target, THE Universal_Action_Layer SHALL execute a double click via the selected Environment_Adapter.
3. WHEN the `right_click` Primitive is invoked with a Target, THE Universal_Action_Layer SHALL execute a right click via the selected Environment_Adapter.
4. WHEN the `scroll` Primitive is invoked with a direction and magnitude, THE Universal_Action_Layer SHALL scroll the resolved environment by the specified magnitude in the specified direction.
5. WHEN the `drag` Primitive is invoked with a source Target and a destination Target, THE Universal_Action_Layer SHALL execute a drag from the source to the destination via the selected Environment_Adapter.
6. IF a pointer Primitive's Target cannot be resolved, THEN THE Universal_Action_Layer SHALL return an ActionResult with status FAILED and a repair hint to re-observe or relocate the Target.

### Requirement 10: Keyboard Primitives

**User Story:** As a capability author, I want keyboard primitives (type_text, press_key, press_hotkey), so that I can enter text and issue keystrokes consistently across environments.

#### Acceptance Criteria

1. WHEN the `type_text` Primitive is invoked with text, THE Universal_Action_Layer SHALL enter the text into the focused element of the resolved environment.
2. WHEN the `press_key` Primitive is invoked with a key name, THE Universal_Action_Layer SHALL issue the corresponding single keystroke in the resolved environment.
3. WHEN the `press_hotkey` Primitive is invoked with a key combination, THE Universal_Action_Layer SHALL issue the combination as a simultaneous chord in the resolved environment.
4. IF a keyboard Primitive is invoked while no element is focused in the resolved environment, THEN THE Universal_Action_Layer SHALL return an ActionResult with status FAILED and a repair hint to focus a Target first.

### Requirement 11: Window Switching Primitive

**User Story:** As a capability author, I want a switch_window primitive, so that I can move focus between windows when a goal spans multiple applications.

#### Acceptance Criteria

1. WHEN the `switch_window` Primitive is invoked with a window Target, THE Universal_Action_Layer SHALL bring the matching window to the foreground.
2. WHEN a window matching the Target is brought to the foreground, THE Universal_Action_Layer SHALL return an ActionResult to the Caller with ActionEvidence recording the window change.
3. IF no window matches the Target, THEN THE Universal_Action_Layer SHALL return an ActionResult with status FAILED and a repair hint to open the application first.
4. IF a window that does not match the Target is brought to the foreground, THEN THE Universal_Action_Layer SHALL return an ActionResult with status FAILED and a repair hint to open the application first.

### Requirement 12: Tool Registry Integration

**User Story:** As the planner, I want primitives discoverable through the capability registry, so that higher-level capabilities compose from primitives rather than duplicating environment-specific code.

#### Acceptance Criteria

1. THE Universal_Action_Layer SHALL register its Primitives with the Tool_Registry as environment-agnostic capabilities.
2. WHEN the planner queries the Tool_Registry for an interaction capability that a Primitive provides, THE Tool_Registry SHALL return the corresponding Primitive.
3. WHERE an existing environment-specific tool duplicates a Primitive, THE Universal_Action_Layer SHALL provide the Primitive as the single composable implementation for that capability.

### Requirement 13: Backward Compatibility With Existing Contracts

**User Story:** As a maintainer of the existing 381-test suite, I want the new layer to integrate without breaking current contracts, so that existing functionality keeps working.

#### Acceptance Criteria

1. THE Universal_Action_Layer SHALL return ActionResult objects that conform to the existing `friday/actions/result.py` structure without modifying that contract.
2. THE Universal_Action_Layer SHALL consume WorldState objects as produced by `friday/perception/world_state.py` without modifying that contract.
3. WHEN the Browser_Adapter executes a Primitive, THE Browser_Adapter SHALL use the existing persistent Playwright session provided by `BrowserController`.
4. WHERE existing tests assert current ActionResult or WorldState behavior, THE Universal_Action_Layer SHALL preserve that behavior.

### Requirement 14: Windows-Only Scope

**User Story:** As a v1 stakeholder, I want the layer scoped to Windows, so that delivery stays focused and testable on the target platform.

#### Acceptance Criteria

1. THE Universal_Action_Layer SHALL target Windows as the only supported operating system for v1.
2. THE Universal_Action_Layer SHALL target Python 3.12 as the runtime.
3. WHERE a primitive requires desktop control, THE Desktop_Adapter SHALL use Windows UI Automation as the desktop interface.
