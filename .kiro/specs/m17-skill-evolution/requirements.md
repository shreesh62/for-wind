# Requirements Document

M17 — Skill Evolution Pipeline

## Introduction

The v2.1 traceability matrix marks **A2.5 Skill evolution pipeline** as *Partial* — the
pieces exist but the unified pipeline is not formalized. Today:

- M9 `friday/learning/engine.py::LearningEngine` folds a `VerifiedExperience` through
  `PatternDiscovery → Generalizer → validation`, emitting `learning.validated` (and a
  procedural `memory.candidate`) when a principle validates.
- M11 `friday/evolution/pipeline.py::PromotionPipeline` runs an explicit capability
  candidate through `sandbox → benchmark → promote`, advancing the
  `friday/evolution/lifecycle.py::CapabilityLifecycle` (DRAFT → EXPERIMENTAL → …).
- M20 `friday/cognition/reflection_layers.py::SkillReflector` now emits a
  `reflection.skill` per-capability candidate proposal when a capability accumulates
  verified low-error experience.

What is missing is the **coordinator** that connects these into the normative FAS §A2.5.1
pipeline: `Observation → Experiment → Reflection → Verification → Compilation →
Optimization → Generalization → Capability Registry`. Nothing currently consumes the
`reflection.skill` signal together with `learning.validated` to recognize that a skill has
matured enough to be offered as a formal promotion candidate.

This milestone delivers that coordinator **additively** as a kernel-attached
`SkillEvolutionPipeline` that reuses the existing learning and evolution mechanisms — it
introduces no duplicate learning system, no duplicate promotion pipeline, and no duplicate
lifecycle. It tracks each skill's stage, and when a skill has BOTH a validated
generalization AND a skill-layer candidate signal, it emits a `skill.candidate` **proposal**
event offering the skill to the existing evidence-gated `PromotionPipeline`. The pipeline
never self-promotes, never writes memory directly, and never fabricates competence — only
verified, evidence-backed experience advances a skill (Ch 15.19 / the 4th law).

## Glossary

- **Skill**: a maturing capability identified by `(capability, environment)`, progressing
  through the eight normative stages before it is a promotion candidate.
- **Skill stage**: one of the FAS §A2.5.1 stages
  (`OBSERVATION, EXPERIMENT, REFLECTION, VERIFICATION, COMPILATION, OPTIMIZATION,
  GENERALIZATION, REGISTRY`) — the ordered maturation ladder.
- **SkillEvolutionPipeline**: the kernel-attached coordinator that advances a skill through
  the stages by consuming existing events and emits a `skill.candidate` proposal when ready.
- **`learning.validated`**: the M9 event signalling a generalized, validated principle
  (the GENERALIZATION stage is reached).
- **`reflection.skill`**: the M20 per-capability candidate proposal (verified low-error
  experience accrued).
- **`skill.candidate`**: the new proposal event this pipeline emits offering a matured skill
  to the M11 `PromotionPipeline` (a proposal — promotion remains the pipeline's
  evidence-gated decision).
- **Proposes, not promotes**: the coordinator emits events and tracks stage; it never
  advances the lifecycle or writes memory itself.

## Requirements

### Requirement 1: Skill stage taxonomy

**User Story:** As the architecture, I want the eight normative pipeline stages represented
so a skill's maturity is explicit and ordered.

#### Acceptance Criteria
1. THE system SHALL define a `SkillStage` taxonomy with exactly eight ordered members:
   `OBSERVATION, EXPERIMENT, REFLECTION, VERIFICATION, COMPILATION, OPTIMIZATION,
   GENERALIZATION, REGISTRY` (FAS §A2.5.1 order).
2. THE taxonomy SHALL be ordered (an ordinal makes maturity comparable) and JSON-projectable.

### Requirement 2: Track skill maturation from existing signals

**User Story:** As FRIDAY, I want each skill's stage tracked from the events the learning and
reflection subsystems already emit, so maturation is observed, not re-derived.

#### Acceptance Criteria
1. THE pipeline SHALL attach to a kernel and consume the existing events
   `learning.validated` and `reflection.skill` (and MAY observe `learning.rejected`).
2. THE pipeline SHALL maintain a bounded per-`(capability, environment)` skill record
   tracking the highest stage reached and the signals seen (validated-generalization flag,
   skill-candidate flag).
3. WHEN a `learning.validated` for a skill is seen THEN the skill SHALL advance to at least
   the `GENERALIZATION` stage.
4. THE per-skill store SHALL be bounded (oldest evicted) so memory use never grows without
   limit, and handlers SHALL never raise into the event bus.

### Requirement 3: Emit a promotion candidate when a skill matures

**User Story:** As the M11 promotion pipeline, I want a proposal when a skill is ready for
formal promotion, so I can run it through the evidence-gated candidate flow.

#### Acceptance Criteria
1. WHEN a skill has BOTH a validated generalization (`learning.validated`) AND a
   skill-layer candidate signal (`reflection.skill`) THEN the pipeline SHALL emit exactly
   one `skill.candidate` proposal event for that skill (deduplicated — not re-emitted while
   the skill remains a candidate).
2. THE `skill.candidate` payload SHALL be JSON-serializable and SHALL carry the
   `(capability, environment)` identity, the reached stage, and the evidence signals that
   qualified it (never a fabricated competence value).
3. THE pipeline SHALL expose a query returning the current per-skill stage/record.

### Requirement 4: Reuse, not duplicate; evidence-only

**User Story:** As the architecture, I require the coordinator to reuse existing mechanisms
and honor the evidence invariants.

#### Acceptance Criteria
1. THE pipeline SHALL NOT implement its own pattern discovery, generalization, promotion, or
   lifecycle — it coordinates the existing M9 learning and M11 evolution subsystems.
2. THE pipeline SHALL NOT write long-term memory directly, SHALL NOT advance the capability
   lifecycle itself, and SHALL NOT self-report competence; its only side effect is emitting
   `skill.*` proposal events (promotion remains the M11 evidence-gated decision).
3. ONLY verified, evidence-backed signals SHALL advance a skill (a `learning.rejected` or an
   unverified experience SHALL NOT qualify a skill as a candidate).
4. THE pipeline SHALL contain no application-specific logic (no app/site/window identity —
   Axiom 15); a skill is keyed only by generic `(capability, environment)`.

### Requirement 5: Replay-safe, additive, safe integration

**User Story:** As the maintainer, I want the pipeline wired so it changes no default
behavior, is replay-compatible, and never breaks hermetic tests.

#### Acceptance Criteria
1. EVERY emitted `skill.*` payload SHALL be JSON-serializable so the append-only
   `EventStore` stays replay-compatible.
2. THE pipeline SHALL attach via a reusable wiring helper, attaching only within the guarded
   kernel-execution path; it SHALL be inert without a kernel and degrade safely on wiring
   failure (never crashing bootstrap).
3. THE default (flag-off) path SHALL be byte-unchanged and the full existing test suite
   SHALL remain green (zero failures).

### Requirement 6: Verification artifacts

**User Story:** As the maintainer, I require every milestone to ship its evidence.

#### Acceptance Criteria
1. THE milestone SHALL include property/unit tests covering the stage taxonomy, maturation
   tracking from events, the dual-signal candidate emission (+ dedup), the reuse/evidence
   isolation invariants (no direct memory write, no self-promotion, verified-only), bounded
   storage, and defensive handlers.
2. THE milestone SHALL include a deterministic, hermetic skill-evolution benchmark (skill
   maturation + candidate emission over synthetic event streams) that is NOT recorded into
   the committed competence baseline.
3. THE milestone SHALL update the FAS (A2.5 → Built), the traceability matrix, and produce
   an after-milestone architecture review, with a full-suite checkpoint (zero failures).
