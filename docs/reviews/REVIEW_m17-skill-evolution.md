# After-Milestone Review — M17 Skill Evolution Pipeline

> Governance gate. Delivers **A2.5 Skill evolution pipeline** (previously *Partial*
> in the v2.1 traceability matrix) additively as one kernel-attached **coordinator**
> over the mechanisms that already exist. It formalizes the eight-stage FAS §A2.5.1
> ladder, consumes M9 `learning.validated` + M20 `reflection.skill`, tracks each
> skill's stage, and emits a single deduplicated `skill.candidate` **proposal** when a
> skill carries BOTH signals — offering it to the M11 evidence-gated
> `PromotionPipeline`. No duplicate learning / promotion / lifecycle system; the
> "proposes, never promotes" invariant (Ch 15.19 / the 4th law) is preserved. All new
> code is additive and inert without a kernel.

## 0. Milestone under review

- Milestone: `M17 — Skill Evolution Pipeline`
- Target capability: the normative FAS §A2.5.1 pipeline
  (`Observation → Experiment → Reflection → Verification → Compilation → Optimization →
  Generalization → Capability Registry`) surfaced as a live coordinator that recognizes
  when a skill has matured enough to be offered as a formal promotion candidate.
- Summary of what M17 delivered:
  - **`SkillStage` 8-stage taxonomy** (`friday/learning/skill_stage.py` — NEW). A `str`
    enum with exactly eight ordered members (`OBSERVATION, EXPERIMENT, REFLECTION,
    VERIFICATION, COMPILATION, OPTIMIZATION, GENERALIZATION, REGISTRY`) in FAS §A2.5.1
    order, plus an `ordinal` property (0-based declaration index) so maturity is
    comparable and a stage can only advance, never regress. Every `.value` is a
    JSON-safe lowercase string. Kept in its own tiny module so both the coordinator and
    the benchmark import it without a cycle.
  - **`SkillEvolutionPipeline` coordinator** (`friday/learning/skill_pipeline.py` —
    NEW). `SkillRecord` dataclass (stage, `generalized`, `candidate_flag`, `emitted`
    dedup latch, JSON-safe `evidence` summary, `to_dict()`) + the pipeline itself:
    `attach(kernel)` subscribes to `learning.validated` + `reflection.skill` and
    observes `learning.rejected`; a bounded insertion-ordered per-`(capability,
    environment)` store (oldest evicted beyond `max_skills`, default 500);
    `learning.validated` → `generalized=True` and advance to ≥ `GENERALIZATION`;
    `reflection.skill` → `candidate_flag=True` + evidence summary (never fabricates
    generalization); `learning.rejected` → clears `generalized`; the dual-signal
    condition emits exactly ONE deduplicated `skill.candidate` and advances the skill
    to `REGISTRY`; `skill(...)` / `skills()` queries. Every handler is defensive and
    never raises into the event bus (A2.14.2).
  - **`attach_skill_pipeline(kernel, *, pipeline=None, **kwargs)`** — a reusable wiring
    helper mirroring `attach_reflection_layers` / `attach_reactive_loop`: constructs or
    reuses a pipeline, attaches it (isolating any attach exception so a wiring failure
    never crashes bootstrap), returns it; no-op holder semantics without a kernel;
    forwards only the kwargs the constructor accepts.
  - **Additive `learning.validated` / `learning.rejected` identity enrichment**
    (`friday/learning/engine.py`). The M9 `LearningEngine` now includes the
    experience's `capability` + `environment` on both event payloads (extra JSON-safe
    keys only; `""` when genuinely unavailable), so *real* learning events — not just
    synthetic ones — carry the identity the pipeline keys on. Existing consumers are
    unaffected.
  - **Activation of the `learning.validated` producer** (`friday/kernel/reactive_loop.py`).
    `attach_reactive_loop` previously attached Recovery / Competence / Reflection /
    FailureLog but **no** `LearningEngine`, so `learning.validated` had no production
    producer and the M9→M17 chain could not complete outside tests. The M9
    `LearningEngine` is now attached in `attach_reactive_loop` (guarded, additive,
    function-local import, isolates its own exceptions — mirrors the existing
    components) after the `ReflectionEngine` whose `reflection.completed` it consumes,
    so verified experience actually produces `learning.validated` in production.
  - **Guarded bootstrap wiring** (`friday/api/server.py`). Within the
    `FRIDAY_USE_KERNEL_EXECUTION=1` block, after the reactive loop and reflection layers
    are wired, `attach_skill_pipeline(kernel)` is called and exposed as
    `kernel.skill_pipeline`. Additive; the default (flag-off) path is byte-unchanged;
    wiring failure is logged with structured context and never crashes bootstrap.
  - **Hermetic skill-evolution benchmark** (`friday/benchmarks/skill_evolution.py` —
    NEW). `SkillEvent` / `SkillScenario` / `SkillMetrics` / `SkillEvolutionBenchmark`
    feed synthetic `learning.validated` / `reflection.skill` / `learning.rejected`
    streams through the pipeline on a *real* `CognitiveKernel` (in-memory event store)
    and score candidate-emission precision / recall / exact-match. Deterministic +
    hermetic (no LLM, network, or wall-clock); domain-general (Axiom 15); NOT part of
    the 5-domain scorecard and never written to the committed baseline.

## 1. Regression safety (automated)

- Full-suite checkpoint (established gate command, from repo root):
  `python -m pytest tests -q` → **1658 passed, 0 failed, 113 warnings in 375.76s
  (0:06:15)**. Total collected **1658** = baseline floor **1637** (post-M20) + the
  **21** new M17 tests (`tests/friday/test_m17_skill_evolution.py` 16 +
  `tests/friday/test_m17_skill_evolution_benchmark.py` 5), so the M17 tests are
  confirmed included and the zero-failure Requirement 5.3 / 6.3 checkpoint is
  satisfied.
- **Clean process table.** Before running, the process table was checked and no
  stale/background pytest suites were active (only MCP servers and the language
  server), so the load-sensitive M1 throughput benchmark ran on a clean machine with no
  shared-load contamination.
- **A8 kernel throughput benchmark green.** The M1 benchmark
  `tests/kernel/test_kernel.py::TestBenchmark::test_a8_100_ticks_per_second_sustained`
  passed both inside the full suite (0 failed) and in a targeted re-run
  (bundled with the M17 suite: **22 passed in 29.41s**), confirming the ≥100 ticks/sec
  architectural threshold with no timing flake.
- **M9 learning + M24 reactive-loop suites green after the enrichment + LearningEngine
  attach.** Targeted re-runs confirm no regression from Task 3.6 (event enrichment) or
  Task 4.1 (LearningEngine attached to the reactive loop): the M9 suite
  (`test_m9_engine / _integration / _isolation / _properties / _validator /
  _generalizer / _gate / _temporal / _horizon / _learning_models`) → **94 passed in
  31.21s**; the M24 / reactive-loop selection (`-k "m24 or reactive_loop or reactive"`)
  → **28 passed, 1630 deselected in 151.08s**.
- **No production default changed.** The pipeline is attached only in the guarded
  `FRIDAY_USE_KERNEL_EXECUTION=1` bootstrap; hermetic tests/benchmark perform no
  unbidden disk I/O (the benchmark uses an in-memory event store). Rollback = leave the
  flag off (byte-unchanged default path).

## 2. Architecture compliance

- **No duplicate learning / promotion / lifecycle system.** The pipeline is a pure
  CONSUMER of events that already flow on the bus — M9 `learning.validated` and M20
  `reflection.skill`. It re-implements no pattern discovery, generalization, promotion,
  or lifecycle; it tracks stage and offers a `skill.candidate` PROPOSAL to the existing
  M11 evidence-gated `PromotionPipeline`, which remains the sole decision-maker for
  actual promotion (sandbox → benchmark → lifecycle transition).
- **Proposes-never-promotes invariant (Req 4.1 / 4.2).**
  `friday/learning/skill_pipeline.py` imports no `friday.memory.*` /
  `friday.competence.*` / `friday.evolution.*`, references no `FridayMemory` /
  `MemoryStore`, and calls no lifecycle/promotion API. Its only side effect is
  emitting `skill.candidate` via `kernel.publish_event(make_event(...))` — no self
  promote, no memory write, no fabricated competence value (the payload carries only
  the observed evidence summary). This is asserted directly by the **Property 4
  isolation test** (`test_p4_module_does_not_import_memory_competence_evolution` scans
  the module source for forbidden `import` / `from` statements and class-name code
  references; `test_p4_only_emitted_event_type_is_skill_candidate` drives a full
  both-signals stream and asserts the only emitted type is `skill.candidate`).
- **Verified-only maturation (Req 4.3).** A `reflection.skill` alone never sets
  `generalized`, and a `learning.rejected` clears the `generalized` flag so a rejected
  skill can never become a candidate — cited by
  `test_p4_rejected_clears_generalized_blocks_candidate` (validated → rejected →
  reflection.skill emits nothing) and the benchmark's `validated-rejected-skill`
  scenario (expected candidates: none).
- **No application-specific logic (Axiom 15, Req 4.4).** A skill is keyed only by the
  generic `(capability, environment)` pair; no app / site / window-title identity
  appears anywhere. **Property 5** proves behavior is identical under arbitrary label
  text (`test_p5_generic_keying_dual_signal_one_candidate`) and that distinct
  environments are distinct skills (`test_p5_distinct_environments_are_distinct_skills`).
- **Bounded store + defensive handlers (A2.14.2).** The per-skill store is an
  insertion-ordered dict capped at `max_skills` (oldest evicted), proven bounded by
  `test_p2_store_never_exceeds_max_skills`. Every handler catches narrowly and degrades
  to a no-op, never raising into the bus — proven by
  `test_p2_malformed_events_never_raise_and_create_no_junk`. `BaseException`
  propagates.
- **Additive / kernel-guarded wiring (no default change).** `attach_skill_pipeline`
  adds a new helper and alters no existing method; the bootstrap attaches the pipeline
  only inside the guarded kernel-execution path and degrades safely on wiring failure
  (`test_p4_attach_without_kernel_is_noop`). The flag-off path is byte-unchanged.
- **Two dormant-chain activations make the capability genuinely live end-to-end.** The
  event enrichment (engine.py) and the `LearningEngine` attach (reactive_loop.py) are
  what close the production M9→M17 chain: previously `learning.validated` had no
  production producer and carried no `(capability, environment)`, so the pipeline could
  only be exercised by synthetic events. With both activations, verified experience
  flowing through the reactive loop's `ReflectionEngine` now yields real
  `learning.validated` events that carry the skill identity the pipeline keys on — the
  capability is live in production, not test-only. Both changes are additive, guarded,
  and confirmed regression-free (§1).

## 3. Requirements coverage

| Req | Requirement | How satisfied | Validating tests / properties |
|---|---|---|---|
| 1 | Skill stage taxonomy (exactly eight FAS §A2.5.1 members; ordered + JSON-projectable) | `SkillStage(str, Enum)` with 8 ordered members + `ordinal`; JSON-safe `.value` | **Property 1** (`test_p1_taxonomy_structure_static`, `test_p1_ordinal_matches_declaration_and_value_json`) |
| 2 | Track maturation from existing signals (attach to kernel; bounded per-(capability, environment) record; `learning.validated` → ≥ GENERALIZATION; handlers never raise) | `SkillEvolutionPipeline.attach` subscribes to the M9/M20 signals; bounded store; stage advance; defensive handlers | **Property 2** (`test_p2_validated_advances_to_generalization`, `test_p2_reflection_skill_sets_candidate_flag`, `test_p2_store_never_exceeds_max_skills`, `test_p2_malformed_events_never_raise_and_create_no_junk`) |
| 3 | Emit a promotion candidate when a skill matures (dual-signal → exactly one deduped `skill.candidate`; JSON-safe identity + evidence payload; per-skill query) | Dual-signal latch emits once + advances to REGISTRY; `skill()` / `skills()` queries | **Property 3** (`test_p3_dual_signal_validated_then_skill_emits_once`, `test_p3_dual_signal_skill_then_validated_emits_once`, `test_p3_single_signal_never_emits`), integration `test_integration_real_kernel_dual_signal_emits_one_candidate` |
| 4 | Reuse, not duplicate; evidence-only (no memory/competence/evolution import; only `skill.*` side effect; `learning.rejected` disqualifies; generic keying) | Module isolation; emit-only; rejection clears generalized; `(capability, environment)` keying | **Property 4** (`test_p4_module_does_not_import_memory_competence_evolution`, `test_p4_only_emitted_event_type_is_skill_candidate`, `test_p4_rejected_clears_generalized_blocks_candidate`), **Property 5** (`test_p5_generic_keying_dual_signal_one_candidate`, `test_p5_distinct_environments_are_distinct_skills`) |
| 5 | Replay-safe, additive, safe integration (JSON-serializable payloads; reusable wiring helper; inert without kernel; safe wiring failure; default byte-unchanged; suite green) | JSON-safe proposal dicts; `attach_skill_pipeline`; no-op without kernel; guarded `server.py` wiring | **Property 4** (`test_p4_attach_without_kernel_is_noop`), full-suite checkpoint (§1), guarded-bootstrap wiring |
| 6 | Verification artifacts (property/unit tests; hermetic non-baselined benchmark; FAS + matrix + review + checkpoint) | 21 tests + deterministic benchmark; FAS/matrix updated; this review | `test_m17_skill_evolution_benchmark.py` (5 tests); §4 below; §1 checkpoint |

## 4. Benchmark results (hermetic, not baselined)

`SkillEvolutionBenchmark` fed the 5 domain-general default scenarios through a fresh
pipeline attached to a real `CognitiveKernel` (in-memory event store):

| Metric | Value |
|---|---|
| total_scenarios | 5 |
| precision | **1.0** (every expected candidate emitted; no false positives) |
| recall | **1.0** (no expected candidate missed) |
| exact_match_rate | **1.0** (every scenario's emitted skill set == expected set) |
| total_emissions | **3** `skill.candidate` events |

- Scenario coverage: (a) a dual-signal skill → one candidate; (b1) single signal
  `learning.validated` only → none; (b2) single signal `reflection.skill` only → none;
  (c) validated → rejected → skill (the rejection disqualifies it) → none; (d) two
  independent dual-signal skills → two candidates. Total = 1 + 0 + 0 + 0 + 2 = **3**
  emissions, matching the sum of expected candidates.
- **Deterministic + hermetic:** no LLM, no network, no wall-clock; identical runs yield
  identical metrics (`test_run_is_deterministic`), and an empty scenario set yields zero
  rates without crashing (`test_empty_scenarios_zero_metrics`). The metrics payload is
  JSON-safe and renders markdown (`test_metrics_payload_is_json_safe`).
- **Policy:** domain-general (Axiom 15), **NOT** part of the 5-domain competence
  scorecard, and **never** recorded into the committed competence baseline (mirrors the
  M19 / M20 / M24 policy).

## 5. Verification

- **Full-suite checkpoint:** `python -m pytest tests -q` → **1658 passed, 0 failed,
  113 warnings in 375.76s (0:06:15)**. The run started on a clean process table (no
  stale pytest suites), so it represents one clean repo-root checkpoint.
- **M17 property tests (Properties 1–5) + benchmark tests green:** all 16 tests in
  `tests/friday/test_m17_skill_evolution.py` (taxonomy totality/ordering, maturation
  tracking, dual-signal single-emission + dedup, reuse/evidence isolation,
  verified-only disqualification, generic keying, real-kernel integration) and all 5
  tests in `tests/friday/test_m17_skill_evolution_benchmark.py` are included in the
  1658-test green checkpoint, and passed in a targeted re-run bundled with A8
  (**22 passed in 29.41s**).
- **M9 / M24 suites green after the enrichment + LearningEngine attach:** M9 learning
  suite → **94 passed in 31.21s**; M24 / reactive-loop selection → **28 passed, 1630
  deselected in 151.08s**. Task 3.6 (event enrichment) and Task 4.1 (LearningEngine on
  the reactive loop) introduced no regression.
- **A8 throughput green:** the ≥100 ticks/sec architectural threshold holds in both the
  full suite and the targeted re-run; no timing flake observed.
- **Diagnostics:** this review file was checked after writing; no diagnostics reported.

## 6. Traceability

- **A2.5 Skill evolution pipeline: Partial → Built.**
  - `docs/architecture/FAS_v2.1_AMENDMENTS.md` — A2.5 marked **Built** with a code-state
    line pointing at `friday/learning/skill_pipeline.py` (`SkillEvolutionPipeline` +
    `attach_skill_pipeline`) and `friday/learning/skill_stage.py`, documenting the
    normative §A2.5.1 ladder, the pure-coordinator / dual-signal-proposal /
    proposes-never-promotes / verified-only / bounded-and-safe sub-sections.
  - `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` — A2.5 row flipped
    **Partial → Built** (M17), with the summary line noting A2.5 is now Built.
- Consumes M9 `learning.validated` and M20 `reflection.skill`; offers `skill.candidate`
  to the M11 `PromotionPipeline`. No duplicate learning / promotion / lifecycle system;
  no direct memory writes; no self-promotion; verified-only; no application-specific
  logic (Axiom 15).
- FAS reference: Ch 15 / 27; v2.1 amendment A2.5.

## 7. Decision

- **PROCEED — zero-failure gate satisfied.** A previously-*Partial* architectural
  capability (A2.5 Skill evolution pipeline) is now built and verified as one general
  coordinator layered additively over the existing M9 learning + M20 reflection +
  M11 evolution mechanisms: the eight-stage taxonomy, a dual-signal latch that PROPOSES
  (emits one deduplicated `skill.candidate`) and never DECIDES (no self-promote, no
  memory write, no fabricated competence). No duplicate system, bounded store with
  defensive handlers (A2.14.2), generic `(capability, environment)` keying (Axiom 15),
  and additive kernel-guarded wiring with no default change. All **1658 tests pass**;
  the hermetic M17 benchmark scores 1.0 across precision / recall / exact-match with 3
  candidate emissions over 5 domain-general scenarios.
- The two dormant-chain activations (event identity enrichment + attaching the
  `LearningEngine` to the reactive loop) close the production M9→M17 chain, making the
  capability genuinely live end-to-end rather than test-only, with the M9 and M24
  suites confirmed regression-free.
- The M1 A8 kernel throughput benchmark remains green (≥100 ticks/sec) in both the full
  suite and a targeted re-run, with no shared-load contamination.
- **Working tree left uncommitted for user review.** No commit was made; changes remain
  in the working tree for inspection.
- Recommended next: have the M11 `PromotionPipeline` (and observability) consume the
  `skill.candidate` proposals so a matured skill flows automatically into the
  evidence-gated candidate flow, closing the §A2.5 → §A2.4 handoff.

Reviewer / date: FRIDAY orchestrator, M17 close-out.
