# Requirements Document

M16 — Deliberation v2 (Expanded Utility & Recovery Contracts)

## Introduction

The v2.1 traceability matrix marks **A2.3 Deliberation** as *Partial* — the current
`friday/deliberation/utility.py::UtilityFunction` scores a candidate with only three terms
(`confidence * expected_value − cost − risk_weight * risk`, plus a flat irreversibility
penalty), and there is no recovery-contract concept. FAS §A2.3 requires substantially more:

- **§A2.3.1 Expanded utility** computed from at least nine terms:
  `Expected Goal Progress + Information Gain + Future Optionality − Risk − Time −
  Resource Cost − Attention Cost − Irreversibility − Opportunity Cost`, where no single
  term dominates (weights are policy).
- **§A2.3.2 Action safety term** — an explicit penalty for actions touching
  protected/irreversible surfaces (integrating the Ch 35 permission boundary).
- **§A2.3.3 Recovery contracts** — every action declares
  `{undo, rollback, verification, compensation, recovery}`; an action with no undo path
  must raise its required confidence and incur the full irreversibility penalty, and may
  require human confirmation.
- **§A2.3.4 Rollback plans & compensating actions** — where a true undo is impossible, a
  compensating action is defined for the Recovery Engine (Ch 34).

This milestone delivers Deliberation v2 **additively**: it extends `CandidateAction` with
defaulted term/contract fields (existing construction unaffected), adds an
`ExpandedUtilityFunction` and a `RecoveryContract`, and integrates a confidence-raising gate
for no-undo actions — without changing the existing `UtilityFunction`/`Deliberator` default
behavior. Scoring stays deterministic and evidence-shaped (no model calls; the 4th law), and
carries no application-specific logic (Axiom 15).

## Glossary

- **Expanded utility**: the nine-term §A2.3.1 utility score for a candidate action.
- **Utility term**: one contributor to the score (goal progress, information gain, future
  optionality, risk, time, resource cost, attention cost, irreversibility, opportunity cost).
- **RecoveryContract**: a candidate's declared `{undo, rollback, verification, compensation,
  recovery}` — how an action can be walked back if it goes wrong.
- **Undo path**: a candidate is undoable when its prediction is reversible AND its recovery
  contract provides an undo/rollback/compensation.
- **Action safety term**: an explicit penalty for actions touching protected/irreversible
  surfaces.
- **Required confidence**: the minimum prediction confidence a candidate must clear to be
  chosen; raised for actions with no undo path.

## Requirements

### Requirement 1: Recovery contracts

**User Story:** As the deliberator, I want every action to declare how it can be walked back,
so irreversible actions are treated with appropriate caution.

#### Acceptance Criteria
1. THE system SHALL define a `RecoveryContract` carrying `undoable`, `rollback`,
   `verification`, `compensation`, and `recovery` descriptors.
2. THE `RecoveryContract` SHALL expose whether the action has an undo path (undoable, or a
   rollback/compensation is defined).
3. A `CandidateAction` SHALL carry an optional `RecoveryContract`; when absent, the candidate
   SHALL be treated as having no declared undo path (conservative default).
4. `CandidateAction` SHALL remain constructible exactly as before (all new fields defaulted;
   the `RecoveryContract` and expanded terms are additive).
5. THE `RecoveryContract` SHALL be JSON-projectable for decision records / events.

### Requirement 2: Expanded utility function

**User Story:** As the deliberator, I want a richer utility so decisions weigh progress,
information, optionality, and the full cost/risk picture — not just confidence and risk.

#### Acceptance Criteria
1. THE `ExpandedUtilityFunction` SHALL compute a score from at least the nine §A2.3.1 terms:
   Expected Goal Progress, Information Gain, Future Optionality (positive contributors); Risk,
   Time, Resource Cost, Attention Cost, Irreversibility, Opportunity Cost (negative
   contributors).
2. EACH term's contribution SHALL be governed by a configurable policy weight; no single term
   SHALL be able to dominate the score by construction (weights are bounded and
   documented — no hardcoded term dwarfs the rest).
3. THE score SHALL be deterministic and side-effect free (no model calls, no I/O) — a pure
   function of the candidate and the configured weights (the 4th law).
4. `CandidateAction` SHALL carry the additional term inputs (`information_gain`,
   `future_optionality`, `time_cost`, `resource_cost`, `attention_cost`, `opportunity_cost`)
   as defaulted fields, sourced from evidence/estimates — never self-asserted competence.
5. THE existing `UtilityFunction` behavior and the existing three-term scoring SHALL be
   unchanged (Deliberation v2 is additive; the simple scorer remains available).

### Requirement 3: Action safety term & irreversibility

**User Story:** As the safety boundary, I want protected/irreversible actions penalized so the
less reversible an action is, the higher the bar it must clear.

#### Acceptance Criteria
1. THE expanded utility SHALL apply an explicit safety penalty when a candidate touches a
   protected/irreversible surface (a `touches_protected` signal), integrating the Ch 35
   permission boundary.
2. THE irreversibility term SHALL apply the full irreversibility penalty when the candidate
   is not reversible OR has no undo path (per its recovery contract).
3. FOR two otherwise-identical candidates, the one that is irreversible / protected SHALL
   score strictly lower than the reversible / unprotected one.

### Requirement 4: Confidence gate for no-undo actions

**User Story:** As the deliberator, I want no-undo actions to require higher confidence before
they can be chosen, so unrecoverable mistakes are rare.

#### Acceptance Criteria
1. THE system SHALL compute a per-candidate `required_confidence` that is raised above the
   baseline when the candidate has no undo path.
2. WHEN selecting the best candidate, a no-undo candidate SHALL be chosen ONLY if its
   prediction confidence meets its raised required confidence AND its utility clears the bar.
3. THE decision SHALL expose (for the record) whether a candidate required elevated confidence
   and whether it would require human confirmation (no undo path + high impact).
4. THE gate SHALL never auto-approve an irreversible action that fails its raised confidence
   requirement.

### Requirement 5: Additive integration & determinism

**User Story:** As the maintainer, I want Deliberation v2 wired so it changes no default
behavior and stays deterministic.

#### Acceptance Criteria
1. THE `Deliberator` SHALL support selecting between the simple `UtilityFunction` (default,
   unchanged) and the `ExpandedUtilityFunction` (opt-in) without altering existing call sites.
2. ALL scoring/gating SHALL be deterministic and replay-safe (no model calls, no clock, no
   network); given the same candidates and weights, results SHALL be identical.
3. THE full existing test suite SHALL remain green (zero failures); no existing deliberation
   behavior regresses.

### Requirement 6: Verification artifacts

**User Story:** As the maintainer, I require every milestone to ship its evidence.

#### Acceptance Criteria
1. THE milestone SHALL include property/unit tests covering the recovery contract, the
   nine-term expanded utility (each term moves the score in the correct direction; no-dominance),
   the safety/irreversibility penalties, the confidence gate, and additive/deterministic
   behavior.
2. THE milestone SHALL include a deterministic, hermetic deliberation benchmark (ranking /
   gate behavior over synthetic candidate sets) that is NOT recorded into the committed
   competence baseline.
3. THE milestone SHALL update the FAS (A2.3 → Built), the traceability matrix, and produce an
   after-milestone architecture review, with a full-suite checkpoint (zero failures).
