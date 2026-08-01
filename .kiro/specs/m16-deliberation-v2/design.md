# Design: M16 — Deliberation v2 (Expanded Utility & Recovery Contracts)

## Overview

Deliberation v2 extends the existing deliberation module **additively** to satisfy FAS §A2.3:
a nine-term `ExpandedUtilityFunction`, a first-class `RecoveryContract` on each candidate, an
action-safety/irreversibility penalty, and a confidence gate that raises the bar for actions
with no undo path. The existing simple `UtilityFunction` and `Deliberator` default behavior
are left untouched — the expanded scorer is opt-in. All scoring is deterministic and
evidence-shaped (no model calls, the 4th law), and carries no application-specific logic
(Axiom 15).

## Architecture

```
CandidateAction (extended, all new fields defaulted)
  ├─ prediction: PredictedOutcome (existing; confidence, reversible)
  ├─ expected_value / cost / risk               (existing)
  ├─ information_gain / future_optionality       (NEW positive terms)
  ├─ time_cost / resource_cost / attention_cost / opportunity_cost  (NEW negative terms)
  ├─ touches_protected: bool                     (NEW safety signal)
  └─ recovery_contract: RecoveryContract | None  (NEW; undo/rollback/verification/…)
                    │
                    ▼
       ExpandedUtilityFunction(weights)          UtilityFunction (existing, unchanged)
         score() = Σ wᵢ·termᵢ − safety − irrev          score() = simple 3-term
         required_confidence(candidate)
         best(candidates, baseline_min_conf)
                    │
                    ▼
              Deliberator(utility=…)  ← selects simple (default) OR expanded
```

### Modified / new components

| Component | File | Change |
|---|---|---|
| Recovery contract | `friday/deliberation/recovery_contract.py` (NEW) | `RecoveryContract` dataclass |
| Candidate fields | `friday/deliberation/candidate.py` | additive defaulted term/contract fields |
| Expanded utility | `friday/deliberation/expanded_utility.py` (NEW) | `ExpandedUtilityFunction`, `UtilityWeights` |
| Deliberator seam | `friday/deliberation/deliberator.py` | accept an injected utility (default = simple) |
| Package exports | `friday/deliberation/__init__.py` | export the new types (additive) |
| Benchmark | `friday/benchmarks/deliberation.py` (NEW) | deterministic ranking/gate benchmark |

## Components and Interfaces

### C1 — `RecoveryContract` (frozen dataclass, NEW)
Fields: `undoable: bool = False`, `rollback: str = ""`, `verification: str = ""`,
`compensation: str = ""`, `recovery: str = ""` (the descriptor strings name the plan; empty =
none). Properties: `has_undo_path` → `undoable or bool(rollback) or bool(compensation)`
(Requirement 1.2); `to_dict()` JSON-safe (Requirement 1.5). Immutable and pure.

### C2 — `CandidateAction` additive fields (`candidate.py`)
Add defaulted fields (frozen dataclass, all with defaults so existing construction and
`build(...)` are unaffected — Requirement 1.4, 2.4):
`information_gain: float = 0.0`, `future_optionality: float = 0.0`, `time_cost: float = 0.0`,
`resource_cost: float = 0.0`, `attention_cost: float = 0.0`, `opportunity_cost: float = 0.0`,
`touches_protected: bool = False`, `recovery_contract: Optional[RecoveryContract] = None`.
A helper `has_undo_path` → `prediction.reversible AND (recovery_contract.has_undo_path if
present else False)` (a missing contract ⇒ no declared undo path — conservative,
Requirement 1.3). Bounded fields clamped in `__post_init__` where sensible; construction never
raises.

### C3 — `UtilityWeights` + `ExpandedUtilityFunction` (NEW `expanded_utility.py`)
- `UtilityWeights` (frozen dataclass): one weight per term, all defaulting to a bounded value
  (e.g. `1.0` for positives, documented penalty weights for negatives) plus
  `safety_penalty` and `irreversibility_penalty`. Weights are **policy** and bounded so no
  single term dominates by construction (Requirement 2.2); a `__post_init__` clamps them to a
  documented non-negative range.
- `ExpandedUtilityFunction(weights=UtilityWeights())`:
  - `score(candidate)` (Requirement 2.1, 2.3): 
    `w_progress·(confidence·expected_value) + w_ig·information_gain
     + w_opt·future_optionality − w_risk·risk − w_time·time_cost − w_res·resource_cost
     − w_attn·attention_cost − w_opp·opportunity_cost − irreversibility − safety`,
    where `irreversibility = irreversibility_penalty` when `not candidate.has_undo_path`
    (Requirement 3.2) else 0, and `safety = safety_penalty` when `touches_protected`
    (Requirement 3.1) else 0. Pure/deterministic.
  - `required_confidence(candidate, baseline)` (Requirement 4.1): returns `baseline` raised
    (e.g. `max(baseline, no_undo_floor)`) when the candidate has no undo path.
  - `rank(candidates)` and `best(candidates, min_utility, baseline_min_confidence)`
    (Requirement 4.2, 4.4): a candidate is eligible only if `score ≥ min_utility` AND
    `prediction.confidence ≥ required_confidence(candidate, baseline)`; a no-undo candidate
    that fails its raised confidence is never chosen.
  - `requires_human_confirmation(candidate)` (Requirement 4.3): `no undo path AND
    touches_protected` (high impact) → True.

### C4 — `Deliberator` seam (`deliberator.py`)
Accept an injected scorer: `Deliberator(..., utility=None)` defaults to the existing
`UtilityFunction()` (behavior byte-unchanged, Requirement 5.1); callers may pass an
`ExpandedUtilityFunction`. The `DecisionRecord` gains optional additive fields recording the
elevated-confidence / human-confirmation flags when the expanded scorer is used.

## Data Models

- `RecoveryContract` (C1) — new JSON-projectable value object.
- `CandidateAction` (C2) — extended with defaulted term/contract fields; still frozen.
- `UtilityWeights` (C3) — bounded policy weights.
- No new persistence; decision records stay in-memory/event-projectable.

## Correctness Properties

### Property 1: recovery contract semantics
`has_undo_path` is true iff undoable or a rollback/compensation is declared; a candidate with
no contract has no undo path; `to_dict()` round-trips through `json.dumps`.
**Validates: Requirements 1.1, 1.2, 1.3, 1.5**

### Property 2: additive construction unchanged
Every existing `CandidateAction(...)` / `CandidateAction.build(...)` call still constructs
identically; the simple `UtilityFunction.score` returns the same value as before for a
candidate with default new fields.
**Validates: Requirements 1.4, 2.5, 5.1**

### Property 3: term monotonicity + no dominance
Increasing a positive term (goal progress / information gain / future optionality) never
decreases the expanded score; increasing a negative term (risk/time/resource/attention/
opportunity) never increases it. With bounded weights, no single term can move the score
beyond the combined range of the others (no-dominance check).
**Validates: Requirements 2.1, 2.2, 2.3**

### Property 4: safety + irreversibility penalties
For two otherwise-identical candidates, the irreversible (or no-undo) one scores strictly
lower, and the `touches_protected` one scores strictly lower, by the configured penalties.
**Validates: Requirements 3.1, 3.2, 3.3**

### Property 5: confidence gate
`required_confidence` is strictly higher for a no-undo candidate; `best(...)` never selects a
no-undo candidate whose confidence is below its raised requirement, even if its raw score is
highest; `requires_human_confirmation` is true exactly for no-undo + protected candidates.
**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

### Property 6: determinism
`score` / `rank` / `best` are pure: identical inputs+weights yield identical outputs across
repeated calls; no model/clock/network use.
**Validates: Requirements 2.3, 5.2**

## Error Handling

Structured-error-model compliant: scoring is a pure computation over dataclass fields; malformed
numeric inputs are clamped in `__post_init__` rather than raising. No blanket exception
swallowing. The scorer performs no I/O so there is no degradation boundary to guard.

## Testing Strategy

Hypothesis property tests (≥100 examples, tagged `# Feature: m16-deliberation-v2, Property N`)
for Properties 1–6 over synthetic candidates with randomized term values/weights. A
deterministic, hermetic **deliberation benchmark** (`friday/benchmarks/deliberation.py`) ranks
synthetic candidate sets and checks the gate (a high-utility but no-undo/low-confidence
candidate is correctly withheld); it is NOT part of the 5-domain scorecard and is never written
to the committed baseline (mirrors the M19/M20/M17 policy). Full regression suite must stay
green (zero failures).

## Traceability

- FAS Ch 10 / 34 / 35; v2.1 amendment **A2.3 — Deliberation v2** (Partial → Built).
- Reuses the existing `CandidateAction` / `Deliberator`; integrates the Ch 35 permission
  boundary via the `touches_protected` signal and the Ch 34 Recovery Engine via the
  `RecoveryContract` (compensation/rollback). No duplicate deliberation system; deterministic,
  evidence-only; no application-specific logic (Axiom 15).
