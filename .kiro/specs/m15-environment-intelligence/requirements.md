# Requirements Document

M15 — Environment Intelligence (Fingerprints & Capability Invalidation)

## Introduction

The v2.1 traceability matrix marks **A2.2 Environment Intelligence** as *Absent* on the
live path. FAS §A2.2 requires that each environment compute a **fingerprint** (from
application version, window class, accessibility signature, DOM signature, visual hash,
platform, capability version, layout version), that interactive surfaces carry a **UI
fingerprint**, that a **fingerprint change invalidates** learned assumptions/cached
affordances for that environment and triggers re-exploration (Ch 25), and that
capabilities record the fingerprint they were validated against so a mismatch lowers their
confidence for that environment (**version-aware adaptation**).

**Invariant (§A2.2):** a UI update makes FRIDAY re-explore, never silently wrong.

This milestone delivers Environment Intelligence as one **general** mechanism over the
existing universal perception (`friday/perception/active_window.py` → `WorldState`, which
already carries a screenshot/visual hash, UI-Automation elements, and window info from
M23). It introduces no application-, browser-, site-, or window-title-specific logic
(Axiom 15): a fingerprint is a pure, deterministic function of generic `WorldState`
signals. Change detection is event-driven on the kernel bus and, on a detected change,
emits an invalidation/re-explore signal that the existing Exploration Engine (A2.8, M7 —
Built) and competence model can consume. All new code is additive and inert without a
kernel; the default path is unchanged.

## Glossary

- **Environment fingerprint**: a stable, deterministic digest of an environment's current
  identity/version/layout, computed from generic `WorldState` + window signals.
- **UI fingerprint**: a digest of the interactive-surface structure (the set/shape of
  interactive World Objects), sensitive to layout changes.
- **Fingerprint change**: a differing fingerprint for the same environment key between two
  observations — the signal that the environment's identity/layout shifted.
- **Capability invalidation**: marking learned assumptions / cached affordances for an
  environment as stale so they are re-explored rather than silently reused.
- **Version-aware confidence**: a capability records the fingerprint it was validated
  against; a mismatch lowers its confidence for that environment.
- **Environment key**: the stable environment identifier (e.g. `EnvironmentContract.name`
  like `desktop.windows` / `browser.chrome.dedicated`) — never a site name.

## Requirements

### Requirement 1: Environment fingerprint

**User Story:** As FRIDAY, I want a stable fingerprint of the current environment so I can
tell when its identity or version changed.

#### Acceptance Criteria
1. THE system SHALL compute an `EnvironmentFingerprint` deterministically from a
   `WorldState` (and optional window info), incorporating available generic signals:
   platform, window class/kind, an accessibility-structure signature (from UI-Automation
   element kinds/roles), a visual hash (the existing screenshot hash), and an optional
   supplied capability/layout version.
2. THE fingerprint SHALL be a pure function of its inputs: identical inputs produce an
   identical digest; a change in any incorporated signal produces a different digest.
3. THE fingerprint SHALL never incorporate application-, site-, or window-title-specific
   identity as a special case (Axiom 15) — only generic structural/version signals.
4. THE fingerprint SHALL be JSON-projectable (digest + the component signals) for
   events/logging, and SHALL be computable from a sparse/partial `WorldState` without
   raising (a missing sensor simply omits that signal).

### Requirement 2: UI fingerprint

**User Story:** As FRIDAY, I want a fingerprint of the interactive surface so a changed
layout is detectable even when the environment identity is unchanged.

#### Acceptance Criteria
1. THE system SHALL compute a `ui_fingerprint` from the structure of interactive World
   Objects (their kinds/roles and count/shape), independent of their volatile text values.
2. A change to the interactive-surface structure SHALL change the UI fingerprint; a
   re-observation of the same layout SHALL produce the same UI fingerprint.
3. THE UI fingerprint SHALL be computable from a sparse `WorldState` without raising.

### Requirement 3: Change detection

**User Story:** As the FRIDAY kernel, I want fingerprint changes detected per environment
so downstream systems can react.

#### Acceptance Criteria
1. THE system SHALL maintain, per environment key, the last-seen fingerprint and SHALL
   report whether a newly-observed fingerprint differs (changed / unchanged / first-seen).
2. WHEN a change is detected for an environment key AND a kernel is present THEN THE system
   SHALL emit an `environment.fingerprint_changed` event carrying the environment key, the
   previous and current digests, and which component signals changed (JSON-safe).
3. THE first observation of an environment key SHALL be recorded as a baseline and SHALL
   NOT be reported as a change.
4. THE registry of last-seen fingerprints SHALL be bounded (oldest environment keys evicted
   beyond a cap) so memory never grows without limit.

### Requirement 4: Capability invalidation on change

**User Story:** As FRIDAY, I want a fingerprint change to invalidate stale assumptions so I
re-explore rather than act on outdated affordances.

#### Acceptance Criteria
1. WHEN an `environment.fingerprint_changed` event is emitted THEN THE system SHALL emit an
   invalidation signal (`environment.capabilities_invalidated`) for that environment key so
   the Exploration Engine (A2.8) / competence consumers can re-explore or re-validate,
   rather than silently reusing cached affordances.
2. THE invalidation signal SHALL be a proposal/notification only — this milestone SHALL
   NOT itself delete competence records or mutate the Exploration Engine; it emits the
   event that those subsystems consume (kernel-mediated, Ch 52).
3. THE invalidation payload SHALL be JSON-serializable (environment key + reason +
   changed signals) for replay compatibility.

### Requirement 5: Version-aware confidence adjustment

**User Story:** As Deliberation, I want a capability's confidence lowered when the
environment it was validated against no longer matches, so I do not over-trust stale skills.

#### Acceptance Criteria
1. THE system SHALL provide a pure function that, given a capability's validated
   fingerprint and the current fingerprint, returns a confidence multiplier in [0, 1]:
   `1.0` on a match and a reduced factor on a mismatch (larger structural divergence →
   lower factor).
2. THE function SHALL be total and deterministic (no raising; a missing validated
   fingerprint yields a defined neutral/penalized factor per policy).
3. THE adjustment SHALL be advisory (a multiplier the caller applies) — it SHALL NOT
   itself write competence; empirical competence remains evidence-derived (A2.9).

### Requirement 6: Event-driven, replay-safe integration

**User Story:** As the FRIDAY kernel, I want fingerprinting wired via events so it is
replay-compatible and safe.

#### Acceptance Criteria
1. EVERY emitted `environment.*` payload SHALL be JSON-serializable so the append-only
   `EventStore` stays replay-compatible.
2. THE change-detection component SHALL attach to a kernel via a single reusable wiring
   helper and SHALL be inert without a kernel (no-op).
3. THE component's handlers SHALL never raise into the event bus (malformed inputs ignored).

### Requirement 7: Additive, safe integration

**User Story:** As the maintainer, I want Environment Intelligence wired so it changes no
default behavior and never breaks hermetic tests.

#### Acceptance Criteria
1. Fingerprint computation SHALL be a pure library usable without a kernel; the
   change-detector SHALL be attached only within the guarded kernel-execution path.
2. THE default (flag-off) path SHALL be byte-unchanged in behavior; a wiring failure SHALL
   degrade safely without crashing bootstrap.
3. THE full existing test suite SHALL remain green (zero failures).

### Requirement 8: Verification artifacts

**User Story:** As the maintainer, I require every milestone to ship its evidence.

#### Acceptance Criteria
1. THE milestone SHALL include property/unit tests covering fingerprint determinism +
   sensitivity, UI-fingerprint layout sensitivity, change detection (first-seen/unchanged/
   changed + bounded registry), invalidation emission, version-aware confidence, isolation
   (no app-specific logic), and defensive handlers.
2. THE milestone SHALL include a deterministic, hermetic environment-intelligence benchmark
   (fingerprint stability/sensitivity + change-detection precision over synthetic
   WorldStates) that is NOT recorded into the committed competence baseline.
3. THE milestone SHALL update the FAS (A2.2 → Built), the traceability matrix, and produce
   an after-milestone architecture review, with a full-suite checkpoint (zero failures).
