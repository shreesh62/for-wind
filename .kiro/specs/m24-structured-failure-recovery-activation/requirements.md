# Requirements Document

M24 — Structured Failure Taxonomy & Verification-Event Activation

## Introduction

M24 implements audit architectural objectives 1–4 (structured error model, unified
observability, failure classification, recovery framework) by activating the existing
but **dormant** failure→recovery/competence/reflection loop and formalizing failures as
first-class objects. It reuses existing mechanisms (`FailureClass`, `RecoveryEngine`,
`CompetenceModel`, the kernel event system) and introduces no duplicate systems.

## Glossary

- **FailureDomain**: the stage/subsystem a failure originated in (perception, resource,
  environment, capability, verification, planning, execution, external service).
- **FailureClass**: the *existing* recoverability taxonomy (transient/precondition/…),
  reused unchanged.
- **verification.completed**: the kernel event the recovery/competence/reflection
  subsystems already subscribe to; previously never published.
- **StructuredFailure**: a first-class failure object with domain, severity, confidence,
  recoverability, recommended recovery, and evidence.

## Requirements

### Requirement 1: Structured error model

**User Story:** As an operator architecture, I want a canonical failure-domain taxonomy
derived from existing error categories, so failures are classifiable without rewriting
every producer.

#### Acceptance Criteria
1. WHEN `classify_error_category` receives any string THEN THE system SHALL return a
   `FailureDomain` (a total function; unknown/empty ⇒ `UNKNOWN`).
2. THE classifier SHALL map every existing free-form `error_category` value to a
   non-`UNKNOWN` `FailureDomain`.
3. THE classifier SHALL contain no application/site/browser-specific branching (Axiom
   15) — it is a data map over generic category tokens.

### Requirement 2: First-class failure objects

**User Story:** As a recovery/observability consumer, I want failures represented as
structured objects carrying domain, severity, confidence, recoverability, recommended
recovery path, and evidence.

#### Acceptance Criteria
1. THE `StructuredFailure` SHALL carry domain, severity, category, message, confidence,
   recoverable, recommended_recovery, goal_id, capability, environment, requirement, and
   evidence.
2. WHEN built from an `ActionResult` or a `RequirementVerdict` THEN THE constructor
   SHALL never raise and SHALL default missing fields safely.
3. THE `StructuredFailure` SHALL expose a JSON-serializable `to_payload()`.

### Requirement 3: Verification-event producer (recovery activation)

**User Story:** As the FRIDAY kernel, I want verdicts published as `verification.completed`
events so the recovery, competence, and reflection subsystems actually react.

#### Acceptance Criteria
1. WHEN a publisher is attached to a kernel AND a verdict is published THEN THE system
   SHALL emit a `verification.completed` event with the payload fields the existing
   subscribers read (goal_id, satisfied, requirement, evidence, capability, environment,
   reversible, blocked, competence).
2. IF no kernel is attached THEN publishing SHALL be a silent no-op that never raises.
3. WHEN a real `RecoveryEngine` is attached to the same kernel AND a failed verdict is
   published THEN THE system SHALL cause a `recovery.proposed` event to be emitted
   (the dormant loop is activated).

### Requirement 4: Observability as an event consumer

**User Story:** As an operator, I want failures logged through structured records driven
by the event system, not scattered prints.

#### Acceptance Criteria
1. WHEN a `verification.completed` (failure) or `recovery.proposed` event is published
   THEN THE `FailureLogSubscriber` SHALL emit exactly one structured log record.
2. THE log record SHALL carry subsystem id, goal id, correlation id, logical time, and
   failure domain in structured fields.
3. THE log level SHALL derive from severity, and the subscriber SHALL never raise into
   the event bus.

### Requirement 5: Additive, safe production wiring

**User Story:** As the maintainer, I want M24 to change no production default and no
behavior when a kernel is not injected.

#### Acceptance Criteria
1. WHEN the `Operator` is constructed without a kernel THEN behavior SHALL be identical
   to pre-M24 (no events, full regression green).
2. WHEN the `Operator` is constructed with a kernel THEN each requirement verdict SHALL
   be published as a `verification.completed` event.
3. THE full existing test suite SHALL remain green (no regressions).
