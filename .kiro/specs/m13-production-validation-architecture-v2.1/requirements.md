# Requirements Document

M13 — Production Validation & Architecture v2.1

## Introduction

M13 qualifies the Cognitive Kernel for production through real-world validation and strengthens the
Architecture Specification to v2.1 — **without changing any production default or implementing any new
subsystem**. Part 1 delivers the validation harness, evidence framework, parity report, and explicit
promotion criteria to answer "Is the Cognitive Kernel production-ready?"; if no, it says why; if yes,
it delivers a rollback strategy and a single isolated default-flip commit. Part 2 amends the FAS with
normative sections for the reviewed architectural improvements, then updates the traceability matrix,
dependency graph, affected-milestone analysis, and revised roadmap. Implementation of the new
subsystems resumes only after the revised architecture is reviewed and approved.

## Glossary

- **Production validation**: exercising the kernel path (`FRIDAY_USE_KERNEL_EXECUTION=1`) against
  realistic end-to-end goals and collecting evidence, without changing defaults.
- **Promotion criteria**: the explicit, measurable conditions the kernel must satisfy before becoming
  the default.
- **Parity report**: a structured comparison of legacy vs kernel paths on identical workloads.
- **requires_live**: a scenario needing real browser/desktop/network/GPU, executable only on the
  user's machine (not in the sandbox `FRIDAY_DRY_RUN` environment).
- **FAS v2.1 amendments**: normative additions to the Architecture Specification.
- **Traceability matrix**: concept → FAS chapter → code state → owning milestone.

## Requirements

### Requirement 1: Production validation tooling (no default change)

**User Story:** As the FRIDAY maintainer, I want a runnable validation harness that exercises the
kernel path against realistic goals and collects evidence, so that a production-readiness decision is
based on real-world behavior — without changing any default.

#### Acceptance Criteria

1. WHEN the validation harness runs THEN it SHALL NOT change any production default; the bridge
   `use_kernel_execution` default SHALL remain False and the environment SHALL be restored afterward.
2. WHEN a scenario is validated THEN the runner SHALL submit the identical goal to both the legacy and
   kernel paths and record both results without cross-contamination.
3. WHEN a scenario runs THEN evidence (event logs, goal transitions, decisions, timings, errors) SHALL
   be captured in a JSON-serializable `ValidationEvidence` record.
4. IF a scenario is flagged `requires_live` AND the environment is `FRIDAY_DRY_RUN` THEN it SHALL be
   reported SKIPPED (never fabricated pass/fail).
5. WHEN the scenario suite is defined THEN it SHALL cover all 18 required categories (browser, desktop,
   multi-environment, research, file generation, long-running, interruption/resume, crash recovery,
   browser-failure recovery, unknown-app, concurrent goals, human confirmation, event replay,
   checkpoint restore, memory consistency, world-model consistency, goal-graph consistency,
   deterministic replay).

### Requirement 2: Parity report and readiness verdict

**User Story:** As the maintainer, I want a parity report and an explicit readiness verdict, so I know
whether — and exactly why — the kernel is or is not production-ready.

#### Acceptance Criteria

1. WHEN evidence has been collected THEN the report generator SHALL compare legacy vs kernel across
   behavior, correctness, reliability, performance, recovery quality, and determinism, deterministically
   for identical inputs.
2. WHEN the validation plan is authored THEN it SHALL define explicit, measurable promotion criteria
   that must ALL be satisfied before the kernel becomes the default.
3. WHEN the milestone concludes THEN it SHALL produce a readiness verdict answering "Is the Cognitive
   Kernel production-ready?"; IF no, it SHALL state exactly which criteria are unmet; IF yes, it SHALL
   include a rollback strategy and a single isolated commit plan to flip the default.
4. WHEN real-world results are unavailable in the sandbox THEN the verdict SHALL be explicitly gated on
   the user executing the harness on a real machine, and SHALL NOT fabricate results.

### Requirement 3: Architecture v2.1 normative amendments

**User Story:** As the architect, I want the reviewed engineering improvements added to the FAS as
normative sections, so the architecture is strengthened before further implementation.

#### Acceptance Criteria

1. WHEN the FAS v2.1 amendments are authored THEN they SHALL add or expand normative sections for ALL
   of: World Model (belief freshness/TTL/refresh/provenance/evidence graph/staleness); Environment
   Intelligence (fingerprints/UI fingerprints/capability invalidation/version-aware adaptation);
   Deliberation (expanded utility function + rollback/compensating actions/undo/recovery contracts);
   Capability System (Draft→Experimental→Verified→Stable→Deprecated→Archived lifecycle + per-capability
   version/success-rate/reliability/dependencies/failure-modes/benchmarks); Skill Evolution pipeline;
   Resource Manager (CPU/GPU/memory/local-vs-cloud/model-selection/parallel/scheduling/optimization);
   Retrieval Router (World Model/Memory/Filesystem/RAG/APIs/Capability Registry/Connectors); Exploration
   Engine (observation/object-graph/affordance/safe-experiment/reflection/capability-generation, never
   app-specific); Statistical Evaluation (empirical competence scoring, never LLM self-reported);
   Reflection (Immediate/Session/Long-Term/Skill/Architectural); Memory (Working/Episodic/Semantic/
   Procedural/Capability/Failure/Preference); Cognitive State Manager (focus/active-goal/attention/
   interruptibility/cognitive-load/reasoning-depth/modes/background-state).
2. WHEN each amendment is written THEN it SHALL cross-reference the existing FAS chapter(s) it extends
   and note the current code state (built/partial/absent).
3. WHEN the amendments are complete THEN they SHALL preserve the invariants: one Kernel, one World
   Model, one Goal Graph, one Competence Model; general mechanisms over task-specific logic; no
   app-specific logic; no hardcoded workflows.

### Requirement 4: Traceability, dependencies, roadmap (planning only)

**User Story:** As the maintainer, I want the traceability matrix, dependency graph, and a revised
roadmap so implementation can resume in the optimal order after approval.

#### Acceptance Criteria

1. WHEN the traceability matrix is produced THEN each v2.1 concept SHALL map to FAS chapter(s), current
   code state, and an owning (existing or new) milestone.
2. WHEN the dependency graph is produced THEN it SHALL express the build-order dependencies among the
   new/expanded subsystems.
3. WHEN the roadmap is produced THEN it SHALL identify affected milestones and recommend the optimal
   implementation order with rationale.
4. WHEN M13 concludes THEN NO new subsystem SHALL have been implemented and NO production default SHALL
   have changed — M13 stops at the review/approval gate.

### Requirement 5: Regression and conventions

**User Story:** As a maintainer, I want M13's tooling to stay out of production code and keep the suite
green, so the milestone adds validation capability without any runtime risk.

#### Acceptance Criteria

1. WHEN the validation tooling is added THEN it SHALL live under `scripts/` (non-production) and carry
   `"""..."""` docstrings; documents SHALL live under `docs/`.
2. WHEN the full suite runs under `FRIDAY_DRY_RUN=1` THEN all pre-existing tests (≥ 1227) SHALL still
   pass and M13 SHALL add tooling tests only (no production code change).

## Property-to-Requirement Mapping

| Correctness Property (design.md) | Validates Requirements |
|---|---|
| P1 Runner changes no production default | 1.1 |
| P2 Identical workload on both paths | 1.2 |
| P3 Evidence structured and serializable | 1.3 |
| P4 Live-only scenarios skipped safely | 1.4 |
| P5 Parity report deterministic | 2.1 |
