# Requirements Document

M25 — Learned Choice & Preference Resolution

## Introduction

FRIDAY today asks the user for clarification whenever it reaches an ambiguous
decision — even when the user has answered the same question before in the same
context. This produces repeated friction for recurring, context-identical choices.
FAS §A2.15 mandates that FRIDAY learn recurring user decisions so it asks once when
genuinely necessary, remembers the decision with full context, and automatically
applies it in future equivalent situations — eliminating repeated clarification
without making unsafe assumptions.

All architectural foundations exist: Preference Memory (M21,
`friday/memory/preference_memory.py`), Retrieval Router (M19), Expanded Deliberation
with irreversibility/safety penalties (M16/A2.3), Cognitive State Manager with
`should_interrupt` (M22/A2.12), Reflection + Learning (M20/M17), Failure Memory (M21),
World Model with provenance (M15), and the event bus (Ch 52). This milestone wires
them together into a coherent Preference Resolution Pipeline: detect a decision point,
resolve it from memory or ask, execute, verify, and learn — all as a single general
mechanism (Axiom 15) with no application-specific logic.

## Glossary

- **DecisionPoint**: a first-class structured object representing a state where
  multiple plausible actions exist, the correct choice depends on user preference or
  information FRIDAY does not possess, and the outcomes are consequential. Not tied
  to dialogs or popups.
- **Preference Resolution Pipeline**: the sequence
  Detect → Understand → Context → Query → Evaluate → Apply/Infer/Ask → Execute →
  Verify → Learn that transforms a `DecisionPoint` into a resolved action.
- **PreferenceResolver**: the component implementing the pipeline, integrating with
  Preference Memory, Retrieval Router, Deliberation, and Cognitive State.
- **Contextual scope**: the tuple of (goal, environment, task category, object
  semantics) under which a preference was learned and under which it may be reused.
- **Precedence hierarchy**: the strict ordering of preference sources:
  Explicit instruction > Session choice > Exact contextual preference > Generalized
  preference > Safe inference > Ask user.
- **Preference class**: one of `one-time`, `session`, `contextual`, `general-default`,
  `credential-reference` — determines lifecycle and reuse rules.
- **Empirical confidence**: a [0, 1] score derived exclusively from evidence (explicit
  statement, reuse count, corrections, recency, contradictions) — never LLM-asserted.
- **Reversibility gate**: the decision of whether to act autonomously or ask,
  integrating irreversibility/safety penalties (A2.3) and `should_interrupt` (A2.12).
- **Credential separation boundary**: the security invariant that preference memory
  stores identity references only; secret material remains exclusively in the secure
  credential subsystem.
- **Decision event**: one of the lifecycle bus events (`decision.required`,
  `decision.resolved`, `preference.learned`, `preference.applied`,
  `preference.corrected`, `preference.superseded`) — JSON-serializable and replay-safe.

## Requirements

### Requirement 1: DecisionPoint representation

**User Story:** As the deliberation subsystem, I want a first-class, generic
representation of a recurring choice so that detection, resolution, and learning
operate over a uniform structure independent of any specific application.

#### Acceptance Criteria
1. THE `DecisionPoint` SHALL be a structured object carrying at minimum: a semantic
   identity (decision key), the available options, the current context (goal,
   environment, task category), a risk/reversibility assessment, and any candidate
   preferences retrieved from memory.
2. THE `DecisionPoint` SHALL NOT contain application-specific fields (no app name,
   window handle, dialog identity, URL — Axiom 15); it is keyed by decision semantics
   and context only.
3. THE `DecisionPoint` SHALL be JSON-serializable (`to_dict` / `from_dict`) so it can
   be published on the event bus and persisted for replay.
4. WHEN a `DecisionPoint` is constructed with missing required fields (no decision key,
   no options) THEN THE constructor SHALL raise a validation error immediately (fail
   fast).

### Requirement 2: Decision detection

**User Story:** As FRIDAY's execution engine, I want to recognize when I have reached
an ambiguous multi-option state that depends on user preference, so the resolution
pipeline can activate rather than always interrupting the user.

#### Acceptance Criteria
1. THE detection mechanism SHALL identify a decision point when execution reaches a
   state with multiple plausible actions where the correct choice depends on user
   preference or information FRIDAY does not possess and where the outcome is
   consequential (not a trivial/cosmetic difference).
2. THE detection mechanism SHALL NOT contain application-specific logic (no
   hard-coded patterns for specific apps, sites, or dialogs — Axiom 15); detection is
   based on structural properties of the choice (ambiguity, preference-dependence,
   consequence).
3. WHEN a `DecisionPoint` is detected THEN THE system SHALL publish a
   `decision.required` event on the kernel bus before entering the resolution pipeline.
4. THE detection mechanism SHALL be invocable from within the deliberation/planning
   path and SHALL NOT require a live user-facing dialog to trigger.

### Requirement 3: Preference resolution pipeline

**User Story:** As FRIDAY, I want to resolve a `DecisionPoint` by consulting memory,
evaluating confidence, and either applying a learned preference automatically or
asking only when genuinely necessary — so that recurring identical choices never
produce repeated clarification.

#### Acceptance Criteria
1. THE `PreferenceResolver` SHALL implement the full pipeline: Detect → Understand
   semantics → Determine context → Query Preference Memory via Retrieval Router →
   Evaluate contextual similarity + confidence + freshness → If confident and safe:
   apply automatically | Else if safely inferable: infer and verify | Else: ask user →
   Execute → Verify outcome → Determine reusability → Store/update preference if
   appropriate.
2. WHEN the pipeline queries Preference Memory THEN THE query SHALL go through the
   existing Retrieval Router (M19) — no direct store bypass or parallel retrieval
   mechanism.
3. WHEN the pipeline evaluates a candidate preference THEN THE evaluation SHALL
   consider contextual similarity (goal, environment, task category match), empirical
   confidence, freshness (recency), and contradiction history.
4. WHEN a preference is applied automatically THEN THE system SHALL publish a
   `preference.applied` event and SHALL verify the outcome (post-execution check).
5. IF a preference application fails or produces unexpected results THEN THE system
   SHALL record the failure in Failure Memory (M21) and SHALL NOT reapply the same
   preference in the same context without re-confirmation.

### Requirement 4: Contextual scoping and precedence hierarchy

**User Story:** As the user, I want my preferences respected in the right context but
never blindly reused in dissimilar situations, and I want my explicit instructions to
always override any learned preference.

#### Acceptance Criteria
1. THE system SHALL scope every learned preference by context: goal, environment, task
   category, and object semantics — and SHALL NOT reuse a preference outside its
   learned context without evaluating similarity.
2. THE system SHALL enforce the precedence hierarchy strictly:
   Explicit current instruction > Current-session choice > Exact contextual preference >
   Strong generalized preference > Safe inference > Ask user. A higher-precedence
   source SHALL always override a lower one.
3. WHEN an explicit user instruction contradicts a stored preference THEN THE system
   SHALL follow the instruction immediately and SHALL NOT require confirmation; the
   preference MAY be updated or superseded depending on the instruction's scope.
4. WHEN contextual similarity between the current situation and a stored preference's
   scope falls below a configurable threshold THEN THE system SHALL treat the preference
   as inapplicable and fall through to the next precedence level.

### Requirement 5: Preference lifecycle

**User Story:** As the user, I want FRIDAY to learn from my explicit statements,
repeated selections, and corrections — and to refine preference boundaries over time
without forgetting what it learned before.

#### Acceptance Criteria
1. THE system SHALL learn preferences from three sources: explicit user statements
   (highest initial confidence), repeated consistent selections (confidence grows with
   count), and inferred patterns confirmed by verification.
2. WHEN a preference is learned THEN THE system SHALL record it with full provenance:
   source type (explicit/repeated/inferred), timestamp, context at learning time,
   initial confidence, and a reuse counter initialized to zero.
3. THE system SHALL publish a `preference.learned` event on the kernel bus when a new
   preference is stored.
4. WHEN the user corrects a previous preference THEN THE system SHALL refine the
   contextual boundary (narrowing the scope where the old preference applies) rather
   than destroying the history; THE system SHALL publish a `preference.corrected` event
   and SHALL increment the correction counter.
5. WHEN a preference is superseded by a strictly broader or contradictory one THEN THE
   system SHALL mark the old preference with `superseded_by` and publish a
   `preference.superseded` event; the old preference remains queryable for provenance
   but is no longer applied.
6. THE system SHALL assign each preference a class (`one-time`, `session`,
   `contextual`, `general-default`, `credential-reference`) that determines its reuse
   scope and expiration rules.
7. THE empirical confidence of a preference SHALL be computed exclusively from evidence
   (explicit statement weight, reuse count, corrections, recency decay,
   contradictions) and SHALL NEVER be LLM-asserted or set by prompt output.

### Requirement 6: Reversibility-gated asking

**User Story:** As the user, I want FRIDAY to act autonomously on low-risk reversible
decisions when confident, but always confirm before taking irreversible or
consequential actions — so I get smooth flow without unsafe assumptions.

#### Acceptance Criteria
1. WHEN a decision is low-risk, reversible, and cheap-to-verify AND the matched
   preference has high empirical confidence THEN THE system MAY apply the preference
   autonomously and verify the outcome without asking.
2. WHEN a decision is irreversible, consequential, or security-sensitive THEN THE
   system SHALL require either very high confidence (configurable threshold) or
   explicit user confirmation before acting.
3. THE reversibility assessment SHALL integrate with the Deliberation utility's
   irreversibility/safety penalties (§A2.3) — the same scoring mechanism used for
   action selection.
4. THE asking-gate SHALL integrate with the Cognitive State Manager's
   `should_interrupt(urgency)` (§A2.12) — when `should_interrupt` returns False (user
   is deeply focused, low urgency), the system SHALL defer non-critical questions
   rather than interrupting.
5. WHEN a preference is applied autonomously and the outcome verification fails THEN
   THE system SHALL escalate to asking the user on the next occurrence (confidence
   reduction).

### Requirement 7: Credential separation

**User Story:** As the user, I want FRIDAY to remember which identity/account I prefer
for a context without ever storing my actual passwords or tokens in preference memory.

#### Acceptance Criteria
1. THE Preference Memory SHALL store identity references only (e.g.,
   `preferred_identity: personal_google`, `deploy_account: work_aws`) — never secret
   material (passwords, tokens, API keys, certificates).
2. Secret material SHALL remain exclusively in the secure credential subsystem and
   SHALL NEVER appear in preference memory entries, kernel events, logs, or bus
   payloads.
3. IF a preference recording attempt contains what appears to be secret material (by
   heuristic: high-entropy strings, known token patterns) THEN THE system SHALL reject
   the recording and log a security warning — this is a hard boundary, not a
   best-effort filter.
4. THE `credential-reference` preference class SHALL contain only a reference key that
   maps to the vault; the resolver SHALL dereference it through the secure credential
   subsystem at application time.

### Requirement 8: Explainability and provenance

**User Story:** As the user, I want to understand why FRIDAY made an automatic choice
and where the preference came from, so I can trust the system and correct it if wrong.

#### Acceptance Criteria
1. THE system SHALL be able to explain any automatic choice, citing: preference source
   (explicit statement / repeated selection / inference), when learned (timestamp),
   context at learning time, current empirical confidence, reuse count, correction
   count, and last successful verification timestamp.
2. WHEN a preference is applied automatically THEN THE `preference.applied` event
   SHALL carry full provenance (source preference key, confidence, context match
   score, reuse count) so observability consumers can audit decisions.
3. THE provenance chain SHALL be preserved end-to-end: from the `decision.required`
   event through resolution to the `decision.resolved` event, each step's reasoning is
   traceable.
4. WHEN the user asks "why did you choose X?" THEN THE system SHALL retrieve and
   present the provenance of the applied preference in natural language.

### Requirement 9: General mechanism — no application-specific logic

**User Story:** As the architecture, I require the learned-choice mechanism to work for
arbitrary recurring choices without per-application code branches.

#### Acceptance Criteria
1. THE entire Preference Resolution Pipeline SHALL be generic — keyed by decision
   semantics and contextual scope, never by application name, site, dialog identity,
   or window handle (Axiom 15).
2. THE mechanism SHALL work equally for: profile/account selection, download-path
   choices, default-app preferences, device selection, template choices, permission
   grants, formatting preferences, and any other recurring user choice — without any
   code specific to these domains.
3. THE `DecisionPoint` identity SHALL be derived from the semantic structure of the
   choice (what is being decided, in what context, with what options) — not from the
   UI surface or application that triggered it.
4. NEITHER the detection logic NOR the resolution logic SHALL contain conditional
   branches based on specific application identifiers or domain names.

### Requirement 10: Event-driven and replay-safe integration

**User Story:** As the event system, I want all decision/preference lifecycle events
published on the kernel bus in JSON-serializable form so the event store remains
replay-compatible and observability consumers can react.

#### Acceptance Criteria
1. THE system SHALL publish the following events on the kernel bus at the appropriate
   lifecycle points: `decision.required`, `decision.resolved`, `preference.learned`,
   `preference.applied`, `preference.corrected`, `preference.superseded`.
2. EVERY published event SHALL be JSON-serializable (all payload fields are
   JSON-projectable primitives, lists, or dicts — no opaque objects, no callables).
3. THE event payloads SHALL carry sufficient context for replay: decision key, context,
   resolved option, confidence, provenance, and timestamp — so a replayer can
   reconstruct the decision history without re-executing the pipeline.
4. THE event handlers (subscribers) SHALL be defensive: they SHALL never raise into the
   bus, and malformed events SHALL be silently ignored (consistent with the defensive
   handler pattern established in M21/M19).

### Requirement 11: Additive, safe integration

**User Story:** As the maintainer, I want the preference resolution system wired so it
changes no default behavior and never breaks hermetic tests.

#### Acceptance Criteria
1. THE `PreferenceResolver` SHALL be opt-in in the reactive-loop / bootstrap wiring
   (attached only when supplied / within the guarded kernel-execution path) so hermetic
   tests perform no unbidden disk I/O or bus subscriptions.
2. THE production bootstrap SHALL attach the `PreferenceResolver` when kernel execution
   is enabled, wiring it to the existing Preference Memory, Retrieval Router, Cognitive
   State Manager, and Deliberation utility.
3. THE default (flag-off) path SHALL be byte-unchanged; existing execution paths that do
   not encounter a detected `DecisionPoint` SHALL have zero overhead from this feature.
4. THE full existing test suite SHALL remain green (zero failures, zero new flaky tests)
   after integration.

### Requirement 12: Verification artifacts

**User Story:** As the maintainer, I require every milestone to ship its evidence.

#### Acceptance Criteria
1. THE milestone SHALL include property-based tests covering: DecisionPoint
   construction + serialization round-trip; precedence hierarchy enforcement;
   contextual scoping (similarity threshold); empirical confidence computation
   (never LLM-asserted invariant); reversibility-gated asking (integration with
   should_interrupt + irreversibility scoring); credential separation (secret material
   rejection); event serialization round-trip; pipeline idempotence (resolving the same
   DecisionPoint twice with no state change yields the same result).
2. THE milestone SHALL include acceptance scenario tests covering the directive
   scenarios A through H: (A) first-time ask, (B) same-context automatic reuse,
   (C) different-context re-ask, (D) explicit override, (E) correction refines
   boundary, (F) irreversible-action gate, (G) credential-reference without secret
   leakage, (H) explain-why audit.
3. THE milestone SHALL update the FAS (A2.15 → Built) and the traceability matrix, and
   produce an after-milestone architecture review with a full-suite checkpoint (zero
   failures).
