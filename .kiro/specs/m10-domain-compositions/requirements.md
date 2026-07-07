# Requirements Document

M10 — Domain Depth as Pure Capability Compositions

## Introduction

M10 adds **domain depth** to FRIDAY (Research Ch 37, Communication Ch 39, Documents Ch 40, SWE Ch 41)
**without** adding any application-specific pipeline, durable domain state, or hardcoded application /
site name. Each domain is a *pure composition* over the existing `CapabilityRegistry` (`find_for` by
abstract verb) and the `ExecutionEvidence` bundle (the Evidence Law). The defining constraint: the
domain layer is a set of leaves — deleting any domain module leaves every capability and every other
domain intact. This preserves Axiom 15 (environment-independence / no hardcoded sites) and the
wrap-don't-rewrite constraint from HANDOFF Section 12/13. Ch 41 (software engineering) full depth is
explicitly deferred to v2 (HANDOFF Section 9); M10 ships only a documented stub for it.

## Glossary

- **Domain**: a pure composition module under `friday/domains/` that satisfies a class of tasks by
  discovering and composing capabilities; it owns no durable state.
- **Capability**: an executable `CapabilityContract` in the `CapabilityRegistry`, discoverable by
  abstract verb via `find_for`.
- **Abstract verb**: a semantic action name (`search`, `read`, `deliver`, `create_file`) used to
  discover capabilities without naming any concrete application.
- **ExecutionEvidence / Evidence Law**: the artifact bundle (`GATHERED_INFO`, `SOURCE_URL`,
  `GENERATED_CONTENT`, `FILE_ARTIFACT`, `DELIVERY_CONFIRMATION`) that makes false completion
  architecturally impossible; a gather/deliver demand is met only by real matching evidence.
- **SemanticDocument**: a format-independent document model (title → sections → blocks + citations)
  rendered to concrete formats on export.
- **Conversation**: an immutable, caller-owned transcript value; domains return updated copies.
- **Credibility / authority class**: a domain-agnostic ranking of a source by host *class*
  (`primary`/`reference`/`general`), never by literal site identity (Axiom 15).
- **UNAVAILABLE**: the graceful degradation outcome a domain returns when no capability matches a verb.
- **Pure composition**: a domain method whose outputs depend only on its arguments (and the registry
  contents), with no cross-call mutable state.

## Requirements

### Requirement 1: Research domain depth (Ch 37) as pure composition

**User Story:** As FRIDAY, I want to investigate a query with hypotheses, source credibility ranking,
and contradiction detection, so that research output is deeper than raw gathering while inventing no
facts and storing nothing durable.

#### Acceptance Criteria

1. WHEN `ResearchDomain.investigate(query, evidence)` is called THEN the system SHALL gather material
   by composing the existing `research(...)` capability and SHALL record `GATHERED_INFO` / `SOURCE_URL`
   artifacts on the passed evidence bundle (no fabricated sources).
2. WHEN sources have been gathered THEN the system SHALL rank them by a domain-agnostic credibility
   heuristic based on host authority *class* (primary/reference/general), producing `credibility`
   scores in `[0, 1]` in a stable total order, and SHALL NOT rank by any literal site name.
3. WHEN claims are extracted from gathered text THEN the system SHALL detect contradictions as pairs
   of claims sharing a subject with opposing polarity, symmetric in input order.
4. WHEN hypotheses are supplied THEN the system SHALL score each hypothesis with a support ratio
   `supporting / total` in `[0, 1]` (0 when `total == 0`), derived only from gathered claims.
5. IF no `search`/`read` capability (or browser) is available THEN the system SHALL return a
   `ResearchFinding` flagged unavailable/blocked with `success == False` and SHALL NOT raise.

### Requirement 2: Environment-independent communication (Ch 39)

**User Story:** As FRIDAY, I want to deliver a message through whatever delivery capability exists and
verify it really went out, so that communication works in any environment without hardcoding an app.

#### Acceptance Criteria

1. WHEN `CommunicationDomain.deliver(recipient, message, evidence)` is called THEN the system SHALL
   discover the delivery capability via `find_for("deliver")` and SHALL NOT reference any literal
   application or site name.
2. WHEN a delivery capability executes and observed "sent" state is present THEN the system SHALL
   record a `DELIVERY_CONFIRMATION` artifact and return `DeliveryStatus.CONFIRMED`.
3. IF a delivery capability runs but no `DELIVERY_CONFIRMATION` artifact appears THEN the system SHALL
   return `DeliveryStatus.FAILED` and SHALL NOT report success from generated text alone.
4. WHEN `append_turn(transcript, speaker, text)` is called THEN the system SHALL return a NEW
   `Conversation` with the turn appended and SHALL leave the original transcript unchanged.
5. IF no `deliver` capability exists THEN the system SHALL return `DeliveryStatus.UNAVAILABLE` and
   SHALL NOT raise.

### Requirement 3: Documents as a semantic model with multi-format export and citations (Ch 40)

**User Story:** As FRIDAY, I want to build a document once as a semantic model and export it to
multiple formats with citations back to my sources, so that produced documents are portable and
provenance-linked.

#### Acceptance Criteria

1. WHEN `render(document, fmt)` is called for MARKDOWN/HTML/PLAINTEXT THEN the system SHALL produce a
   deterministic string containing the title and every section heading and block text in document
   order.
2. WHEN `export(document, filename, fmt, evidence)` is called THEN the system SHALL render the document
   and persist it by composing a `create_file`-verb capability, recording a `FILE_ARTIFACT` (bytes >
   0) and `GENERATED_CONTENT` on success.
3. WHEN `cite(document, evidence)` is called THEN every produced `Citation` SHALL reference a
   `SOURCE_URL` artifact present in the evidence bundle, and no citation SHALL be emitted without
   backing evidence.
4. IF no `create_file` capability exists THEN `export` SHALL return `ExportOutcome(success=False)`
   flagged unavailable and SHALL NOT raise.

### Requirement 4: Domains are pure composition leaves (the M10 gate)

**User Story:** As the FRIDAY architecture, I want domains to be deletable leaves that own no state,
so that domain depth never becomes a load-bearing dependency or a hidden store.

#### Acceptance Criteria

1. WHEN a domain instance's pure method is invoked twice with identical arguments THEN the system
   SHALL return equal results and SHALL NOT mutate any instance attribute across calls.
2. WHEN a domain module is removed from `sys.modules` THEN `CapabilityRegistry.capability_count` and
   the results of `find_for(verb)` SHALL be unchanged.
3. WHEN any single domain module is deleted THEN every other domain SHALL remain importable and every
   capability SHALL remain intact (no capability lives inside `friday/domains/`).
4. WHEN a domain module's source is scanned THEN it SHALL contain no banned application/site name
   literal and no URL scheme literal in code (docstrings excluded) — Axiom 15.
5. WHEN Ch 41 software-engineering behaviour is requested THEN the `SoftwareDomain` SHALL return a
   `DeferredOutcome(deferred=True)` documenting the v2 deferral and SHALL implement no SWE behaviour.

### Requirement 5: Isolation, conventions, and regression safety

**User Story:** As a FRIDAY maintainer, I want M10 to follow the established milestone conventions and
keep the suite green, so that domain depth integrates cleanly.

#### Acceptance Criteria

1. WHEN M10 modules are added THEN each SHALL carry a `"""Ch NN — ..."""` module docstring
   identifying its chapter.
2. WHEN a domain module's imports are scanned THEN it SHALL import only `friday.capabilities.*`,
   `friday.verification.evidence_law`, `friday.actions.result`, and standard-library modules — never
   `friday.kernel.*`, `friday.memory.*`, `friday.goals.*`, or another domain.
3. WHEN the domain file set is scanned for site-agnosticism THEN no banned app/site name and no URL
   scheme literal SHALL appear in code (Axiom 15).
4. WHEN the full test suite runs under `FRIDAY_DRY_RUN=1` THEN all pre-existing tests (≥ 1044) SHALL
   still pass and M10 SHALL add property, unit, isolation, integration, and gate tests.

## Property-to-Requirement Mapping

| Correctness Property (design.md) | Validates Requirements |
|---|---|
| P1 Domains own no durable state | 1.1, 4.1 |
| P2 Deleting a domain leaves capabilities intact | 4.2, 4.3 |
| P3 Research findings deterministic in gathered evidence | 1.2, 1.3, 1.4 |
| P4 Credibility scores bounded and authority-ordered | 1.2 |
| P5 Contradiction detection symmetric and subject-scoped | 1.3 |
| P6 Hypothesis support is a bounded ratio | 1.4 |
| P7 Delivery requires real confirmation evidence | 2.2, 2.3 |
| P8 Conversation memory immutable and append-only | 2.4 |
| P9 Document render round-trips structure | 3.1, 3.2 |
| P10 Citations reference only real gathered sources | 3.3 |
| P11 Domains hardcode no application or site name | 4.4, 5.3 |
