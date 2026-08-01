# Design: M17 — Skill Evolution Pipeline

## Overview

The Skill Evolution Pipeline formalizes FAS §A2.5.1
(`Observation → Experiment → Reflection → Verification → Compilation → Optimization →
Generalization → Capability Registry`) as one kernel-attached **coordinator** over the
mechanisms that already exist. It is a thin, additive layer: it does not re-implement pattern
discovery, generalization, promotion, or the lifecycle. It consumes the events those
subsystems already emit — M9 `learning.validated` (a skill has generalized) and M20
`reflection.skill` (a capability accrued verified low-error experience) — tracks each skill's
stage, and when a skill carries BOTH signals it emits a single `skill.candidate` **proposal**
offering the skill to the M11 evidence-gated `PromotionPipeline`. It never self-promotes,
never writes memory, and never fabricates competence.

## Architecture

```
   M9 LearningEngine ── learning.validated ──┐
                                             ▼
   M20 SkillReflector ── reflection.skill ──▶ SkillEvolutionPipeline
                                             │  (per-(capability,environment) skill record;
                                             │   stage ladder; dual-signal latch)
                                             ▼
                                   skill.candidate  (JSON-safe proposal)
                                             │
                                             ▼
                       (offered to) M11 PromotionPipeline  ── evidence-gated ──▶ CapabilityLifecycle
                       [existing; NOT invoked/mutated by this coordinator]
```

The coordinator only observes events and emits `skill.candidate`. Actual promotion — sandbox,
benchmark, lifecycle transition — remains entirely inside the existing M11 `PromotionPipeline`
and is triggered by whatever already drives it; M17 merely surfaces *which* skills are ready.

### Modified / new components

| Component | File | Change |
|---|---|---|
| Stage taxonomy | `friday/learning/skill_stage.py` (NEW) | `SkillStage` enum (8 ordered stages) |
| Coordinator | `friday/learning/skill_pipeline.py` (NEW) | `SkillRecord`, `SkillEvolutionPipeline`, `attach_skill_pipeline` |
| Bootstrap | `friday/api/server.py` | attach the pipeline in the guarded kernel path |
| Benchmark | `friday/benchmarks/skill_evolution.py` (NEW) | deterministic maturation/candidate benchmark |

Isolation (mirrors the M9/M20 rule): `skill_pipeline.py` MUST NOT import `friday.memory.*`,
`friday.competence.*`, or `friday.evolution.*`, and MUST NOT reference
`FridayMemory`/`MemoryStore` or call the lifecycle/promotion API. Its only side effect is
`kernel.publish_event(make_event("skill.candidate", ...))`.

## Components and Interfaces

### C1 — `SkillStage` (enum, NEW `friday/learning/skill_stage.py`)
A `str` enum with the eight FAS §A2.5.1 members in order: `OBSERVATION, EXPERIMENT,
REFLECTION, VERIFICATION, COMPILATION, OPTIMIZATION, GENERALIZATION, REGISTRY`. An `ordinal`
property (declaration index) makes maturity comparable; `.value` is JSON-safe. Kept in its
own tiny module so both the pipeline and the benchmark import it without cycles.

### C2 — `SkillRecord` (dataclass)
Per-skill state keyed by `(capability, environment)`: `stage: SkillStage`,
`generalized: bool` (a `learning.validated` was seen), `candidate_flag: bool` (a
`reflection.skill` was seen), `emitted: bool` (a `skill.candidate` was already emitted —
dedup latch), and a small evidence summary (e.g. last mean_error / verified_rate from the
`reflection.skill` payload, sample counts). JSON-projectable via `to_dict()`.

### C3 — `SkillEvolutionPipeline`
- `attach(kernel)` subscribes to `learning.validated` and `reflection.skill` (and observes
  `learning.rejected` to avoid qualifying a rejected skill). No-op without a kernel.
- `_on_learning_validated`: resolve the skill key from the payload (`capability`,
  `environment`); mark `generalized=True`; advance `stage` to at least `GENERALIZATION`.
  Then evaluate the candidate condition.
- `_on_reflection_skill`: mark `candidate_flag=True` and record the evidence summary; advance
  stage toward `GENERALIZATION` only via `learning.validated` (the skill signal alone does
  not fabricate generalization). Then evaluate the candidate condition.
- `_on_learning_rejected`: clear `generalized` for that skill (a rejected learning does not
  qualify) — verified-only invariant (Requirement 4.3).
- **Candidate condition:** when `generalized AND candidate_flag AND NOT emitted`, emit one
  `skill.candidate` proposal, set `emitted=True` (dedup, Requirement 3.1). Advance stage to
  `REGISTRY` (offered to the registry/promotion pipeline).
- Bounded store: an insertion-ordered dict capped at `max_skills` (oldest evicted).
  Handlers wrapped defensively; never raise into the bus.
- Query: `skill(capability, environment) -> dict` and `skills() -> dict` snapshot
  (Requirement 3.3).

### C4 — `attach_skill_pipeline(kernel, *, pipeline=None, **kwargs) -> SkillEvolutionPipeline`
Reusable wiring helper (mirrors `attach_reactive_loop` / `attach_reflection_layers`):
constructs or reuses a pipeline, attaches it, returns it. No-op holder semantics without a
kernel; attach failure isolated.

### C5 — Bootstrap wiring (`friday/api/server.py`)
Within the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` block (after `attach_reactive_loop` and
`attach_reflection_layers`, since this pipeline consumes their `learning.validated` /
`reflection.skill` output), call `attach_skill_pipeline(kernel)` and expose it as
`kernel.skill_pipeline`. Additive; default path byte-unchanged; wiring failure logged with
structured context, never crashes bootstrap.

## Data Models

- `SkillStage` — the new enum (C1).
- `SkillRecord` — in-memory per-skill state (C2); no new persistence. `skill.candidate`
  payloads are plain JSON-safe dicts: `{capability, environment, stage, generalized,
  candidate_flag, evidence:{...}}`. The consumed `learning.validated` / `reflection.skill`
  payloads are read defensively (fields may be absent → skip, never raise).

## Correctness Properties

### Property 1: stage taxonomy totality + ordering
`SkillStage` has exactly eight members in the FAS §A2.5.1 order; ordinals strictly
increasing 0..7; every `.value` JSON-serializes.
**Validates: Requirements 1.1, 1.2**

### Property 2: maturation tracking
A `learning.validated` for a skill advances it to ≥ `GENERALIZATION`; a `reflection.skill`
sets the candidate flag; the per-skill store never exceeds the bound; malformed events never
raise and never create junk records.
**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

### Property 3: dual-signal candidate emission + dedup
A `skill.candidate` is emitted exactly once and only when BOTH `learning.validated` and
`reflection.skill` have been seen for the skill; neither signal alone emits; re-delivering
either signal does not re-emit; payload is JSON-safe and carries the identity + evidence.
**Validates: Requirements 3.1, 3.2, 3.3**

### Property 4: reuse + evidence-only isolation
The module imports no memory/competence/evolution modules and references no
`FridayMemory`/`MemoryStore`/lifecycle API; its only emitted event type is `skill.candidate`;
a `learning.rejected` clears the generalized flag so a rejected skill cannot become a
candidate; without a kernel the pipeline is a no-op.
**Validates: Requirements 4.1, 4.2, 4.3, 5.2**

### Property 5: no application-specific logic
Skills are keyed only by generic `(capability, environment)` strings; behavior is identical
under arbitrary capability/environment labels (Axiom 15).
**Validates: Requirements 4.4**

## Error Handling

Structured-error-model compliant (A2.14.2): every handler catches narrowly and degrades to a
no-op, never raising into the bus (mirrors M9/M20). No silent blanket swallow without a
justifying comment. Bootstrap wiring guarded and logged. `BaseException` propagates.

## Testing Strategy

Hypothesis property tests (≥100 examples, tagged `# Feature: m17-skill-evolution, Property N`)
for Properties 1–5 using a fake/real `CognitiveKernel` and synthetic
`learning.validated` / `reflection.skill` / `learning.rejected` streams. A deterministic,
hermetic **skill-evolution benchmark** (`friday/benchmarks/skill_evolution.py`) drives
synthetic streams through the pipeline and measures candidate-emission precision/recall
(a skill with both signals emits exactly one candidate; single-signal skills emit none); it
is NOT part of the 5-domain scorecard and is never written to the committed baseline (mirrors
the M19/M20/M24 policy). Full regression suite must stay green (zero failures).

## Traceability

- FAS Ch 15/27; v2.1 amendment **A2.5 — Skill evolution pipeline** (Partial → Built).
- Consumes M9 `learning.validated` and M20 `reflection.skill`; offers `skill.candidate` to
  the M11 `PromotionPipeline`. No duplicate learning/promotion/lifecycle system; no direct
  memory writes; no self-promotion; verified-only; no application-specific logic (Axiom 15).
