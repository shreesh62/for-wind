# Requirements Document

M21 (slice 1) — Failure Memory

## Introduction

The v2.1 traceability matrix marks **A2.11 Failure memory** as *Absent*. This milestone
delivers it as the seventh memory tier: a persistent, queryable memory of failures that
CONSUMES the M24 failure→recovery loop (`verification.completed` + `recovery.proposed`
events) so past failures — and the recoveries proposed for them — inform future planning
instead of being silently repeated. It reuses the existing bounded `JSONFileStore` and
the M24 `StructuredFailure` model (no duplicate systems). The broader seven-tier memory
expansion (Reflection v2 / Retrieval Router integration) is out of scope for this slice.

## Glossary

- **Failure Memory**: the seventh memory tier — a persistent, queryable record of failures.
- **FailureRecord**: one remembered failure (requirement/domain/capability/recovery info).
- **StructuredFailure**: the M24 first-class failure object this tier consumes.
- **verification.completed / recovery.proposed**: the M24 kernel events this tier subscribes to.

## Requirements

### Requirement 1: Record failures

**User Story:** As the operator, I want failures persisted so I can learn from them.

#### Acceptance Criteria
1. THE `FailureMemory` SHALL record a failure carrying requirement, domain, category,
   capability, environment, goal_id, severity, message, and recoverability.
2. WHEN given an M24 `StructuredFailure` THEN THE system SHALL record it directly
   (`record_structured`).
3. Storage SHALL be bounded (oldest evicted beyond a max) — no unbounded growth.

### Requirement 2: Consume the failure→recovery loop

**User Story:** As the FRIDAY kernel, I want failure memory to react to verdicts and
recoveries automatically.

#### Acceptance Criteria
1. WHEN attached to a kernel AND a `verification.completed` failure is published THEN
   THE system SHALL record a failure; a satisfied verdict SHALL NOT be recorded.
2. WHEN a `recovery.proposed` event follows for the same goal THEN THE system SHALL
   annotate the recorded failure with the recovery class and whether it was actionable.
3. THE event handlers SHALL never raise into the event bus (malformed events ignored).

### Requirement 3: Query failure history

**User Story:** As planning/deliberation, I want to ask whether we have failed at
something before and see the distribution of failures.

#### Acceptance Criteria
1. THE system SHALL answer `has_failed_before(requirement, capability?, environment?)`.
2. THE system SHALL `recall(...)` recent failures filtered by capability/environment/domain.
3. THE system SHALL report `failure_count(...)` and `statistics()` (totals + by-domain
   distribution + count with actionable recovery).

### Requirement 4: Additive, safe integration

**User Story:** As the maintainer, I want failure memory wired safely so it changes no
default behavior and never breaks hermetic tests.

#### Acceptance Criteria
1. Failure memory SHALL be opt-in in `attach_reactive_loop` (attached only when supplied)
   so hermetic tests/benchmarks never write files unbidden.
2. THE production bootstrap SHALL attach a bounded `FailureMemory` when kernel execution
   is enabled.
3. THE full existing test suite SHALL remain green.
