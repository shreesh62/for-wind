# Requirements Document

M15 — World Model v2 (Belief Freshness, TTL, Provenance, Staleness)

## Introduction

M15 implements the normative World Model expansions specified in FAS v2.1 §A2.1. It extends the
existing `Belief` and `WorldModel` primitives with first-class freshness scoring, per-class TTL and
refresh policies, a composable provenance/evidence graph, and a staleness sweep that flags high-impact
stale beliefs before they gate irreversible actions. The target competence domains are research and
long-horizon execution, both of which depend on trustworthy, explainable beliefs whose age and origin
are transparent.

All changes are additive: existing `Belief` and `WorldModel` public APIs remain backward-compatible,
no production defaults change, and the full regression suite continues to pass.

## Glossary

- **Belief**: a confidence-weighted, probabilistic statement about reality held by the World Model.
- **Freshness**: a `[0, 1]` score representing how current a belief is, decaying via half-life from
  the moment of observation (`0.5 ** (age / half_life)`).
- **TTL (Time-To-Live)**: the maximum number of seconds a belief may live before it transitions to the
  `stale` state.
- **Stale belief**: a belief whose age exceeds its TTL or whose freshness has decayed below the
  configured staleness threshold.
- **Refresh_Policy**: the strategy for refreshing a stale belief; one of `on_read`, `on_stale`,
  `periodic`, or `never`.
- **Refresh_Cost**: a dimensionless `[0, 1]` cost estimate representing the expense of re-acquiring a
  belief from its source.
- **Provenance**: the recorded origin and derivation chain of a belief — supporting observations,
  contradicting observations, parent beliefs from which the belief was derived, and verification status.
- **Evidence_Graph**: the directed acyclic structure linking a belief to its supporting and
  contradicting observations, plus any parent beliefs it was derived from.
- **Derivation_Chain**: the ordered sequence of parent belief IDs from which a derived belief was
  computed.
- **Verification_Status**: one of `unverified`, `verified`, or `contradicted`, indicating whether a
  belief has been independently confirmed.
- **High_Impact_Belief**: a belief that gates an irreversible action (impact classification provided by
  the caller/planner).
- **World_Model**: the kernel-owned probabilistic world representation fed by sensor events.
- **KnowledgeAging**: the M9 temporal aging component whose half-life decay formula this milestone
  reuses.
- **Kernel_Event**: the sole communication channel; World Model receives observations and emits
  staleness notifications only through kernel events.

## Requirements

### Requirement 1: Belief Freshness Scoring

**User Story:** As the planner, I want every belief to carry a computable freshness score, so I can
quantify how current a belief is and prefer refreshing stale beliefs over trusting them.

#### Acceptance Criteria

1. THE Belief SHALL carry a `freshness(now)` method computed as `0.5 ** ((now - observed_at) / half_life_seconds)` and clamped to `[0, 1]`.
2. WHEN `now` equals `observed_at`, THE Belief freshness SHALL equal `1.0`.
3. WHEN `now` exceeds `observed_at` by exactly one `half_life_seconds`, THE Belief freshness SHALL equal `0.5` (within floating-point epsilon).
4. WHEN `now` is less than `observed_at` (clock skew or replay), THE Belief freshness SHALL be clamped to `1.0`.
5. THE Belief freshness computation SHALL delegate to `KnowledgeAging.freshness(observed_at, now)` from `friday/temporal/aging.py` (M9 precedent) rather than re-implementing the decay formula.
6. WHEN a Belief is reinforced with a new observation, THE returned Belief SHALL have `observed_at` reset to the observation time so that freshness returns to `1.0` at that moment.
7. THE Belief SHALL carry a configurable `half_life_seconds` field of type `float` defaulting to `86400.0` (one day), with values ≤ 0 treated as "instantly stale" (freshness = 0.0 for any `now > observed_at`).
8. THE freshness method SHALL accept `now` as an explicit `float` argument and SHALL NOT call `time.time()` internally, ensuring determinism and replay-safety under `FRIDAY_DRY_RUN=1`.

### Requirement 2: TTL and Refresh Policy

**User Story:** As the planner, I want each belief class to declare a TTL and refresh policy, so the
system knows when beliefs expire and how to refresh them.

#### Acceptance Criteria

1. THE Belief SHALL carry a `ttl_seconds` field of type `Optional[float]` representing the maximum age in seconds before the belief becomes stale, where a non-None value must be greater than 0.
2. WHEN a Belief's age (`now - observed_at`) exceeds `ttl_seconds`, THE World_Model SHALL classify the Belief as stale.
3. THE Belief SHALL carry a `refresh_policy` field accepting exactly one of: `on_read`, `on_stale`, `periodic`, `never`.
4. THE Belief SHALL carry a `refresh_cost` field as a float in the inclusive range `[0.0, 1.0]` representing the expense of re-acquiring the belief, clamped to `[0.0, 1.0]` on assignment.
5. WHILE a Belief is stale, THE World_Model SHALL NOT include the Belief in query results as current knowledge unless it has been refreshed; if refresh fails, the Belief SHALL remain marked stale.
6. WHEN `refresh_policy` is `never`, THE World_Model SHALL classify the Belief as stale once TTL is exceeded but SHALL NOT initiate a refresh action.
7. IF `ttl_seconds` is `None`, THEN THE Belief SHALL be treated as non-expiring and SHALL NOT transition to stale based on TTL alone (freshness decay via half-life still applies).
8. IF a Belief has both `ttl_seconds` exceeded (stale) and `expires_at` exceeded (hard expiry), THEN THE World_Model SHALL treat the Belief as expired rather than stale, and SHALL NOT attempt refresh regardless of `refresh_policy`.
9. WHEN `refresh_policy` is `on_read` and a stale Belief is queried, THE World_Model SHALL signal a refresh is needed; WHEN `refresh_policy` is `on_stale`, THE World_Model SHALL signal refresh upon staleness detection; WHEN `refresh_policy` is `periodic`, THE World_Model SHALL signal refresh at intervals equal to `ttl_seconds`.

### Requirement 3: Belief Provenance and Evidence Graph

**User Story:** As the maintainer, I want every belief to record its provenance — supporting
observations, contradicting observations, derivation chain, and verification status — so the World
Model can explain WHY it believes something.

#### Acceptance Criteria

1. THE Belief SHALL carry a `provenance` structure containing: `supporting_observations` (list of observation IDs), `contradicting_observations` (list of observation IDs), `derivation_chain` (list of parent belief IDs, maximum 20 entries), and `verification_status`.
2. WHEN a Belief is derived from one or more parent beliefs, THE Belief provenance SHALL record every parent belief ID in `derivation_chain`, preserving insertion order from root ancestor to immediate parent.
3. WHEN a supporting observation is added, THE Belief provenance SHALL append the observation ID to `supporting_observations` and SHALL set `verification_status` to `verified` if it was previously `unverified`.
4. WHEN a contradicting observation is added, THE Belief provenance SHALL append the observation ID to `contradicting_observations`.
5. THE Belief `verification_status` SHALL be one of: `unverified`, `verified`, `contradicted`. `unverified` is the initial state for newly created beliefs.
6. IF a Belief has at least one entry in `contradicting_observations` and zero entries in `supporting_observations`, THEN THE Belief verification_status SHALL be `contradicted`.
7. THE Evidence_Graph SHALL be a directed acyclic graph: no belief's derivation_chain SHALL contain its own ID (no self-reference), and no derivation cycle SHALL exist.
8. WHEN a Belief is derived from other beliefs, THE provenance model SHALL record the full ordered derivation_chain from root to immediate parent, enabling traversal of the complete ancestor path in a single lookup without recursive queries.
9. THE Belief provenance structure SHALL coexist with the legacy `supporting_evidence` and `contradicting_evidence` fields: adding an observation ID to provenance `supporting_observations` SHALL also append it to the legacy `supporting_evidence` field, and vice versa for contradicting.
10. WHILE the WorldModel is ingesting observations or updating provenance, THE system SHALL hold the existing RLock for the entire read-modify-write sequence, ensuring no concurrent mutation produces an inconsistent provenance state.

### Requirement 4: Staleness Sweep and High-Impact Flagging

**User Story:** As the planner, I want to query all stale beliefs and have high-impact stale beliefs
flagged before they gate irreversible actions, so no critical decision relies on outdated information.

#### Acceptance Criteria

1. THE World_Model SHALL expose a `stale_beliefs(now)` method that returns a list of Belief objects whose age (`now - observed_at`) exceeds their `ttl_seconds`, or whose freshness is strictly below the configured staleness threshold (default `0.1`, configurable at World_Model construction).
2. WHEN `stale_beliefs(now)` is called, THE World_Model SHALL recompute freshness at `now` for each belief using `KnowledgeAging.freshness(observed_at, now)` rather than relying on any previously cached freshness values.
3. WHEN a Belief has its `high_impact` field set to `True` and is stale, THE World_Model SHALL flag the Belief for refresh by including it in the results and emitting a kernel event.
4. WHEN a high-impact Belief is flagged as stale, THE World_Model SHALL emit a `belief.stale_flagged` Kernel_Event containing the belief ID and the belief's current computed freshness value in the event payload.
5. WHEN no beliefs have age exceeding their `ttl_seconds` and no beliefs have freshness below the staleness threshold, THE `stale_beliefs(now)` method SHALL return an empty list.
6. WHILE executing the `stale_beliefs(now)` scan, THE World_Model SHALL hold the existing `threading.RLock` for the entire duration of the scan to ensure thread-safe iteration over the belief collection.
7. IF a Belief has `ttl_seconds` of zero or negative, THEN THE World_Model SHALL treat that belief as immediately stale for any `now` greater than `observed_at`.

### Requirement 5: Backward Compatibility and Regression Safety

**User Story:** As the maintainer, I want M15 to extend existing primitives additively without breaking
existing callers or failing any existing test.

#### Acceptance Criteria

1. WHEN M15 is implemented, THE existing Belief public API (`decay`, `reinforce`, `contradict`, `expired` property, and all existing fields: `description`, `confidence`, `source`, `id`, `observed_at`, `expires_at`, `supporting_evidence`, `contradicting_evidence`, `dependencies`, `last_updated`) SHALL retain identical method signatures, parameter defaults, and return types.
2. WHEN M15 is implemented, THE existing WorldModel public API (`ingest`, `observed_world`, `unmet_conditions`, `relate`, `attach`) SHALL retain identical method signatures, parameter defaults, and return types (including `ingest` returning `List[Belief]`).
3. WHEN M15 adds new fields to the Belief dataclass, EACH new field SHALL have a default value so that existing construction `Belief(description=..., confidence=..., source=...)` continues to succeed without passing the new fields.
4. WHEN `reinforce()` or `contradict()` returns a new Belief via `dataclasses.replace()`, THE returned Belief SHALL preserve any M15-added field values from the original instance unchanged.
5. WHEN the full test suite runs under `FRIDAY_DRY_RUN=1`, THE pre-existing tests (minimum 1245) SHALL report zero failures and zero errors, and M15 SHALL only add new test files or new test functions without modifying existing test assertions.
6. THE M15 implementation SHALL NOT change any existing default parameter value in the Belief or WorldModel constructors or method signatures.
7. THE M15 implementation SHALL NOT introduce application-specific logic (Axiom 15): all new functions and classes SHALL operate on domain-agnostic primitives (Belief, Observation, WorldObject).
8. WHEN M15 modules are added, EACH module SHALL carry a module-level docstring and SHALL match existing codebase style.
9. THE WorldModel SHALL remain a single instance per Kernel, communicating with other subsystems exclusively through events published and subscribed on the Kernel event bus.

### Requirement 6: Thread Safety and Determinism

**User Story:** As the kernel operator, I want freshness, provenance, and staleness operations to be
thread-safe and deterministic given the same inputs.

#### Acceptance Criteria

1. WHILE the World_Model RLock is held by one thread for a mutating operation (ingest or relate), THE freshness computation and staleness sweep invoked by a different thread SHALL block until the lock is released, and SHALL acquire the same RLock before reading belief state.
2. WHEN the same `now` and `observed_at` values are provided to a freshness computation, THE computation SHALL return a bit-identical `float` result regardless of calling thread, invocation count, or wall-clock time.
3. THE freshness computation and staleness sweep SHALL accept `now` as an explicit `float` argument and SHALL NOT call `time.time()` or any system clock function internally, ensuring replay-safety under `FRIDAY_DRY_RUN=1`.
4. THE staleness sweep SHALL be idempotent: calling `stale_beliefs(now)` N times (N ≥ 2) with the same beliefs and `now` value SHALL return a list containing the same elements in the same order on every invocation.
5. WHILE a thread holds the World_Model RLock via reentrant acquisition (same thread entering a nested lock scope), THE system SHALL permit the reentrant call to proceed without deadlock.
6. WHEN concurrent threads invoke freshness computation and staleness sweep simultaneously on overlapping belief sets, THE system SHALL produce results consistent with some serial ordering of those operations (linearizability at the lock boundary).
