# Requirements Document

M21 (slice 2) — Seven-Tier Memory Completion (Capability + Preference tiers)

## Introduction

The v2.1 traceability matrix's last remaining non-Built item is the broader **A2.11
seven-tier memory** expansion. FAS §A2.11.1 requires seven tiers:
`Working, Episodic, Semantic, Procedural, Capability, Failure, Preference`. Today the
codebase has Working / Episodic / Semantic / Procedural (M8) and Failure (M21 slice 1,
`friday/memory/failure_memory.py`). The two tiers not yet formalized as first-class,
persistent, queryable memory on the live path are **Capability** and **Preference**.

This milestone delivers those two tiers **additively**, mirroring the proven
`FailureMemory` template: each is a bounded `JSONFileStore`-backed, kernel-driven, defensive
memory tier that consumes events already on the bus, exposes the uniform
`retrieve(query, top_k)` surface (so it participates in the M19 Retrieval Router), and is
attached only within the guarded kernel-execution path. No duplicate systems are introduced.

Critically, the **Capability tier is memory, not authority**: the evidence-only
`CompetenceModel` (Ch 28) remains the sole authority on competence. The Capability tier
records a queryable, reflective *memory* of capability outcomes (formed from
`competence.updated` events) so planning can recall "what do we know about capability X in
environment Y" — it never fabricates competence and never overrides the CompetenceModel. The
**Preference tier** is a persistent, queryable record of user preferences formed from
preference signals, distinct from volatile working-memory context.

## Glossary

- **Capability tier (`MemoryTier.CAPABILITY`)**: a persistent, queryable memory of capability
  outcomes/notes keyed by `(capability, environment)`, formed from `competence.updated`
  events. A memory VIEW, not a competence authority.
- **Preference tier (`MemoryTier.PREFERENCE`)**: a persistent, queryable memory of user
  preferences (key/value + description), formed from preference signals.
- **CapabilityMemory / PreferenceMemory**: the two new tier classes, mirroring `FailureMemory`.
- **Uniform retrieve surface**: `retrieve(query, top_k) -> List[MemoryEntry]` — the contract
  every tier exposes so the M19 Retrieval Router can route across it.
- **CompetenceModel**: the existing evidence-only competence authority (Ch 28) — the
  Capability tier defers to it and never replaces it.

## Requirements

### Requirement 1: Capability + Preference tier identifiers

**User Story:** As the architecture, I want the two missing tiers represented so the
seven-tier model is complete.

#### Acceptance Criteria
1. THE `MemoryTier` enum SHALL include `CAPABILITY` and `PREFERENCE` members (additive; the
   existing members SHALL be unchanged).
2. THE seven canonical FAS §A2.11.1 tiers (Working, Episodic, Semantic, Procedural,
   Capability, Failure, Preference) SHALL each be representable by a `MemoryTier` value.

### Requirement 2: Capability memory tier

**User Story:** As planning/deliberation, I want to recall what we know about a capability in
an environment, without duplicating or overriding the competence authority.

#### Acceptance Criteria
1. THE `CapabilityMemory` SHALL record a capability outcome keyed by
   `(capability, environment)` carrying at least: confidence/observed value, attempts, and a
   short summary — sourced from `competence.updated` events.
2. WHEN attached to a kernel AND a `competence.updated` event is published THEN the tier
   SHALL record/update the corresponding capability memory; malformed events SHALL be
   ignored and handlers SHALL never raise into the bus.
3. THE tier SHALL be a memory VIEW only — it SHALL NOT recompute competence, SHALL NOT
   override the `CompetenceModel`, and SHALL NOT emit competence authority; it records what
   the authority reported.
4. THE tier SHALL expose `recall(capability?, environment?, limit)` and the uniform
   `retrieve(query, top_k)` surface, and its storage SHALL be bounded (oldest evicted).

### Requirement 3: Preference memory tier

**User Story:** As FRIDAY, I want durable user preferences remembered so behavior respects
them across sessions.

#### Acceptance Criteria
1. THE `PreferenceMemory` SHALL record a preference as a `(key, value)` with an optional
   description, and SHALL upsert (a newer value for the same key supersedes the older).
2. WHEN attached to a kernel AND a preference signal is observed on the bus THEN the tier
   SHALL record the preference; malformed events SHALL be ignored and handlers SHALL never
   raise. THE tier SHALL also expose a direct `record_preference(key, value, ...)` API.
3. THE tier SHALL expose `get(key)` / `all()` queries and the uniform
   `retrieve(query, top_k)` surface, and its storage SHALL be bounded (oldest evicted).

### Requirement 4: Reuse, not duplicate

**User Story:** As the architecture, I require the new tiers to reuse existing mechanisms.

#### Acceptance Criteria
1. BOTH tiers SHALL be backed by the existing bounded `JSONFileStore` and `MemoryEntry`
   contracts (no new persistence mechanism).
2. BOTH tiers SHALL follow the `FailureMemory` pattern (kernel `attach`, defensive handlers,
   bounded store, uniform `retrieve`) — no duplicate memory framework.
3. NEITHER tier SHALL contain application-specific logic (no app/site/window identity —
   Axiom 15); capability keys are generic `(capability, environment)` and preferences are
   generic `(key, value)`.

### Requirement 5: Retrieval-router participation

**User Story:** As planning, I want capability and preference memory retrievable through the
same router as the other tiers.

#### Acceptance Criteria
1. BOTH tiers SHALL satisfy the router source contract via `retrieve(query, top_k)`.
2. THE controller factory (`build_retrieval_router`) SHALL register both tiers (under
   `MemoryTier.CAPABILITY` / `MemoryTier.PREFERENCE`) when they are supplied.

### Requirement 6: Additive, safe integration

**User Story:** As the maintainer, I want the tiers wired so they change no default behavior
and never break hermetic tests.

#### Acceptance Criteria
1. THE tiers SHALL be opt-in in the reactive-loop / bootstrap wiring (attached only when
   supplied / within the guarded kernel path) so hermetic tests perform no unbidden disk I/O.
2. THE production bootstrap SHALL attach bounded `CapabilityMemory` + `PreferenceMemory` when
   kernel execution is enabled, and register them in the retrieval router.
3. THE default (flag-off) path SHALL be byte-unchanged and the full existing test suite SHALL
   remain green (zero failures).

### Requirement 7: Verification artifacts

**User Story:** As the maintainer, I require every milestone to ship its evidence.

#### Acceptance Criteria
1. THE milestone SHALL include property/unit tests covering: the new tier ids; capability
   recording from `competence.updated` (+ memory-not-authority invariant); preference
   upsert + query; bounded storage; defensive handlers; uniform `retrieve`; and
   retrieval-router participation.
2. THE milestone SHALL update the FAS (A2.11 seven-tier → Built) and the traceability matrix
   (the last Partial row → Built), and produce an after-milestone architecture review with a
   full-suite checkpoint (zero failures). This closes the Architecture v2.1 build-out
   entirely.
