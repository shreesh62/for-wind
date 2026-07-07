# Implementation Plan: M11 — Capability Evolution, Plugins, Benchmarks & Federation

## Overview

This plan converts the approved M11 design into incremental, code-focused steps. M11 adds four
kernel-event-driven subsystems onto the existing M1–M10 substrate by **wiring, wrapping, and
extending** existing code — never rewriting it: the M7 `CapabilityCandidate`
(`friday/environments/unknown/`), the `CapabilityRegistry.promote_candidate` seam
(`friday/capabilities/registry.py`), the M8 `CompetenceModel` (`friday/competence/model.py`), and the
M4 `ResourceRegistry` (`friday/resources/`).

Ordering is dependency-driven and validates functionality early through code:

1. **Data models + Benchmarks first** (`friday/benchmarks/`) — the scoring core the pipeline gates on,
   directly unit/property testable.
2. **Evolution** (`friday/evolution/`) — `CapabilityLifecycle` → `RollbackManager` → `PromotionPipeline`
   (which composes the benchmark runner + registry seam).
3. **Plugins** (`friday/plugins/`) — manifest + sandbox + loader + registry, feeding the pipeline.
4. **Federation** (`friday/federation/`) — node directory + resource federation over the M4 registry.
5. **Tests** — unit, all 11 Hypothesis properties, AST isolation, kernel-event integration, and the M11
   gate.
6. **Final regression checkpoint** (keep ≥ 1097 tests green).

Every pure core (`BenchmarkRunner.run` / `RegressionDetector.is_regression` /
`CapabilityLifecycle.can_transition` / `PromotionPipeline.submit` / `PluginSandbox.validate` /
`ResourceFederation.join`) is separated from kernel wiring so it is directly unit- and property-testable
under `FRIDAY_DRY_RUN=1`. All new modules carry a `"""Ch NN — ..."""` docstring, contain no hardcoded
app/site names or URLs (Axiom 15), and communicate only through kernel events (Ch 52); evolution never
imports plugin internals, plugins import no kernel/world/goals/safety/verification, and federation
imports only `friday.resources` + `friday.events`.

**Language:** Python 3.12. **Test command:** `python -m pytest tests/friday/ -q`.

## Tasks

- [x] 1. Benchmarks — `friday/benchmarks/`
  - [x] 1.1 Create the benchmark data models and scoring core
    - Create `friday/benchmarks/__init__.py` and `friday/benchmarks/suite.py` with a `"""Ch 55 — ..."""`
      docstring
    - Define frozen `BenchmarkScenario` (`id`, `description`, `weight=1.0`) and frozen `BenchmarkReport`
      (`capability_id`, `score`, `scenarios_run`, `scenarios_passed`, `latency_ms=0.0`)
    - Implement `BenchmarkSuite` (`scenarios()`, `add(scenario)`) and `BenchmarkRunner.run(capability_id,
      evaluate) -> BenchmarkReport` where `score = passed_weight / total_weight` in `[0,1]` (0.0 when no
      scenarios), a throwing `evaluate` counts as a failed scenario, deterministic for deterministic
      `evaluate`
    - Implement `RegressionDetector.is_regression(incumbent, candidate, *, tolerance=0.0)` returning
      `candidate < incumbent - tolerance` (monotonic in candidate)
    - _Requirements: 2.1, 2.3, 2.4, 5.1_

  - [x]* 1.2 Write property + unit tests for benchmark scoring and regression
    - **Property 5: Benchmark score is a bounded weighted ratio**
    - **Property 4: Promotion never regresses the incumbent** (the `is_regression` monotonicity half)
    - Unit-test empty suite → 0.0, all-pass → 1.0, all-fail → 0.0, throwing scenario counts as failure
    - **Validates: Requirements 2.1, 2.3, 2.4**

- [x] 2. Capability Evolution — `friday/evolution/`
  - [x] 2.1 Implement CapabilityLifecycle and RollbackManager
    - Create `friday/evolution/__init__.py`, `friday/evolution/lifecycle.py` (`"""Ch 27 — ..."""`), and
      `friday/evolution/rollback.py` (`"""Ch 27 — ..."""`)
    - Define `LifecycleState(str, Enum)` and implement `CapabilityLifecycle` (`state_of`,
      `can_transition`, `transition` raising on illegal, `is_usable_for(id, risk)` where DRAFT/
      EXPERIMENTAL are never usable for `irreversible`)
    - Implement `RollbackManager` (`record_stable`, `can_rollback`, `rollback` raising `LookupError`
      when no snapshot)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x]* 2.2 Write property tests for lifecycle and rollback
    - **Property 1: Lifecycle transitions are legal-only**
    - **Property 2: Unverified capabilities cannot perform irreversible actions**
    - **Property 6: Rollback restores the last-known-good snapshot**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

  - [x] 2.3 Implement the PromotionPipeline (pure core + kernel wiring)
    - Create `friday/evolution/pipeline.py` with a `"""Ch 27 — ..."""` docstring
    - Define `PromotionOutcome(str, Enum)` and frozen `PromotionResult`
    - Implement `__init__(registry, lifecycle, runner, *, min_benchmark_score=0.6)` and pure
      `submit(candidate) -> PromotionResult`: run the benchmark, reject when `score <
      min_benchmark_score` OR the candidate regresses the incumbent, else `promote_candidate` on the
      registry + advance lifecycle `DRAFT → EXPERIMENTAL`; deterministic wrt inputs
    - Implement `attach(kernel)` subscribing to `capability.candidate`; emit `capability.promoted` /
      `capability.rejected` via `make_event`; read payload defensively, never raise into the tick loop
    - Import only `friday.capabilities.*`, `friday.evolution.*`, `friday.benchmarks.*`,
      `friday.events.*`, stdlib
    - _Requirements: 2.2, 2.3, 2.5, 5.2_

  - [x]* 2.4 Write property test for benchmark-gated promotion
    - **Property 3: Promotion requires a passing benchmark**
    - **Validates: Requirements 2.1, 2.2**

- [x] 3. Plugins — `friday/plugins/`
  - [x] 3.1 Implement plugin manifest, sandbox, loader, and registry
    - Create `friday/plugins/__init__.py`, `friday/plugins/manifest.py`, `friday/plugins/sandbox.py`,
      `friday/plugins/loader.py`, `friday/plugins/registry.py`, each with a `"""Ch 54 — ..."""` docstring
    - Define frozen `PluginManifest` (`name`, `version`, `author`, `capabilities`, `permissions`,
      `signature`) and frozen `LoadFailure`
    - Implement `PluginSandbox.validate(manifest) -> (bool, str)` rejecting any manifest whose
      `permissions` reference `kernel`/`world`/`goals`/`safety`/`verification`; `PluginLoader.load`
      producing `CapabilityCandidate`-shaped objects (or `LoadFailure` on malformed/unsigned/rejected);
      `PluginRegistry` (`install`, `uninstall`, `get`) tracking manifests by name
    - Import only `friday.evolution.*`, `friday.capabilities.*`, `friday.events.*`, stdlib — NEVER
      kernel/world/goals/safety/verification
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 5.2_

  - [x]* 3.2 Write property tests for plugin sandbox and pipeline-only entry
    - **Property 7: Plugins cannot request protected subsystems**
    - **Property 8: Plugin capabilities enter only through the pipeline**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

- [x] 4. Federation — `friday/federation/`
  - [x] 4.1 Implement NodeDirectory and ResourceFederation
    - Create `friday/federation/__init__.py`, `friday/federation/directory.py`, and
      `friday/federation/federation.py`, each with a `"""Ch 47 — ..."""` docstring
    - Define frozen `FederatedNode` (`node_id`, `resources`, `healthy=True`)
    - Implement `NodeDirectory` (`add`, `remove`, `healthy_nodes`) and `ResourceFederation(registry,
      directory)` with `join(node)` (register each resource namespaced by `node_id`, emit
      `federation.node_joined`), `leave(node_id)` (unregister exactly those, emit `federation.node_left`),
      and `attach(kernel)`
    - Import only `friday.resources.*`, `friday.events.*`, stdlib
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.2_

  - [x]* 4.2 Write property tests for federation namespacing and descriptor-only transmission
    - **Property 9: Federation namespaces resources and is reversible**
    - **Property 10: Federation transmits only resource descriptors**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

- [x] 5. Package surfaces
  - [x] 5.1 Finalize the public export surfaces
    - Ensure `friday/benchmarks/__init__.py`, `friday/evolution/__init__.py`,
      `friday/plugins/__init__.py`, and `friday/federation/__init__.py` export their public classes and
      data models with `"""Ch NN — ..."""` docstrings
    - _Requirements: 5.1_

- [x] 6. Tests — isolation, integration, gate
  - [x]* 6.1 Write the AST isolation / site-agnosticism test
    - Add `tests/friday/test_m11_isolation.py` mirroring `test_m10_isolation.py`: each M11 module carries
      a `"""Ch NN — ..."""` docstring; evolution imports no plugin internals; plugins import no
      kernel/world/goals/safety/verification; federation imports only resources + events; no banned
      app/site name or URL scheme literal in code
    - **Property 11: M11 modules hardcode no application or site name**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

  - [x]* 6.2 Write the kernel-event integration test
    - Add `tests/friday/test_m11_integration.py`: real `CognitiveKernel` + `CapabilityRegistry`; a
      `CapabilityCandidate` flows through the pipeline (passing benchmark) and emits `capability.promoted`
      landing on the event log; a plugin manifest flows loader → sandbox → pipeline; a `FederatedNode`
      joins and its namespaced resources appear in the `ResourceRegistry`; run under `FRIDAY_DRY_RUN=1`
    - _Requirements: 2.5, 3.1, 4.1, 5.5_

  - [x]* 6.3 Write the M11 gate test
    - Add `tests/friday/test_m11_gate.py`: assert a capability is promoted ONLY via sandbox → benchmark
      → promote; a regressing candidate is rejected and (given a recorded snapshot) rolled back; a
      goal-graph resource requirement is satisfiable by a federated node; and re-running with identical
      inputs produces identical ordered M11 event types (determinism)
    - **Validates: Requirements 1.4, 2.2, 2.3, 4.1**

- [x] 7. Final regression checkpoint
  - [x] 7.1 Run the full suite and confirm green
    - Run `python -m pytest tests/friday/ -q`; confirm ≥ 1097 pre-existing tests plus the new M11 tests
      pass under `FRIDAY_DRY_RUN=1`
    - _Requirements: 5.5_

## Notes

- Tasks marked with `*` are test tasks and may run alongside or right after their implementation task
  within the same wave.
- All work is additive under `friday/benchmarks/`, `friday/evolution/`, `friday/plugins/`,
  `friday/federation/`; no M1–M10 file is modified.
- Frontends (Ch 57) are deferred to a documented kernel-API client contract only; no UI is built in M11
  (mirrors the M10 SWE deferral).
- Every module carries a `"""Ch NN — ..."""` docstring and contains no hardcoded app/site name or URL
  scheme literal (Axiom 15).
- All tests set `os.environ.setdefault("FRIDAY_DRY_RUN", "1")` before importing any `friday` module so
  the existing suite (≥ 1097 tests) stays green.
- The M11 gate (task 6.3): a capability enters the registry only through sandbox → benchmark → promote,
  a regressing candidate is rejected/rolled back, and one goal graph can be advanced by a federated
  node's resources.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1", "4.2"] },
    { "id": 3, "tasks": ["2.4", "3.2", "5.1"] },
    { "id": 4, "tasks": ["6.1", "6.2", "6.3"] },
    { "id": 5, "tasks": ["7.1"] }
  ]
}
```
