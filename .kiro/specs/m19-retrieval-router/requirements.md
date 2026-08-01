# Requirements Document

M19 — Retrieval Router

## Introduction

The v2.1 traceability matrix marks **A2.7 Retrieval Router** as *Absent* — retrieval today
is ad hoc: each caller decides for itself which memory tier or source to search, so tier
selection is hardcoded at every call site and results are neither merged, ranked, nor
provenance-tracked across sources. FAS §A2.7.1 requires a single **Retrieval Router** that
selects the correct information source(s) per request *before* any search runs, routing
across the World Model, Memory tiers (episodic/semantic/procedural/failure), the Capability
Registry, and future connectors — with vector search as *one* strategy, never the universal
default.

This milestone delivers that router as one general, reusable mechanism over the existing
uniform retrieval surface (`retrieve(query, top_k) -> List[MemoryEntry]`, implemented by
every `MemoryStore` and by `FailureMemory`). Callers describe **what** they want (a query,
optionally a tier filter); the router fans out to registered sources, normalizes results
into uniform provenance-carrying items, merges, ranks, de-duplicates, and returns a single
list. It introduces no duplicate memory system and no per-tier or application-specific
logic (Axiom 15) — tier selection is data, not code branches.

The failure tier (M21) is a first-class participant: past failures become retrievable
alongside episodic/semantic memory so planning can weigh "we have failed at this before"
in the same ranked result set.

## Glossary

- **Retrieval Router**: the single mechanism that routes a retrieval query across
  registered sources, then merges/ranks/de-duplicates results.
- **Source**: any object exposing `retrieve(query, top_k) -> List[MemoryEntry]` (every
  `MemoryStore`; `FailureMemory` via its `retrieve`). Registered under a name + a tier.
- **RetrievedItem**: a uniform, ranked result carrying content, tier, score, source
  (provenance), entry_id, timestamp, and metadata.
- **Tier filter**: an optional set of `MemoryTier`s restricting which sources are queried.
- **Rank-based scoring**: per-source scoring by best-first position (top hit = 1.0,
  decreasing), scaled by an optional per-source weight — backend-agnostic, independent of
  each source's internal scoring scheme.
- **Provenance**: the `source` (and `tier`) that produced each result, preserved end to end.

## Requirements

### Requirement 1: Uniform source registration

**User Story:** As a subsystem owner, I want to register any memory source under one
contract so the router can query it without knowing its internals.

#### Acceptance Criteria
1. THE Retrieval Router SHALL register a source under a unique name, an owning
   `MemoryTier`, and an optional non-negative weight (default 1.0).
2. IF a candidate source does not expose a `retrieve(query, top_k)` method THEN THE router
   SHALL reject the registration with a clear error (fail fast at wiring time).
3. THE router SHALL support unregistering a source by name and SHALL report its current
   source count and the distinct set of registered tiers.
4. Registering a name that already exists SHALL replace the prior registration for that name.

### Requirement 2: Cross-source routing

**User Story:** As a caller, I want to issue one query and have the router search all
relevant sources, so I never hardcode which tier to hit.

#### Acceptance Criteria
1. WHEN `route(query)` is called with no tier filter THEN THE router SHALL query every
   registered source.
2. WHEN `route(query, tiers=...)` is called with a tier filter THEN THE router SHALL query
   ONLY sources whose owning tier is in the filter, and SHALL query no others.
3. WHEN no source is registered, OR the tier filter matches no registered source, THEN THE
   router SHALL return an empty result list (never an error).
4. THE router SHALL request at most `per_source_k` entries from each source and SHALL
   return at most `top_k` merged results.

### Requirement 3: Merge, rank, and cap

**User Story:** As a caller, I want a single ranked list across sources so I can consume
the best evidence regardless of where it came from.

#### Acceptance Criteria
1. THE router SHALL score each source's results by rank (top hit = 1.0, decreasing by
   position) scaled by that source's weight, so scoring is independent of any source's
   internal score scheme.
2. THE router SHALL merge results from all queried sources and SHALL return them sorted by
   score in descending order.
3. THE router SHALL cap the returned list at `top_k`.
4. A source registered with a higher weight SHALL contribute proportionally higher-ranked
   results than an equally-positioned result from a lower-weighted source.

### Requirement 4: Provenance and de-duplication

**User Story:** As planning/deliberation, I want to know where each result came from and
not see the same item twice.

#### Acceptance Criteria
1. EVERY returned `RetrievedItem` SHALL carry its `source` name and `tier` (provenance),
   plus content, score, entry_id, timestamp, and metadata.
2. THE router SHALL de-duplicate results by `entry_id` when present, else by
   `(tier, content)`, keeping the highest-scored occurrence.
3. EVERY `RetrievedItem` SHALL be JSON-projectable (`to_dict`) for replay/logging.

### Requirement 5: Failing-source isolation (graceful degradation)

**User Story:** As the operator, I want one misbehaving source not to break retrieval for
the others.

#### Acceptance Criteria
1. IF a source raises during `retrieve` THEN THE router SHALL skip that source and continue
   with the remaining sources — `route` SHALL never raise on account of a source failure.
2. WHEN a source is skipped due to error THEN THE results from healthy sources SHALL still
   be returned, merged and ranked.
3. THE router itself SHALL NOT use a bare silent `except Exception: pass` in new FRIDAY code
   without attaching diagnostic context or a comment justifying the degradation boundary
   (structured-error-model compliance, A2.14.2).

### Requirement 6: Failure-memory participation

**User Story:** As planning, I want prior failures retrievable alongside other memory so
"we have failed at this before" surfaces in the same ranked result set.

#### Acceptance Criteria
1. THE router SHALL accept `FailureMemory` as a source registered under
   `MemoryTier.FAILURE` via its existing `retrieve(query, top_k)` surface.
2. WHEN failures relevant to the query exist THEN a tier-unfiltered `route` SHALL be able to
   return `MemoryTier.FAILURE` items interleaved with other tiers by score.
3. A tier filter of `{FAILURE}` SHALL return only failure-tier results.

### Requirement 7: Integration (additive, safe)

**User Story:** As the maintainer, I want the router wired so it changes no default
behavior and never breaks hermetic tests.

#### Acceptance Criteria
1. THE memory controller SHALL expose a way to build a router pre-registered with the
   available persistent tiers (episodic/semantic/procedural and, when present, failure),
   without changing existing `FridayMemory` method behavior.
2. THE production bootstrap SHALL construct/register the router only within the guarded
   kernel-execution path, so hermetic tests and benchmarks perform no unbidden I/O.
3. THE full existing test suite SHALL remain green (no regressions).

### Requirement 8: Verification artifacts

**User Story:** As the maintainer, I require every milestone to ship its evidence.

#### Acceptance Criteria
1. THE milestone SHALL include property/unit tests covering routing, tier filtering,
   weighted ranking, provenance, de-duplication, failing-source isolation, and
   failure-memory participation.
2. THE milestone SHALL include a deterministic, hermetic retrieval benchmark (routing
   quality/latency over synthetic sources) that is NOT recorded into the committed
   competence baseline.
3. THE milestone SHALL update the FAS (A2.7 → Built), the traceability matrix, and produce
   an after-milestone architecture review, with a full-suite checkpoint (0 failed).
