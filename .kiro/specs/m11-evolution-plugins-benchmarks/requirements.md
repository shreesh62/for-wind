# Requirements Document

M11 — Capability Evolution, Plugins, Benchmarks & Federation

## Introduction

M11 gives FRIDAY the ability to **safely extend its own competence, measure whether it is improving,
load competence it did not ship with, and run one mind across more than one machine** (FAS Ch 27, 47,
54, 55, 57). Every mechanism wraps existing seams — the M7 `CapabilityCandidate`, the
`CapabilityRegistry.promote_candidate` seam, the M8 `CompetenceModel`, and the M4 `ResourceRegistry` —
and communicates only through kernel events (Ch 52). The binding constraints (HANDOFF Section 12/13,
Axiom 15, Ch 27.23, Ch 54.5): evolution never bypasses benchmarks or safety; plugins never touch the
kernel, world, goals, safety, or verification directly; federation transmits only resource descriptors,
never code or secrets; and nothing hardcodes an application or site name. Frontends (Ch 57) are scoped
to a documented kernel-API client contract only (no UI built in M11).

## Glossary

- **Capability lifecycle**: the ordered states a capability moves through — `DRAFT → EXPERIMENTAL →
  VERIFIED → STABLE → DEPRECATED → ARCHIVED` — with sanctioned rollback.
- **CapabilityCandidate**: a duck-typed proposal (`proposed_id`, `affordance`, `procedure`,
  `confidence`) distilled by exploration or a plugin; the sole input to promotion.
- **Promotion pipeline**: the `candidate → sandbox → benchmark → promote` process; the only path a
  capability enters the registry through evolution.
- **Benchmark**: a goal-completion scenario set (not token metrics) producing a bounded `[0,1]` score.
- **Regression**: a candidate scoring below the incumbent capability's score (beyond tolerance).
- **Rollback**: restoring the last-known-good capability snapshot after a promotion underperforms.
- **Plugin**: an externally supplied manifest of proposed capabilities, adopted through the same
  lifecycle + safety gates; never a direct registry write.
- **Federated node**: a remote machine exposing `Resource` descriptors (not applications) into the
  local `ResourceRegistry`.
- **Protected subsystem**: `kernel`, `world`, `goals`, `safety`, `verification` — never accessible to a
  plugin.

## Requirements

### Requirement 1: Capability lifecycle & rollback (Ch 27)

**User Story:** As FRIDAY, I want every capability to move through a disciplined lifecycle with
rollback, so that competence grows without ever regressing permanently or using unproven capabilities
for dangerous work.

#### Acceptance Criteria

1. WHEN a capability transition is requested THEN the system SHALL permit it only if it is a legal
   forward step (`DRAFT → EXPERIMENTAL → VERIFIED → STABLE`), a deprecation/archival, or a sanctioned
   rollback, and SHALL raise on any illegal transition leaving state unchanged.
2. WHEN a capability's state is queried THEN the system SHALL return exactly one `LifecycleState`,
   defaulting to `DRAFT` for an unseen capability.
3. WHEN a capability is in `DRAFT` or `EXPERIMENTAL` THEN the system SHALL report it NOT usable for an
   `irreversible`-risk action; `VERIFIED`/`STABLE` capabilities MAY be usable.
4. WHEN a stable snapshot was recorded before a promotion THEN `rollback` SHALL return that snapshot and
   mark the current version reverted; WHEN no snapshot exists `can_rollback` SHALL be False and
   `rollback` SHALL raise.

### Requirement 2: Benchmark-gated promotion (Ch 27, 55)

**User Story:** As FRIDAY, I want promotion gated on measured goal completion, so that I only adopt
capabilities that demonstrably work and never one that regresses what I already have.

#### Acceptance Criteria

1. WHEN a candidate is benchmarked THEN the system SHALL compute a weighted goal-completion score in
   `[0,1]` equal to `passed_weight / total_weight` (0.0 when no scenarios run), deterministic for a
   deterministic evaluator.
2. WHEN a candidate's benchmark score is below `min_benchmark_score` THEN the system SHALL return
   `REJECTED` and SHALL NOT change the `CapabilityRegistry` capability count.
3. WHEN an incumbent capability exists THEN a candidate scoring below the incumbent (beyond tolerance)
   SHALL be classified a regression and `REJECTED`.
4. WHEN regression is evaluated THEN `is_regression(incumbent, candidate)` SHALL be monotonic — a lower
   candidate score is never less likely to be flagged than a higher one.
5. WHEN a candidate passes the benchmark and does not regress THEN the system SHALL promote it via
   `CapabilityRegistry.promote_candidate`, advance its lifecycle, and emit `capability.promoted`.

### Requirement 3: Plugins adopted through the same gates (Ch 54)

**User Story:** As FRIDAY, I want externally supplied capabilities to enter through the same lifecycle,
benchmark, and safety gates as evolved ones, so that plugins can never subvert the architecture.

#### Acceptance Criteria

1. WHEN a plugin manifest is loaded THEN its declared capabilities SHALL become `CapabilityCandidate`s
   routed through the `PromotionPipeline`, never written to the registry directly.
2. WHEN a plugin manifest requests access to a protected subsystem (`kernel`, `world`, `goals`,
   `safety`, `verification`) THEN the sandbox SHALL reject it with a reason and load nothing.
3. WHEN a plugin manifest requests only non-protected permissions THEN the sandbox SHALL accept it.
4. WHEN a plugin is installed THEN the system SHALL NOT call `CapabilityRegistry.register` or
   `promote_candidate` from within the plugin subsystem — candidates flow only through the pipeline.
5. IF a plugin manifest is malformed or unsigned THEN `load` SHALL return a `LoadFailure` and install
   nothing.

### Requirement 4: Resource federation (Ch 47)

**User Story:** As FRIDAY, I want to federate the resources of other machines into one resource
registry, so that a single goal graph can be advanced across devices without transmitting code or
secrets.

#### Acceptance Criteria

1. WHEN a node joins THEN the system SHALL register each of its `Resource` descriptors into the
   `ResourceRegistry` with ids namespaced by `node_id`, and emit `federation.node_joined`.
2. WHEN a node leaves THEN the system SHALL unregister exactly the resources it added and emit
   `federation.node_left`.
3. WHEN a node joins and then leaves THEN the `ResourceRegistry` SHALL contain exactly the resources it
   held before the join (join-then-leave is identity).
4. WHEN a `FederatedNode` is transmitted THEN it SHALL carry only `Resource` value descriptors — no
   code object, callable, or secret.
5. WHEN healthy nodes are queried THEN `NodeDirectory.healthy_nodes` SHALL return exactly the nodes
   flagged healthy.

### Requirement 5: Isolation, conventions, and regression safety

**User Story:** As a FRIDAY maintainer, I want M11 to follow the established milestone conventions and
keep the suite green.

#### Acceptance Criteria

1. WHEN M11 modules are added THEN each SHALL carry a `"""Ch NN — ..."""` module docstring.
2. WHEN module imports are scanned THEN evolution SHALL NOT import plugin internals; plugins SHALL NOT
   import `friday.kernel.*`, `friday.world.*`, `friday.goals.*`, `friday.safety.*`, or
   `friday.verification.*`; federation SHALL import only `friday.resources.*`, `friday.events.*`, and
   stdlib.
3. WHEN the M11 file set is scanned THEN no banned application/site name SHALL appear in string literals
   (Axiom 15).
4. WHEN the M11 file set is scanned THEN no URL scheme literal SHALL appear in code lines (Axiom 15).
5. WHEN the full suite runs under `FRIDAY_DRY_RUN=1` THEN all pre-existing tests (≥ 1097) SHALL still
   pass and M11 SHALL add property, unit, isolation, integration, and gate tests.

## Property-to-Requirement Mapping

| Correctness Property (design.md) | Validates Requirements |
|---|---|
| P1 Lifecycle transitions are legal-only | 1.1, 1.2 |
| P2 Unverified capabilities cannot perform irreversible actions | 1.3 |
| P3 Promotion requires a passing benchmark | 2.1, 2.2 |
| P4 Promotion never regresses the incumbent | 2.3, 2.4 |
| P5 Benchmark score is a bounded weighted ratio | 2.1 |
| P6 Rollback restores the last-known-good snapshot | 1.4 |
| P7 Plugins cannot request protected subsystems | 3.2, 3.3 |
| P8 Plugin capabilities enter only through the pipeline | 3.1, 3.4 |
| P9 Federation namespaces resources and is reversible | 4.1, 4.2, 4.3 |
| P10 Federation transmits only resource descriptors | 4.4, 4.5 |
| P11 M11 modules hardcode no application or site name | 5.3, 5.4 |
