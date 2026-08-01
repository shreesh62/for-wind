# Requirements Document

## Introduction

M25 completes Architecture v2.1 amendment A2.11 by placing Capability Memory and Preference Memory on the live path beside the existing Working, Episodic, Semantic, Procedural, and Failure tiers. This milestone continues the approved Architecture v2.1 roadmap and hardens the existing memory subsystem; it does not redesign the architecture, replace an existing tier, or create a second memory system. Capability Memory remains an evidence-derived view rather than a competence authority. Preference Memory records only explicit user evidence and does not infer sensitive or non-sensitive preferences from behavior. The milestone reuses the M19 Retrieval Router, existing kernel event stream, existing competence and lifecycle authorities, and existing JSON persistence abstraction.

The pre-M25 regression floor is **1677 passed, 0 failed**. Completion requires additive guarded production wiring, transaction-safe bounded persistence, replay-safe JSON integration, uniform retrieval, deterministic validation where appropriate, architecture traceability, an after-milestone review, and a zero-failure full-suite checkpoint. Browser and desktop cognition remain canonical, model and embedding operations remain NVIDIA-only, new degradation boundaries remain observable, committed baselines remain deterministic, and all workspace changes remain uncommitted.

## Glossary

- **Seven_Tier_Memory**: The single existing FRIDAY memory subsystem containing exactly the normative Working, Episodic, Semantic, Procedural, Capability, Failure, and Preference tiers.
- **Memory_Controller**: The existing `FridayMemory` composition root that owns or exposes the live memory tiers.
- **Capability_Memory**: The persistent, queryable memory view of evidence-backed capability status keyed by capability and environment; Capability Memory is not a competence, benchmark, lifecycle, or promotion authority.
- **Preference_Memory**: The persistent, queryable tier containing current user preferences supported by explicit user evidence.
- **Existing_Memory_Tier**: One of Working, Episodic, Semantic, Procedural, or Failure memory as implemented before M25.
- **Competence_Authority**: The existing evidence-only Competence Model that computes competence from verified outcomes.
- **Lifecycle_Authority**: The existing Capability Lifecycle state machine that owns lifecycle state and legal transitions.
- **Benchmark_Authority**: The existing benchmark framework that produces benchmark reports from executed scenarios.
- **Verified_Capability_Evidence**: A successful or failed capability outcome whose verdict was produced by the existing verification path and attributed to a capability and environment.
- **Verified_Benchmark_Evidence**: A benchmark report produced by an executed benchmark suite and carrying the capability identifier, score, scenario counts, and measured latency when available.
- **Verified_Lifecycle_Evidence**: A lifecycle state or transition obtained from the Lifecycle Authority rather than from free-form model output.
- **Self_Reported_Competence**: A competence, confidence, success-rate, or lifecycle claim generated as free-form model output without authoritative verified evidence.
- **Explicit_User_Evidence**: A user-authored statement or explicit user-invoked preference-setting action that identifies a preference key, value, scope, and evidence provenance.
- **Sensitive_Preference**: A preference concerning credentials, authentication secrets, health, biometrics, precise location, race or ethnicity, religion, political affiliation, sexual orientation, or similarly sensitive personal data.
- **Evidence_Provenance**: JSON-safe fields identifying evidence type, source, stable evidence identifier, capability or preference key, environment or scope, and logical or observed time.
- **Memory_Evidence_Event**: A domain-general kernel event carrying authoritative evidence and a stable event or evidence identifier for memory integration.
- **Replay**: Reprocessing a previously recorded ordered sequence of Memory Evidence Events.
- **Replay_Safe**: Producing the same final memory state when the same event sequence is processed again, without duplicate records or duplicated side effects.
- **Transaction_Safe_Store**: The existing JSON persistence abstraction hardened so each mutation is all-or-nothing and a failed or interrupted write preserves the last valid committed state.
- **M19_Retrieval_Router**: The existing uniform retrieval mechanism that registers sources exposing `retrieve(query, top_k)` and returns ranked provenance-carrying results.
- **Guarded_Production_Bootstrap**: The existing `FRIDAY_USE_KERNEL_EXECUTION` production path that activates kernel-backed subsystems while leaving the flag-off path unchanged.
- **Hard_Validation**: Rejection of malformed, unsupported, out-of-range, non-JSON-safe, or unauthenticated evidence before persistent state changes.
- **Observable_Degradation**: A contained failure that does not escape into the event bus or bootstrap and is recorded through structured logging, diagnostics, or an inspectable error surface.
- **Canonical_Desktop_Cognition**: The browser and desktop path that perceives, reasons over World Objects, acts through the Motor System, and verifies success by observed World Model change.
- **NVIDIA_Only_Constraint**: The project constraint that model and embedding operations use the existing NVIDIA provider surface and add no alternative model provider.
- **Committed_Baseline**: A version-controlled benchmark result used as a regression reference.
- **Full_Suite_Checkpoint**: A non-watch execution of the complete automated test suite used to establish the milestone regression result.

## Requirements

### Requirement 1: Complete the approved seven-tier architecture without duplication

**User Story:** As an architecture maintainer, I want the remaining memory tiers added to the existing subsystem, so that A2.11 is complete without architectural drift.

#### Acceptance Criteria

1. THE Seven_Tier_Memory SHALL expose Working, Episodic, Semantic, Procedural, Capability, Failure, and Preference as the seven normative live memory tiers.
2. THE Memory_Controller SHALL compose Capability_Memory and Preference_Memory with the Existing_Memory_Tier instances.
3. THE Seven_Tier_Memory SHALL use the existing memory entry and memory store contracts for Capability_Memory and Preference_Memory.
4. IF an integration path would create a second memory controller, persistence mechanism, competence authority, benchmark authority, lifecycle authority, or retrieval router, THEN THE Seven_Tier_Memory SHALL reject that integration path.
5. WHEN current observed reality conflicts with a retrieved memory, THE Seven_Tier_Memory SHALL give current observed reality precedence.
6. THE Existing_Memory_Tier SHALL preserve pre-M25 behavior unless an explicit M25 requirement states otherwise.

### Requirement 2: Derive Capability Memory only from authoritative evidence

**User Story:** As a planner, I want capability recollections grounded in verified evidence, so that remembered competence cannot be fabricated by a model.

#### Acceptance Criteria

1. WHEN Verified_Capability_Evidence is accepted, THE Capability_Memory SHALL store the authoritative capability, environment, verdict, competence values, Evidence_Provenance, and evidence time.
2. WHEN Verified_Benchmark_Evidence is accepted, THE Capability_Memory SHALL store the authoritative capability identifier, score, scenario counts, measured latency when present, Evidence_Provenance, and evidence time.
3. WHEN Verified_Lifecycle_Evidence is accepted, THE Capability_Memory SHALL store the authoritative capability identifier, lifecycle state, Evidence_Provenance, and evidence time.
4. IF a capability candidate contains Self_Reported_Competence or lacks Verified_Capability_Evidence, Verified_Benchmark_Evidence, or Verified_Lifecycle_Evidence, THEN THE Capability_Memory SHALL reject the candidate without changing persistent state.
5. THE Capability_Memory SHALL preserve competence values produced by the Competence_Authority without recomputing competence.
6. THE Capability_Memory SHALL preserve lifecycle values produced by the Lifecycle_Authority without performing lifecycle transitions.
7. THE Capability_Memory SHALL preserve benchmark values produced by the Benchmark_Authority without deciding promotion.
8. THE Capability_Memory SHALL key the current capability view by capability and environment.
9. WHEN newer authoritative evidence is accepted for an existing capability and environment, THE Capability_Memory SHALL replace the current view according to evidence ordering.

### Requirement 3: Form Preference Memory only from explicit user evidence

**User Story:** As a user, I want FRIDAY to remember only preferences I explicitly provide, so that behavior is personalized without speculative profiling.

#### Acceptance Criteria

1. WHEN Explicit_User_Evidence is accepted, THE Preference_Memory SHALL store the preference key, value, scope, Evidence_Provenance, and evidence time.
2. IF a preference candidate lacks Explicit_User_Evidence, THEN THE Preference_Memory SHALL reject the candidate without changing persistent state.
3. IF a preference candidate is derived from observed behavior, episodic frequency, demographic attributes, model speculation, or third-party content, THEN THE Preference_Memory SHALL reject the candidate without changing persistent state.
4. IF a Sensitive_Preference is inferred rather than explicitly stated by the user, THEN THE Preference_Memory SHALL reject the candidate without changing persistent state.
5. WHEN a user explicitly updates an existing preference key and scope, THE Preference_Memory SHALL make the newer explicitly evidenced value the current value.
6. WHEN a user explicitly revokes an existing preference key and scope, THE Preference_Memory SHALL exclude the revoked preference from active retrieval.
7. THE Preference_Memory SHALL key the current preference view by preference key and scope.
8. THE Preference_Memory SHALL expose Evidence_Provenance for each returned preference.

### Requirement 4: Apply distinct retention, forgetting, and contradiction rules

**User Story:** As a memory subsystem owner, I want each tier to retain and forget information according to its meaning, so that the seven tiers do not collapse into an undifferentiated store.

#### Acceptance Criteria

1. THE Capability_Memory SHALL retain a bounded current view and bounded authoritative evidence history per capability and environment.
2. WHEN authoritative capability evidence becomes superseded, expired, invalidated, deprecated, or archived, THE Capability_Memory SHALL update the active capability view according to the authoritative evidence state.
3. THE Preference_Memory SHALL retain only the current explicitly evidenced value for each active preference key and scope.
4. WHEN an explicit preference update contradicts an older preference for the same key and scope, THE Preference_Memory SHALL resolve the contradiction in favor of the newer explicit evidence.
5. WHEN a retention limit is exceeded, THE Capability_Memory SHALL evict the oldest inactive capability evidence before active current views.
6. WHEN a retention limit is exceeded, THE Preference_Memory SHALL evict the oldest inactive or revoked preference before active current preferences.
7. THE Capability_Memory SHALL carry authoritative competence confidence with each active capability view.
8. THE Preference_Memory SHALL carry an explicit-evidence status rather than an inferred confidence claim.
9. THE Existing_Memory_Tier SHALL retain the formation, retention, forgetting, and contradiction behavior established before M25.

### Requirement 5: Provide bounded transaction-safe JSON persistence

**User Story:** As an operator, I want persistent memory mutations to be bounded and atomic, so that interruption or malformed data cannot silently corrupt memory.

#### Acceptance Criteria

1. THE Transaction_Safe_Store SHALL enforce a configurable positive maximum entry count for each persistent memory tier.
2. WHEN a persistent mutation succeeds, THE Transaction_Safe_Store SHALL commit the complete resulting JSON document as one atomic state transition.
3. IF a persistent mutation fails or is interrupted before commit, THEN THE Transaction_Safe_Store SHALL preserve the last valid committed JSON document.
4. IF persisted JSON is malformed or violates the memory schema, THEN THE Transaction_Safe_Store SHALL preserve the malformed artifact for diagnosis and expose an Observable_Degradation.
5. WHEN a valid memory record is serialized and then deserialized, THE Transaction_Safe_Store SHALL produce a record equivalent in tier, content, timestamp, tags, metadata, identifier, and expiration.
6. THE Transaction_Safe_Store SHALL serialize Capability_Memory and Preference_Memory records as JSON-safe values.
7. WHEN concurrent persistent mutations are requested, THE Transaction_Safe_Store SHALL serialize commits without losing a successfully committed mutation.
8. WHEN a persistent tier starts after an interrupted write, THE Transaction_Safe_Store SHALL recover the last valid committed state before serving retrieval.
9. WHILE the persistent entry count exceeds the configured maximum during recovery, THE Transaction_Safe_Store SHALL remove entries according to the tier retention rules before serving retrieval.

### Requirement 6: Integrate evidence through replay-safe JSON events

**User Story:** As a kernel maintainer, I want memory integration driven by replay-safe events, so that live processing and replay produce the same memory state.

#### Acceptance Criteria

1. WHEN the Competence_Authority publishes an existing `competence.updated` event with authoritative provenance, THE Capability_Memory SHALL process the event as Verified_Capability_Evidence.
2. WHEN the Benchmark_Authority or Lifecycle_Authority publishes a domain-general Memory_Evidence_Event, THE Capability_Memory SHALL process the event according to the declared authoritative evidence type.
3. WHEN an explicit user preference action publishes a domain-general Memory_Evidence_Event, THE Preference_Memory SHALL process the event as Explicit_User_Evidence.
4. THE Memory_Evidence_Event SHALL contain a schema version, stable evidence identifier, evidence type, source, logical or observed time, and JSON-safe payload.
5. WHEN the same Memory_Evidence_Event is delivered more than once, THE Seven_Tier_Memory SHALL apply the evidence exactly once.
6. WHEN an ordered Memory_Evidence_Event sequence is replayed from the same initial state, THE Seven_Tier_Memory SHALL produce the same final records, active views, and eviction choices as live processing.
7. IF a Memory_Evidence_Event is malformed, unsupported, out of range, or non-JSON-safe, THEN THE Seven_Tier_Memory SHALL reject the event without changing persistent state.
8. IF a memory event handler encounters a processing failure, THEN THE Seven_Tier_Memory SHALL contain the failure at the event boundary and expose an Observable_Degradation.
9. THE Seven_Tier_Memory SHALL use domain-general event types without application, browser, site, or window identity.
10. THE Seven_Tier_Memory SHALL preserve append-only event-store replay compatibility for every new event payload.

### Requirement 7: Extend uniform retrieval through the existing M19 router

**User Story:** As a planner, I want capability and preference records returned through the same retrieval surface as other memory, so that callers do not add tier-specific search paths.

#### Acceptance Criteria

1. THE Capability_Memory SHALL expose `retrieve(query, top_k)` through the existing memory source contract.
2. THE Preference_Memory SHALL expose `retrieve(query, top_k)` through the existing memory source contract.
3. WHEN the Memory_Controller builds the M19_Retrieval_Router, THE Memory_Controller SHALL register the live Capability_Memory and Preference_Memory instances alongside the available Existing_Memory_Tier sources.
4. WHEN the M19_Retrieval_Router receives an unfiltered query, THE M19_Retrieval_Router SHALL consider Capability and Preference sources under the same ranking contract as every registered source.
5. WHEN the M19_Retrieval_Router receives a Capability tier filter, THE M19_Retrieval_Router SHALL return only Capability tier results.
6. WHEN the M19_Retrieval_Router receives a Preference tier filter, THE M19_Retrieval_Router SHALL return only Preference tier results.
7. THE M19_Retrieval_Router SHALL return Capability and Preference results with source, tier, score, entry identifier, timestamp, and Evidence_Provenance.
8. THE M19_Retrieval_Router SHALL enforce non-negative `top_k` and `per_source_k` bounds for Capability and Preference sources.
9. IF a Capability or Preference source fails during retrieval, THEN THE M19_Retrieval_Router SHALL return healthy-source results and expose the source failure through its existing Observable_Degradation surface.
10. THE Seven_Tier_Memory SHALL route cross-tier retrieval through the M19_Retrieval_Router rather than a duplicate router or caller-specific tier branch.

### Requirement 8: Bootstrap the live path behind the existing production guard

**User Story:** As a release maintainer, I want the completed memory tiers wired through the guarded production bootstrap, so that activation is additive and rollback remains controlled.

#### Acceptance Criteria

1. WHERE `FRIDAY_USE_KERNEL_EXECUTION` is enabled, THE Guarded_Production_Bootstrap SHALL construct bounded Capability_Memory and Preference_Memory instances.
2. WHERE `FRIDAY_USE_KERNEL_EXECUTION` is enabled, THE Guarded_Production_Bootstrap SHALL attach Capability_Memory and Preference_Memory to the existing kernel event stream.
3. WHERE `FRIDAY_USE_KERNEL_EXECUTION` is enabled, THE Guarded_Production_Bootstrap SHALL provide the same Capability_Memory and Preference_Memory instances to the Memory_Controller and M19_Retrieval_Router.
4. WHERE `FRIDAY_USE_KERNEL_EXECUTION` is disabled, THE Guarded_Production_Bootstrap SHALL preserve the pre-M25 flag-off behavior.
5. WHERE `FRIDAY_USE_KERNEL_EXECUTION` is disabled, THE Guarded_Production_Bootstrap SHALL perform no Capability or Preference persistence I/O.
6. IF Capability or Preference bootstrap wiring fails, THEN THE Guarded_Production_Bootstrap SHALL preserve server startup through the established guarded fallback and expose an Observable_Degradation.
7. WHEN the guarded production path restarts with valid persisted state, THE Guarded_Production_Bootstrap SHALL make the recovered Capability and Preference records available to the M19_Retrieval_Router.
8. THE Guarded_Production_Bootstrap SHALL preserve a rollback control by disabling `FRIDAY_USE_KERNEL_EXECUTION`.

### Requirement 9: Enforce hard validation and observable error handling

**User Story:** As an operator, I want invalid evidence rejected before storage and failures made visible, so that memory corruption and silent degradation are prevented.

#### Acceptance Criteria

1. IF authoritative capability evidence lacks a non-empty capability identifier, environment field, evidence type, stable evidence identifier, source, or evidence time, THEN THE Capability_Memory SHALL reject the evidence before persistent mutation.
2. IF capability confidence or benchmark score is outside the inclusive range from 0.0 to 1.0, THEN THE Capability_Memory SHALL reject the evidence before persistent mutation.
3. IF capability attempts, successes, scenarios run, scenarios passed, or measured latency is negative, THEN THE Capability_Memory SHALL reject the evidence before persistent mutation.
4. IF a lifecycle value is not a state recognized by the Lifecycle_Authority, THEN THE Capability_Memory SHALL reject the evidence before persistent mutation.
5. IF explicit preference evidence lacks a non-empty key, value, scope, stable evidence identifier, source, or evidence time, THEN THE Preference_Memory SHALL reject the evidence before persistent mutation.
6. IF a Capability or Preference record exceeds 65536 UTF-8 bytes after JSON serialization, THEN THE Seven_Tier_Memory SHALL reject the record before persistent mutation.
7. IF new M25 code catches an exception at an approved degradation boundary, THEN THE Seven_Tier_Memory SHALL emit or retain diagnostic context containing the subsystem, operation, and error category.
8. THE Seven_Tier_Memory SHALL contain no new silent `except Exception: pass` or equivalent silent exception swallowing.
9. IF validation rejects an event or record, THEN THE Seven_Tier_Memory SHALL return or expose a stable rejection reason.
10. WHEN validation succeeds, THE Seven_Tier_Memory SHALL persist only the validated normalized representation.

### Requirement 10: Verify integration, replay, persistence recovery, and retrieval

**User Story:** As a maintainer, I want automated evidence for the completed live path, so that correctness survives generated inputs, replay, restart, and storage failure.

#### Acceptance Criteria

1. THE milestone validation SHALL include property-based tests over generated authoritative capability evidence and rejected self-reported capability candidates.
2. THE milestone validation SHALL include property-based tests over generated explicit preference evidence and rejected inferred preference candidates.
3. THE milestone validation SHALL include a JSON serialization and deserialization round-trip property for Capability and Preference records.
4. THE milestone validation SHALL include a bounded-storage invariant for Capability and Preference persistence.
5. THE milestone validation SHALL include a replay idempotence property proving repeated delivery of the same evidence sequence produces the same final memory state.
6. THE milestone validation SHALL include a retrieval property proving tier filters, result bounds, provenance, and score ordering for Capability and Preference results.
7. THE milestone validation SHALL include an integration check from authoritative kernel evidence through persistent memory to an M19_Retrieval_Router result.
8. THE milestone validation SHALL include a restart check proving committed Capability and Preference records are available after reconstruction.
9. THE milestone validation SHALL include an interrupted-write recovery check proving the last valid committed JSON state remains available.
10. THE milestone validation SHALL include a malformed-JSON recovery check proving corruption is observable and not silently overwritten.
11. THE milestone validation SHALL include guarded-bootstrap checks for enabled and disabled production paths.
12. THE milestone validation SHALL execute each property-based test with at least 100 generated examples.

### Requirement 11: Provide deterministic milestone benchmarking without probabilistic baselines

**User Story:** As a governance reviewer, I want deterministic measurements for the new memory mechanisms, so that the milestone has reproducible evidence without fabricating competence.

#### Acceptance Criteria

1. THE milestone SHALL include a deterministic hermetic benchmark covering evidence acceptance, replay, retrieval, and persistence recovery for Capability_Memory and Preference_Memory.
2. WHEN the deterministic benchmark receives the same fixtures, logical clock, identifiers, and configuration, THE benchmark SHALL produce identical correctness metrics and record ordering.
3. THE deterministic benchmark SHALL use synthetic domain-general evidence without network, model, browser, desktop, or external-service calls.
4. THE deterministic benchmark SHALL remain separate from the committed five-domain competence scorecard.
5. THE milestone SHALL add no probabilistic result to a Committed_Baseline.
6. IF real-machine capability benchmarks are not executed, THEN THE milestone review SHALL record the benchmark status as not run without fabricating a score.
7. IF real-machine capability benchmarks are executed, THEN THE milestone review SHALL preserve the measured output as review evidence without converting nondeterministic latency into a committed pass baseline.

### Requirement 12: Preserve cross-cutting constraints and complete governance artifacts

**User Story:** As the Architecture v2.1 reviewer, I want the milestone to preserve established constraints and update traceability, so that A2.11 can move from Partial to Built with auditable evidence.

#### Acceptance Criteria

1. THE Seven_Tier_Memory SHALL preserve Canonical_Desktop_Cognition as the browser and desktop execution authority.
2. THE Seven_Tier_Memory SHALL add no browser-specific, site-specific, application-specific, or window-title-specific memory logic.
3. WHERE a model or embedding operation is required, THE Seven_Tier_Memory SHALL use the existing NVIDIA provider surface under the NVIDIA_Only_Constraint.
4. THE milestone SHALL add no non-NVIDIA model or embedding provider dependency.
5. THE milestone SHALL update `docs/architecture/FAS_v2.1_AMENDMENTS.md` to mark the full A2.11 seven-tier memory expansion as Built with live code references.
6. THE milestone SHALL update `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` to move A2.11 seven-tier memory from Partial to Built.
7. THE milestone SHALL update relevant memory subsystem documentation with formation, retention, forgetting, contradiction, evidence, replay, retrieval, and rollback behavior.
8. THE milestone SHALL produce `docs/reviews/REVIEW_m25-seven-tier-memory.md` with architecture compliance, validation evidence, benchmark status, and regression results.
9. WHEN the Full_Suite_Checkpoint runs, THE milestone SHALL report at least the pre-M25 floor of 1677 existing passed tests plus the new M25 tests and zero failed tests.
10. THE milestone SHALL preserve every pre-M25 test without weakening assertions, reducing generated examples, adding skips, adding expected failures, or excluding tests from the Full_Suite_Checkpoint.
11. THE milestone SHALL use a single-run non-watch command for the Full_Suite_Checkpoint.
12. THE milestone SHALL leave the working tree changes uncommitted.
