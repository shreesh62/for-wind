# Requirements Document

M23 — Browser as a Generic Desktop Environment

## Introduction

### Objectives

FRIDAY is a **General Computer Operator**, not a browser-automation framework. This
milestone makes that principle true in code: the **primary execution path** for
operating any web browser — Chrome, Edge, Firefox, Brave, Arc, Electron apps, and
future browsers — SHALL be the same general desktop-cognition pipeline used for every
other desktop application (perceive → reason over World Objects → act with the Motor
System → verify via World-Model change). Browser-specific automation interfaces (CDP,
Playwright, Selenium, DevTools Protocol, browser extensions) become **optional
optimization resources**, never architectural dependencies. The desktop pipeline MUST
remain fully functional — and equally correct — with those interfaces disabled.

The end-state acceptance is a single user request satisfied identically across two
browsers with no browser-specific code: *"Open Chrome normally, search for OpenAI,
open the first result, summarize the homepage, then repeat the exact same task in
Firefox."* The only permitted difference between browsers is measured performance,
never correctness.

### Architectural Rationale

Today the browser path defaults to CDP (`browser_strategy.resolve_browser_strategy`
picks CDP modes first; `bridge._get_browser_controller` establishes Playwright-over-CDP)
and only degrades to desktop control when a profile is locked. The desktop-control
controller that exists (`DesktopChromeController`) is Chrome-window-title-specific and
OCR-only. The executor's `_build_world_state()` only populates browser-DOM elements via
CDP `observe_interactive()`; it never fuses Accessibility (UIA) + OCR + Vision + pixels
for a generic window. Chrome is therefore a **special case**, and browsers other than
Chrome and the no-CDP path are not first-class.

The rest of the stack is already environment-agnostic: `Operator`, `GoalExecutor`, the
Universal Action Layer primitives + adapter cascade, `research`, and `WebAgent` are all
duck-typed against a controller surface, and the perception stack already ranks sources
in the required order (BROWSER_DOM 100 → UIA 80 → OCR 50 → VISION 30 → PIXEL 10 in
`perception/priority.py`). M23 therefore **inverts the default** and **closes the
perception gap** rather than rewriting the cognition stack.

### Dependencies

- **A2.1 World Model v2** (M15) — beliefs carry freshness/provenance; World Objects
  reuse this for the observation metadata required by Phase 5.
- **Universal Action Layer** spec (`.kiro/specs/universal-action-layer/`) — primitives
  + adapter cascade (Browser→Desktop→DesktopActions→Vision) are the Motor System M23
  routes browser interaction through.
- **M6 Environments Verification** — `EnvironmentContract` / `EnvironmentRuntime`,
  `DesktopEnvironment` (Ch 30), backend-independence gate; M23 makes the desktop
  environment the canonical browser backend.
- **A2.8 Exploration Engine** (M7, `friday/environments/unknown/`) — used by Phase 5
  when an element cannot be identified confidently.
- Perception components: `perception/desktop.py` (UIA), `perception/ocr.py`,
  `perception/vision.py`, `perception/screen.py`, `perception/world_state.py`.

### Modified Subsystems (summary; detailed in design)

- `friday/executor.py` — `_build_world_state()` becomes universal (UIA+OCR+Vision+pixels).
- `friday/actions/desktop_browser.py` (NEW) — generic `DesktopBrowserController`
  replacing `friday/actions/desktop_chrome.py`.
- `friday/actions/browser_strategy.py` + `browser_factory.py` — desktop-first default;
  CDP becomes an opt-in optimization plugin.
- `friday/bridge.py` — primary path builds the desktop controller; CDP only when enabled.
- `friday/perception/world_state.py` + a new unified "observe active window" builder.
- Docs: FAS amendment; **rename "Browser Runtime" → "Web Environment Runtime"**.

## Glossary

- **General_Desktop_Pipeline**: The perceive → reason-over-World-Objects → act →
  verify loop (`Operator` + `GoalExecutor` + Universal Action Layer + perception stack)
  used for all desktop applications.
- **Perception_Stack**: The ranked fusion of perception sources —
  Accessibility/UI-Automation → native semantic interface → OCR → Computer Vision →
  raw pixels — defined by `perception/priority.py::SourcePriority`.
- **World_Object**: A source-agnostic semantic observation the planner/deliberator/
  executor reason over. Carries confidence, freshness, evidence, source, bounding
  region, and possible affordances. Never an application-specific structure.
- **WorldState**: The fused snapshot (`perception/world_state.py::WorldState`) built by
  the `WorldStateBuilder` from all active perception sources for the active window.
- **Universal_Perception**: Building a complete `WorldState` for the active window
  regardless of application type, via `Perception_Stack` fusion.
- **Motor_System**: The interaction layer (Universal Action Layer primitives + adapter
  cascade) providing keyboard, mouse, scroll, and shortcut actions.
- **Motor_Preference_Order**: The least-invasive-reliable interaction order —
  Keyboard → Accessibility Actions → Mouse → Pixel fallback.
- **DesktopBrowserController**: The NEW generic controller that operates any browser as
  a desktop application through `Universal_Perception` + `Motor_System`, with no
  browser-name, window-title, or OCR-only assumptions.
- **CDP_Optimization**: The optional Playwright/CDP path (`BrowserController` +
  `BrowserAdapter`), enabled only by explicit configuration; an accelerator, never
  required for correctness.
- **Web_Environment_Runtime**: The renamed "Browser Runtime" — the environment class
  that operates web browsers; one member of the general set of desktop environments.
- **Exploration_Engine**: `friday/environments/unknown/` — Observe → hypothesize →
  safe-experiment → verify → update-World-Model, used when an element is not confidently
  identified. No application-specific heuristics.
- **Verified_Success**: Task/step success established only by an observed change in the
  `WorldState` / World Model, never inferred from having sent an input.
- **Axiom_15**: General-over-specific — mechanisms are general environment/UI rules,
  never application-, browser-, site-, or window-title-specific logic.
- **Browser_Independence**: The property that the pipeline produces the same correctness
  outcome whether `CDP_Optimization` is enabled or disabled.

## Requirements

### Requirement 1: Universal Perception on the primary path (PHASE 1)

**User Story:** As the cognition stack, I want a complete WorldState built for every
task regardless of application type, so that I can operate any window — including a
browser — without a browser-specific perception path.

#### Acceptance Criteria

1. WHEN a step requires perceiving the environment, THE GoalExecutor SHALL build a
   WorldState for the active window by fusing the Perception_Stack sources in rank
   order (Accessibility/UIA → native semantic → OCR → Vision → raw pixels).
2. WHERE Accessibility/UIA observations are available for the active window, THE
   GoalExecutor SHALL include them in the WorldState ranked above OCR, OCR above
   Vision, and Vision above raw pixels.
3. WHERE no CDP browser controller is present, THE GoalExecutor SHALL still build a
   non-empty WorldState from the desktop Perception_Stack when the active window
   exposes any accessibility, OCR, or pixel content.
4. THE GoalExecutor SHALL construct the WorldState using no application-, browser-,
   or window-title-specific branching (Axiom_15).
5. WHEN the planner, deliberator, or execution engine consumes a WorldState, THEY
   SHALL reason only over World_Objects and SHALL NOT depend on which perception
   source produced an observation.

### Requirement 2: Generic Desktop Browser Controller (PHASE 2)

**User Story:** As the operator, I want a single controller that drives any browser as
a desktop application, so that Chrome, Edge, Firefox, Brave, Arc, and Electron apps are
operated by identical code.

#### Acceptance Criteria

1. THE DesktopBrowserController SHALL operate the active window through
   Universal_Perception and the Motor_System, using no browser-name check, no
   window-title assumption, and no OCR-only perception.
2. THE DesktopBrowserController SHALL expose the same duck-typed controller surface the
   GoalExecutor already consumes (`available`, `navigate`, `read_text`, `current_url`,
   `search_web`, `click`, `type_text`, `observe_interactive`), so downstream code is
   unchanged.
3. WHEN DesktopBrowserController performs navigation, THE controller SHALL use generic
   desktop interaction (focus window → address-bar shortcut → type → commit) that is
   identical across browsers, selecting targets by UI affordance, not application
   identity.
4. THE codebase SHALL contain no remaining references to `DesktopChromeController` on
   the primary path; `friday/actions/desktop_chrome.py` SHALL be removed or replaced by
   `DesktopBrowserController`.
5. THE DesktopBrowserController SHALL derive every decision from perceived UI
   affordances and the goal, never from the identity or name of the running browser
   (Axiom_15).

### Requirement 3: Browser Independence — CDP is an optimization plugin (PHASE 3)

**User Story:** As an architect, I want CDP to accelerate but never be required, so
that the architecture behaves identically whether CDP is enabled or disabled.

#### Acceptance Criteria

1. THE primary execution path SHALL default to the desktop pipeline and SHALL NOT
   establish CDP/Playwright unless CDP_Optimization is explicitly enabled by
   configuration.
2. WHERE CDP_Optimization is disabled, THE Operator SHALL complete browser tasks using
   only the desktop pipeline (Universal_Perception + Motor_System).
3. WHERE CDP_Optimization is enabled and available, THE Operator SHALL produce the same
   correctness outcome (same Verified_Success verdict and evidence kinds) as when it is
   disabled, differing only in performance.
4. THE browser strategy resolution SHALL treat DESKTOP_CONTROL as the default mode and
   any CDP mode as opt-in, reversing the current CDP-first default.
5. WHEN CDP_Optimization fails or is unavailable at runtime, THE Operator SHALL proceed
   on the desktop pipeline without error and without loss of correctness (graceful,
   silent fallback — no hard dependency).

### Requirement 4: Semantic World Objects with full observation metadata (PHASE 5 — Perception)

**User Story:** As a reasoning layer, I want every observation to be a semantic World
Object carrying its own confidence and provenance, so that decisions are grounded and
source-agnostic.

#### Acceptance Criteria

1. THE Perception_Stack SHALL represent each observation as a World_Object carrying:
   confidence, freshness, evidence, source, bounding region, and possible affordances.
2. THE World_Object SHALL be application-agnostic and SHALL NOT embed browser- or
   site-specific fields.
3. WHEN two sources observe the same object, THE Perception_Stack SHALL retain the
   higher-ranked source's World_Object (per SourcePriority) while preserving that the
   object was corroborated.
4. THE freshness of a World_Object SHALL follow the A2.1 World Model freshness contract
   (decays with age; stale objects are downgraded, never silently trusted).

### Requirement 5: Least-invasive Motor preference order (PHASE 5 — Motor)

**User Story:** As the Motor System, I want to prefer the least-invasive reliable
interaction, so that actions are robust and minimally disruptive.

#### Acceptance Criteria

1. WHEN more than one interaction method can accomplish an action, THE Motor_System
   SHALL attempt them in Motor_Preference_Order: Keyboard → Accessibility Actions →
   Mouse → Pixel fallback.
2. WHERE an Accessibility Action can perform an interaction on a resolved element, THE
   Motor_System SHALL prefer it over raw mouse coordinates.
3. WHERE no semantic (keyboard/accessibility) method resolves the target, THE
   Motor_System SHALL fall back to mouse, and only then to pixel-coordinate interaction.
4. THE Motor_System SHALL select the interaction method from the resolved World_Object
   and target, using no browser- or application-specific branching (Axiom_15).

### Requirement 6: Exploration for unidentified elements (PHASE 5 — Exploration)

**User Story:** As the operator facing an unfamiliar UI, I want to explore safely
rather than guess, so that I can act on interfaces I have not seen before without
application-specific heuristics.

#### Acceptance Criteria

1. IF an interface element required for the current step cannot be identified with
   sufficient confidence, THEN THE operator SHALL invoke the Exploration_Engine rather
   than acting on a low-confidence guess.
2. THE Exploration_Engine SHALL proceed as Observe → generate interaction hypotheses →
   execute safe experiments → verify outcome → update the World Model.
3. THE Exploration_Engine SHALL use no application-, browser-, or site-specific
   heuristics (Axiom_15).
4. WHEN exploration changes what is known about the environment, THE operator SHALL
   update the World Model with the verified outcome before continuing.

### Requirement 7: Verified success via World-Model change (PHASE 5 — Verification)

**User Story:** As a verification engineer, I want success measured by observable change,
so that no interaction is ever assumed successful merely because an input was sent.

#### Acceptance Criteria

1. WHEN an interaction completes, THE operator SHALL determine success only from an
   observed change in the WorldState / World Model.
2. THE operator SHALL NOT record Verified_Success for a step solely because an input
   (keystroke, click, navigation command) was dispatched.
3. WHERE an expected World-Model change is not observed after an interaction, THE
   operator SHALL treat the step as unverified and eligible for repair or exploration.

### Requirement 8: Browser-independence benchmark suite (PHASE 4)

**User Story:** As a governance reviewer, I want a benchmark suite proving browser
independence with CDP disabled, so that the milestone's claim is measured, not asserted.

#### Acceptance Criteria

1. THE benchmark suite SHALL include browser-independence benchmarks executed with
   CDP_Optimization DISABLED.
2. THE benchmark suite SHALL cover Chrome, Edge, Firefox, Brave, and at least one
   Electron application as target environments.
3. FOR each target browser, THE benchmark suite SHALL measure: launch application,
   navigate, search, login flow, file upload, download verification, multi-tab
   handling, dynamic page interaction, infinite scroll, unexpected dialog handling, and
   browser crash recovery.
4. THE benchmark suite SHALL score each capability via the Evidence Law (observed
   evidence), never by self-report.
5. THE benchmark definitions SHALL be domain-general (goal text names a capability,
   never a specific site), consistent with the existing capability-benchmark contract.
6. WHEN the browser-independence benchmarks run on a real machine with CDP disabled,
   THE results SHALL be recorded honestly (measured/unmeasured) and MUST NOT fabricate
   scores for environments not actually exercised.

### Requirement 9: Formal specification and FAS traceability

**User Story:** As a maintainer, I want a formal milestone spec and FAS alignment, so
that M23 is reviewable and traceable.

#### Acceptance Criteria

1. THE milestone SHALL provide a specification covering objectives, architectural
   rationale, dependencies, modified subsystems, runtime contracts, acceptance criteria,
   rollback strategy, benchmarks, risks, and FAS traceability.
2. THE architecture documentation SHALL rename "Browser Runtime" to "Web Environment
   Runtime" and record the rename as a FAS amendment.
3. THE specification SHALL trace each requirement to the FAS chapter(s)/amendment(s) it
   amends (Ch 23 Environments, Ch 30 Desktop Runtime, Ch 12 Observation, Ch 24
   ActionResult, Ch 25/66 Exploration/A2.8, Ch 31 Motor, Ch 32 Verification, A2.1, A2.2).

### Requirement 10: Rollback safety and regression protection

**User Story:** As an operator of a running system, I want M23 to be reversible and
non-regressing, so that inverting the browser default cannot silently break existing
behavior.

#### Acceptance Criteria

1. THE CDP-first behavior SHALL be restorable by a single configuration switch
   (re-enabling CDP_Optimization as default) without code changes, defining the
   rollback path.
2. WHEN the full test suite runs after M23, THE suite SHALL pass with no fewer green
   tests than before M23, with new tests placed in new files.
3. WHERE a pre-existing test asserts CDP-first behavior or `DesktopChromeController`,
   THE test SHALL be updated to the corrected contract and the change recorded in the
   change notes.
4. THE committed competence baseline seed SHALL remain all-unmeasured; any measured
   browser-independence scores SHALL be recorded only to `baseline.local.json`.
5. WHEN the Ratchet evaluates the post-M23 run, THE Ratchet SHALL report PASS with no
   regression to previously measured domains.

### Requirement 11: Determinism, safety, and honest measurement

**User Story:** As a maintainer, I want M23's logic to be deterministic and its claims
evidence-backed, so that tests need no live calls and no result is fabricated.

#### Acceptance Criteria

1. THE perception-fusion and motor-selection decisions SHALL be pure functions of the
   observed WorldState and target, using no clock-dependent or random branching for the
   selection outcome.
2. WHEN M23 unit and property tests run, THEY SHALL exercise perception fusion, motor
   selection, controller surface, and strategy resolution without live network, model,
   or GUI calls (injected/simulated sensors and a dry-run motor backend).
3. THE operator SHALL never report a capability score it did not measure; unexercised
   browsers/capabilities SHALL be reported as unmeasured.
4. THE M23 changes SHALL preserve public method signatures where behavior is not the
   target of the change, and SHALL keep existing production defaults except the
   deliberate CDP-first → desktop-first inversion (Requirement 3.4).

## Property-to-Requirement Mapping

| # | Testable Property | Type | Requirement(s) |
|---|-------------------|------|----------------|
| a | Executor builds a fused WorldState (UIA→OCR→Vision→pixels) for any active window, source-ranked, with no app/title branching | Invariant | 1.1, 1.2, 1.4 |
| b | A non-empty WorldState is produced from the desktop stack with no CDP controller present | Invariant | 1.3, 3.2 |
| c | Planner/executor consume World_Objects without depending on the producing source | Invariant | 1.5, 4.2 |
| d | DesktopBrowserController exposes the full duck-typed surface and contains no browser-name/window-title/OCR-only branch | Invariant / Structural | 2.1, 2.2, 2.4, 2.5 |
| e | Navigation path is identical across browsers (focus→address shortcut→type→commit), affordance-driven | Metamorphic | 2.3, 2.5 |
| f | With CDP disabled the operator completes a browser task; with CDP enabled the verdict + evidence kinds are identical | Model-based / Equivalence | 3.1, 3.2, 3.3, 3.5 |
| g | Strategy resolution returns DESKTOP_CONTROL by default; CDP only when explicitly enabled | Invariant | 3.4, 11.4 |
| h | Every World_Object carries confidence, freshness, evidence, source, bbox, affordances; freshness decays per A2.1 | Invariant | 4.1, 4.3, 4.4 |
| i | Motor selection follows Keyboard→Accessibility→Mouse→Pixel and prefers accessibility over raw coords | Ordering invariant | 5.1, 5.2, 5.3, 5.4 |
| j | Low-confidence target triggers Observe→hypothesize→experiment→verify→update, no app-specific heuristics | Invariant | 6.1, 6.2, 6.3, 6.4 |
| k | Step success is set only on observed WorldState change, never on input dispatch alone | Invariant / Error condition | 7.1, 7.2, 7.3 |
| l | Benchmark suite defines the required capabilities per browser, domain-general, Evidence-Law scored, CDP disabled | Measurable acceptance | 8.1–8.6 |
| m | Perception fusion + motor selection are pure/deterministic; tests need no live calls | Invariant | 11.1, 11.2 |
| n | Full suite green; ratchet PASS; seed stays unmeasured; rollback switch restores CDP-first | Regression / Process | 10.1–10.5 |
| o | No fabricated scores; unexercised targets reported unmeasured | Honesty | 8.6, 11.3 |

## FAS Traceability

| Requirement | FAS chapter / amendment |
|-------------|-------------------------|
| 1 (Universal Perception) | Ch 12 (Observation), Ch 30 (Desktop Runtime), A2.2 (Environment fingerprint inputs) |
| 2 (DesktopBrowserController) | Ch 23 (EnvironmentContract), Ch 30, Axiom 15 / Ch 63 |
| 3 (Browser Independence) | Ch 23, Ch 29 (Web Environment Runtime, renamed), Ch 52 (kernel-mediated) |
| 4 (World Objects) | Ch 12, A2.1 (freshness/provenance) |
| 5 (Motor preference) | Ch 31 (Motor System), Ch 24 (ActionResult) |
| 6 (Exploration) | Ch 25/66, A2.8 (Exploration Engine) |
| 7 (Verified success) | Ch 32 (Verification), Axiom 5 / 4th law (evidence over assertion) |
| 8 (Benchmarks) | Ch 28 (Competence scoring), A2.9 |
| 9 (Spec + rename) | Ch 29 rename → Web Environment Runtime; constitution amendment |
| 10, 11 (Rollback, determinism, honesty) | Axiom 15, Axiom 5, Ch 28.20 (no LLM-asserted competence) |
