# Implementation Plan: M15 — World Model v2 (Belief Freshness, TTL, Provenance, Staleness)

## Overview

This plan implements M15 additively over the existing `Belief` and `WorldModel` primitives in Python,
reusing `KnowledgeAging.freshness` (M9) as the single decay curve. Work proceeds bottom-up so each step
builds on the previous with no orphaned code:

1. Build the new pure `friday/world/provenance.py` module (no dependencies) and its property tests.
2. Extend `Belief` with M15 fields + methods (freshness delegation, staleness, provenance helpers) and its
   property tests.
3. Extend `WorldModel` with the staleness sweep + kernel-mediated event emission and its property/integration tests.
4. Add integration, concurrency, and API-stability example tests, then a final full-suite verification.

Binding invariants held throughout: additive-only (existing signatures/defaults/returns unchanged), one
`WorldModel` per kernel, kernel-mediated outbound communication only, no application-specific logic
(Axiom 15), reuse of `KnowledgeAging` (no duplicated decay curve), and deterministic replay-safe methods
that take `now` explicitly.

Property tests use Hypothesis with a minimum of 100 examples each and carry a tag comment in the format
`Feature: m15-world-model-v2, Property N: ...`. New test files ONLY — existing test assertions are never modified.

## Tasks

- [x] 1. Establish baseline and confirm existing test locations
  - Run `$env:PYTHONPATH="C:\Projects\JARVIS\for wind"; python -m pytest tests/friday/ -q` and record the passing count (expected 1245).
  - Run `$env:PYTHONPATH="C:\Projects\JARVIS\for wind"; python -m pytest tests/world/ -q` to confirm existing `Belief`/`WorldModel` tests pass and to establish the authoritative location of existing belief/world-model tests (may live under `tests/world/` and/or `tests/friday/`).
  - Verify `friday/temporal/aging.py` `KnowledgeAging.freshness(observed_at, now)` signature is available for reuse (do NOT modify it).
  - Do not write production or test code in this task; this is a read/verify checkpoint that fixes the baseline the additive changes must preserve.
  - _Requirements: 1.5, 5.5_

- [x] 2. Create the provenance model module (`friday/world/provenance.py`)
  - [x] 2.1 Implement `VerificationStatus`, `RefreshPolicy` enums, `MAX_DERIVATION_CHAIN`, and `BeliefProvenance` dataclass
    - Add a module-level docstring matching existing codebase style (Ch 9 conventions).
    - Define `VerificationStatus(str, Enum)` with `UNVERIFIED="unverified"`, `VERIFIED="verified"`, `CONTRADICTED="contradicted"`.
    - Define `RefreshPolicy(str, Enum)` with `ON_READ`, `ON_STALE`, `PERIODIC`, `NEVER`.
    - Define `MAX_DERIVATION_CHAIN = 20`.
    - Define non-frozen `@dataclass BeliefProvenance` with `supporting_observations`, `contradicting_observations`, `derivation_chain` (all `List[str]` via `default_factory=list`), and `verification_status: VerificationStatus = VerificationStatus.UNVERIFIED`.
    - Keep the module domain-agnostic (Axiom 15): no belief/observation imports required.
    - _Requirements: 3.1, 3.5, 5.7, 5.8_

  - [x] 2.2 Implement pure helper `derive_verification_status(supporting, contradicting, current)`
    - Return `CONTRADICTED` iff `contradicting` non-empty AND `supporting` empty (Req 3.6).
    - Promote `UNVERIFIED` -> `VERIFIED` when a supporting observation exists (Req 3.3).
    - Otherwise preserve `current`. Pure function, no side effects.
    - _Requirements: 3.3, 3.6_

  - [x] 2.3 Implement pure helper `build_derivation_chain(parent_chains_and_ids, own_id)`
    - Merge each parent's chain followed by the parent id, preserving root->immediate-parent order.
    - De-duplicate while preserving first-seen order; drop any occurrence of `own_id` (no self-reference, Req 3.7); drop entries that would introduce a cycle.
    - Truncate to the last `MAX_DERIVATION_CHAIN` entries (immediate-parent-ward), preserving order (Req 3.1, 3.8).
    - Total and pure: never raises on adversarial input.
    - _Requirements: 3.1, 3.2, 3.7, 3.8_

  - [x]* 2.4 Write property test for verification status derivation (new file `tests/world/test_provenance_properties.py`)
    - **Property 10: Verification status derivation rule**
    - **Validates: Requirements 3.3, 3.6**
    - Tag: `Feature: m15-world-model-v2, Property 10: ...`; `@settings(max_examples=100)` minimum.

  - [x]* 2.5 Write property test for derivation chain DAG bound (append to `tests/world/test_provenance_properties.py`)
    - **Property 12: Derivation chain is an ordered DAG bounded to 20**
    - **Validates: Requirements 3.1, 3.2, 3.7, 3.8**
    - Include adversarial parents (self-referencing ids, duplicates, oversized chains). Tag + `@settings(max_examples=100)`.

- [x] 3. Extend `Belief` with M15 fields and freshness delegation (`friday/world/belief.py`)
  - [x] 3.1 Add M15 fields and additive `__post_init__` clamping
    - Append defaulted fields after existing fields: `half_life_seconds: float = 86400.0`, `ttl_seconds: Optional[float] = None`, `refresh_policy: RefreshPolicy = RefreshPolicy.ON_STALE`, `refresh_cost: float = 0.0`, `high_impact: bool = False`, `provenance: BeliefProvenance = field(default_factory=BeliefProvenance)`.
    - Import from `friday.world.provenance`.
    - In `__post_init__`, keep the existing confidence clamp unchanged and ADD `refresh_cost = max(0.0, min(1.0, refresh_cost))`. Retain non-None `ttl_seconds <= 0` as-is (never raise).
    - Preserve `decay`, `reinforce`, `contradict`, and `expired` exactly (signatures, defaults, returns, behaviour).
    - _Requirements: 1.7, 2.1, 2.3, 2.4, 3.1, 5.1, 5.3, 5.6, 5.8_

  - [x] 3.2 Implement `freshness(now)` delegating to `KnowledgeAging`
    - `freshness(self, now: float) -> float` constructs `KnowledgeAging(half_life_seconds=self.half_life_seconds)` and returns `.freshness(self.observed_at, now)`.
    - Never call `time.time()`; `now` is an explicit float argument.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8_

  - [x] 3.3 Implement `is_stale(now, staleness_threshold=0.1)`
    - Return `True` if `ttl_seconds` is not `None` and `now - observed_at > ttl_seconds` (with `ttl_seconds <= 0` => stale for any `now > observed_at`), OR if `freshness(now) < staleness_threshold`.
    - Pure; explicit `now`; no clock access.
    - _Requirements: 2.2, 2.7, 4.7_

  - [x] 3.4 Implement provenance-aware `add_supporting_observation` / `add_contradicting_observation`
    - Each returns a NEW `Belief` (build a NEW `BeliefProvenance` copying lists; do not mutate the original).
    - `add_supporting_observation(id)`: append `id` to `provenance.supporting_observations` AND legacy `supporting_evidence`; recompute `verification_status` via `derive_verification_status`.
    - `add_contradicting_observation(id)`: append `id` to `provenance.contradicting_observations` AND legacy `contradicting_evidence`; recompute `verification_status`.
    - Do not alter existing `reinforce`/`contradict` signatures or behaviour.
    - _Requirements: 3.3, 3.4, 3.6, 3.9_

  - [x] 3.5 Implement `derive_from(parents)`
    - Return a NEW `Belief` whose `provenance.derivation_chain` is `build_derivation_chain([(p.provenance.derivation_chain, p.id) for p in parents], self.id)`.
    - Rejects self-id and cycles, bounded to `MAX_DERIVATION_CHAIN`.
    - _Requirements: 3.1, 3.2, 3.7, 3.8_

  - [x]* 3.6 Write property test for freshness correctness (new file `tests/world/test_belief_freshness_properties.py`)
    - **Property 1: Freshness correctness (formula, clamp, boundaries, M9 delegation)**
    - **Validates: Requirements 1.1, 1.2, 1.4, 1.5, 1.7**
    - Tag + `@settings(max_examples=100)` minimum.

  - [x]* 3.7 Write property test for half-life anchor and monotonicity (append to `tests/world/test_belief_freshness_properties.py`)
    - **Property 2: Freshness half-life anchor and monotonicity**
    - **Validates: Requirements 1.3**

  - [x]* 3.8 Write property test for freshness determinism (append to `tests/world/test_belief_freshness_properties.py`)
    - **Property 3: Freshness determinism (replay-safety)**
    - **Validates: Requirements 1.8, 6.2, 6.3**

  - [x]* 3.9 Write property test for reinforce restoring freshness (append to `tests/world/test_belief_freshness_properties.py`)
    - **Property 4: Reinforce restores freshness to 1.0**
    - **Validates: Requirements 1.6**

  - [x]* 3.10 Write property test for refresh_cost clamp (append to `tests/world/test_belief_freshness_properties.py`)
    - **Property 5: refresh_cost is clamped to [0, 1]**
    - **Validates: Requirements 2.4**

  - [x]* 3.11 Write property test for minimal construction defaults (append to `tests/world/test_belief_freshness_properties.py`)
    - **Property 13: Minimal construction defaults all M15 fields**
    - **Validates: Requirements 3.5, 5.3**

  - [x]* 3.12 Write property test for replace() preserving M15 fields (append to `tests/world/test_belief_freshness_properties.py`)
    - **Property 14: reinforce/contradict preserve M15 fields through replace()**
    - **Validates: Requirements 5.4**

  - [x]* 3.13 Write property test for observation-add mirroring legacy fields (append to `tests/world/test_provenance_properties.py`)
    - **Property 11: Observation add appends, mirrors legacy fields, updates status**
    - **Validates: Requirements 3.4, 3.9**

- [x] 4. Checkpoint - Ensure provenance + Belief tests pass
  - Run `tests/world/test_belief_freshness_properties.py`, `tests/world/test_provenance_properties.py`, and existing `tests/world/test_belief.py`.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Extend `WorldModel` with staleness sweep and event emission (`friday/world/world_model.py`)
  - [x] 5.1 Add `staleness_threshold` ctor param and capture kernel in `attach`
    - `__init__(self, decay_rate: float = 0.01, staleness_threshold: float = 0.1)`: keep existing fields unchanged; add `self._staleness_threshold` and `self._kernel: Optional[Any] = None`.
    - `attach(kernel)`: set `self._kernel = kernel` THEN keep the existing `kernel.subscribe("observation.received", self._on_observation_event)` call unchanged.
    - Do not change any existing method signature/default/return.
    - _Requirements: 4.1, 5.2, 5.6, 5.9_

  - [x] 5.2 Implement `stale_beliefs(now)` scan under RLock
    - Acquire `self._lock` for the entire read/recompute/collect/order sequence.
    - Iterate `self._fusion.beliefs`; skip hard-expired beliefs (expiry outranks staleness, Req 2.8); collect beliefs where TTL exceeded (incl. `ttl_seconds <= 0` => stale for `now > observed_at`) OR `freshness(now) < self._staleness_threshold` (recomputed via `KnowledgeAging`, never cached).
    - Return list ordered by the stable key `(observed_at, id)`; return `[]` when nothing is stale.
    - _Requirements: 2.2, 4.1, 4.2, 4.5, 4.6, 4.7, 6.1, 6.4_

  - [x] 5.3 Implement `_publish_stale_flagged(belief, freshness)` and wire into the sweep
    - For each stale `high_impact` belief, build a signed `Event("belief.stale_flagged", source="world_model", payload={"belief_id": belief.id, "freshness": freshness})` and route via `self._kernel.publish_event(event)`.
    - No-op silently if `self._kernel is None`; catch and swallow any exception from `publish_event` so the sweep result is never compromised; never raise into the caller.
    - Emit after building the result list, in the same deterministic order.
    - _Requirements: 4.3, 4.4, 5.9_

  - [x]* 5.4 Write property test for stale classification (new file `tests/world/test_world_model_staleness_properties.py`)
    - **Property 6: Stale classification (TTL, freshness threshold, non-positive TTL)**
    - **Validates: Requirements 2.2, 4.1, 4.3, 4.7**
    - Tag + `@settings(max_examples=100)` minimum.

  - [x]* 5.5 Write property test for non-expiring TTL beliefs (append to `tests/world/test_world_model_staleness_properties.py`)
    - **Property 7: Non-expiring TTL beliefs are stale only by freshness decay**
    - **Validates: Requirements 2.7**

  - [x]* 5.6 Write property test for hard expiry precedence (append to `tests/world/test_world_model_staleness_properties.py`)
    - **Property 8: Hard expiry outranks staleness**
    - **Validates: Requirements 2.8**

  - [x]* 5.7 Write property test for sweep idempotence and order-stability (append to `tests/world/test_world_model_staleness_properties.py`)
    - **Property 9: Staleness sweep is idempotent and order-stable (no cached freshness)**
    - **Validates: Requirements 4.2, 6.4**

- [x] 6. Checkpoint - Ensure staleness sweep tests pass
  - Run `tests/world/test_world_model_staleness_properties.py` and existing `tests/world/test_world_model.py`.
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Integration, concurrency, and API-stability example tests
  - [x]* 7.1 Write event-emission integration test with a fake kernel (append to `tests/world/test_world_model_staleness_properties.py` or a new `tests/world/test_world_model_events.py`)
    - Fake kernel captures `publish_event` calls; assert a `belief.stale_flagged` event with payload `{belief_id, freshness}` is emitted for a stale high-impact belief and routes through `kernel.publish_event`.
    - Assert emission is skipped silently when no kernel is attached, and the sweep still returns results.
    - _Requirements: 4.4, 4.5, 5.9_

  - [x]* 7.2 Write API-unchanged example tests (new file `tests/world/test_m15_api_stability.py`)
    - Call `Belief.decay`, `reinforce`, `contradict`, `expired`; `WorldModel.ingest`, `observed_world`, `unmet_conditions`, `relate`, `attach`; assert signatures/returns intact (incl. `ingest -> List[Belief]`) and minimal `Belief(description, confidence, source)` still constructs.
    - Assert no existing default parameter changed (`WorldModel(decay_rate=0.01)`, Belief defaults).
    - _Requirements: 5.1, 5.2, 5.3, 5.6_

  - [x]* 7.3 Write concurrency and reentrancy tests (append to `tests/world/test_m15_api_stability.py`)
    - Spawn threads doing `ingest` and `stale_beliefs` concurrently; assert no exceptions and results consistent with a serial order.
    - Assert reentrant (nested) RLock acquisition does not deadlock.
    - _Requirements: 3.10, 6.1, 6.5, 6.6_

- [x] 8. Final checkpoint - Full suite verification and default-preservation smoke
  - Run `$env:PYTHONPATH="C:\Projects\JARVIS\for wind"; python -m pytest tests/friday/ tests/world/ -q` under `FRIDAY_DRY_RUN=1`; confirm ≥1245 pre-existing pass plus all new M15 tests, zero failures/errors.
  - Assert new modules expose `__doc__` and that no existing default parameter value changed (`Belief` defaults, `WorldModel(decay_rate=0.01)`).
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 5.5, 5.6, 5.7, 5.8_

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP, but they encode the 14 Correctness Properties and the non-PBT example/integration/smoke coverage and are strongly recommended.
- Each task references specific requirements and/or design properties for traceability.
- Property tests use Hypothesis with ≥100 examples each and a `Feature: m15-world-model-v2, Property N: ...` tag comment; new test files ONLY, never modifying existing assertions.
- Checkpoints ensure incremental validation as each layer (provenance → Belief → WorldModel) lands.
- Invariants preserved throughout: additive-only, one WorldModel per kernel, kernel-mediated communication, no application-specific logic (Axiom 15), reuse of `KnowledgeAging` decay curve, deterministic `now`-based methods.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1"] },
    { "id": 1, "tasks": ["2.2", "2.3"] },
    { "id": 2, "tasks": ["3.1", "2.4", "2.5"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.5"] },
    { "id": 4, "tasks": ["3.6", "3.7", "3.8", "3.9", "3.10", "3.11", "3.12", "3.13"] },
    { "id": 5, "tasks": ["5.1"] },
    { "id": 6, "tasks": ["5.2"] },
    { "id": 7, "tasks": ["5.3"] },
    { "id": 8, "tasks": ["5.4", "5.5", "5.6", "5.7", "7.1", "7.2", "7.3"] }
  ]
}
```
