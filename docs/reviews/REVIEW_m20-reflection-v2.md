# After-Milestone Review — M20 Reflection v2 (Layered Reflection)

> Governance gate. Delivers **A2.10 Layered reflection (5 layers)** (previously
> *Partial* in the v2.1 traceability matrix) additively over the existing
> `ReflectionEngine`. Formalizes the five-layer `ReflectionLayer` taxonomy and adds
> the three higher **consumer** layers (Long-Term / Skill / Architectural) that
> aggregate the existing `reflection.completed` stream and emit JSON-safe
> `reflection.*` proposal events — never memory writes. No duplicate reflection
> system; the "Reflection proposes, Memory decides" invariant (Ch 13.16 / 14.8) is
> preserved across all five layers.

## 0. Milestone under review

- Milestone: `M20 — Reflection v2 (Layered Reflection)`
- Target capability: **five-layer reflection hierarchy** (FAS §A2.10.1) —
  `Immediate` (per action) → `Session` (per goal/session) → `Long-Term` (across
  sessions) → `Skill` (per capability, feeds the §A2.5 skill pipeline) →
  `Architectural` (evaluates whether the architecture still serves the user and
  proposes structural change).
- Summary of what M20 delivered:
  - **Five-layer `ReflectionLayer` taxonomy** (`friday/cognition/reflection.py` —
    additive). A `str` enum with exactly five ordered members
    (`IMMEDIATE`, `SESSION`, `LONG_TERM`, `SKILL`, `ARCHITECTURAL`) plus an `ordinal`
    helper so scope is comparable; every `.value` is JSON-safe. The pre-existing
    `ReflectionScale` (micro/task/goal/session) is retained byte-unchanged; the new
    taxonomy is layered on top with the micro→`IMMEDIATE` / task,goal,session→`SESSION`
    mapping documented and no engine-output change.
  - **Three higher consumer layers** (`friday/cognition/reflection_layers.py` — NEW):
    - `LongTermReflector` — subscribes to `reflection.completed`; keeps a bounded
      per-`(capability, environment)` window of `(prediction_error, calibration)`
      samples; emits a `reflection.longterm` trend proposal when a key has
      ≥ `min_samples` and mean prediction error ≥ `error_threshold`; exposes
      `trend(capability, environment)`.
    - `SkillReflector` — per-capability aggregation (sample count, mean error,
      verified-rate); emits a `reflection.skill` candidate proposal when a capability
      reaches ≥ `min_samples` with `verified_rate ≥ v_thresh` and
      `mean_error ≤ e_thresh`; exposes `summaries()`. Proposal only — promotion stays
      the pipeline's/Memory's decision.
    - `ArchitecturalReflector` — cross-capability meta-signal (count of distinct
      "hot" capabilities whose running mean error is high); emits a single
      **deduplicated** advisory `reflection.architectural` proposal on crossing the
      meta-threshold and latches so it does not spam the bus. Advisory only; mutates
      nothing.
  - **`attach_reflection_layers(kernel, *, longterm=None, skill=None,
    architectural=None, **thresholds)`** — one reusable wiring helper (function-local
    imports, no cycles) mirroring the M24 `attach_reactive_loop` pattern. Reuses
    injected layers or constructs fresh ones (forwarding only kwargs each layer
    accepts), no-op without a kernel, isolates each layer's `attach` exception, and
    returns a small inspectable `ReflectionLayers` holder.
  - **Guarded bootstrap wiring** (`friday/api/server.py`) — within the
    `FRIDAY_USE_KERNEL_EXECUTION=1` block (where `attach_reactive_loop` and the M19
    retrieval router are already wired), `attach_reflection_layers(kernel)` is called
    and exposed as `kernel.reflection_layers`. Additive; the default (flag-off) path
    is byte-unchanged; wiring failure is logged with structured context and never
    crashes bootstrap.
  - **Hermetic reflection benchmark** (`friday/benchmarks/reflection.py` — NEW) —
    `ReflectionScenario` / `ReflectionSample` / `ReflectionMetrics` /
    `ReflectionBenchmark` feed synthetic `reflection.completed` streams through the
    layers on a *real* `CognitiveKernel` (wired with an in-memory event store) and
    score expected-proposal precision / recall / exact-match plus per-type emission
    counts. Deterministic + hermetic (no LLM, network, or wall-clock); domain-general
    (Axiom 15); NOT part of the 5-domain scorecard and never written to the committed
    baseline.

## 1. Regression safety (automated)

- Full-suite checkpoint (established gate command, from repo root):
  `python -m pytest tests -q` → **1637 passed, 0 failed, 113 warnings in 185.81s
  (0:03:05)**. Total collected **1637** = baseline floor **1614** (post-M19, after
  the A8 throughput-benchmark fix) + the **23** new M20 tests
  (`tests/friday/test_m20_reflection_layers.py` 18 + `test_m20_reflection_benchmark.py`
  5), so the M20 tests are confirmed included and the zero-failure Requirement
  7.3 / 8.3 checkpoint is satisfied.
- **A8 kernel throughput benchmark green.** The M1 kernel benchmark
  `tests/kernel/test_kernel.py::TestBenchmark::test_a8_100_ticks_per_second_sustained`
  passed both inside the full suite (0 failed) and in a targeted re-run
  (**1 passed in 6.20s**), confirming the ≥100 ticks/sec architectural threshold with
  no timing flake. Before running, the process table was checked and no stale/background
  pytest suites were active, so the load-sensitive timing test ran on a clean machine
  (no shared-load contamination).
- **All M20 tests green:** `tests/friday/test_m20_reflection_layers.py` (Properties
  1–6 + `ReflectionScale`-unchanged guard) and `tests/friday/test_m20_reflection_benchmark.py`
  (5 benchmark tests) are included in the 1637-test green checkpoint.
- **No production default changed.** The layers are attached only in the guarded
  `FRIDAY_USE_KERNEL_EXECUTION=1` bootstrap; hermetic tests/benchmark perform no
  unbidden disk I/O (the benchmark uses an in-memory event store, so no `session.jsonl`
  is written). Rollback = leave the flag off (byte-unchanged default path).

## 2. Architecture compliance

- **No duplicate reflection system.** The higher layers are pure consumers of the
  existing `ReflectionEngine`'s `reflection.completed` stream. They introduce no
  second reflection engine, no new `ReflectionRecord`, and no new persistence — only
  in-memory bounded aggregates over events the engine already emits.
- **Proposes-not-decides invariant preserved across all five layers (Ch 13.16 / 14.8;
  Requirement 5).** `friday/cognition/reflection_layers.py` imports no
  `friday.memory.*` / `friday.competence.*` / `friday.recovery.*` and references
  neither `FridayMemory` nor `MemoryStore`; its only side effect is
  `kernel.publish_event(make_event(...))` of `reflection.longterm` /
  `reflection.skill` / `reflection.architectural` proposals (and the allowed
  `memory.candidate`). This is asserted directly by the **Property 5 isolation test**
  (`test_p5_module_does_not_import_memory_competence_recovery` scans the module source
  for forbidden `import`/`from` statements and class-name references;
  `test_p5_layers_emit_only_reflection_or_memory_candidate` drives all three layers and
  asserts every reflection-sourced event is in the allowed set).
- **Existing engine outputs byte-unchanged (Requirement 5.3).** **Property 6**
  (`test_p6_existing_engine_outputs_unchanged_with_layers`, 100 examples) runs a
  control kernel with only the `ReflectionEngine` against a treatment kernel with the
  engine **plus** the three higher layers on identical verification input, and asserts
  `memory.candidate` and `reflection.completed` payloads are identical
  (`trt_candidates == ctl_candidates`, `trt_completeds == ctl_completeds`).
  `test_reflection_scale_unchanged` further pins the pre-existing four-scale enum.
- **Bounded aggregates + defensive handlers (A2.14.2).** Every layer keeps a bounded
  `deque(maxlen=window)` per aggregation key (oldest samples evicted), proven bounded
  by `test_p2_window_strictly_bounded` / `test_p3_skill_window_bounded`. Every handler
  catches narrowly and degrades to a no-op, never raising into the bus — proven by
  `test_p5_malformed_events_never_raise` (120 examples over `None`/empty/non-numeric
  payloads). `BaseException` is not swallowed.
- **Additive / kernel-guarded wiring (no default change).** `attach_reflection_layers`
  adds a new helper and alters no existing method; the bootstrap attaches the layers
  only inside the guarded kernel-execution path and degrades safely on wiring failure
  (`test_p5_bus_helper_isolates_layer_attach_failures`,
  `test_p5_attach_without_kernel_is_noop`). The flag-off path is unchanged.
- **No application-specific logic (Axiom 15).** No app/site/window-title identity
  anywhere; layers key on generic `capability` / `environment` strings and the
  benchmark scenarios use only domain-general capabilities (research, coding,
  navigation) and environment classes (web, desktop).

## 3. Requirements coverage

| Req | Requirement | How satisfied | Validating tests / properties |
|---|---|---|---|
| 1 | Five-layer taxonomy (exactly five members; Immediate/Session map to the existing engine without output change; ordered + JSON-projectable) | `ReflectionLayer(str, Enum)` with 5 ordered members + `ordinal`; mapping documented; `ReflectionScale` retained | **Property 1** (`test_p1_taxonomy_structure_static`, `test_p1_ordinal_matches_declaration_and_value_json`), `test_reflection_scale_unchanged` |
| 2 | Long-Term layer (bounded per-(capability, environment) aggregate; `reflection.longterm` proposal on adverse trend ≥ N samples; bounded; handlers never raise) | `LongTermReflector`: bounded deque window, mean-error threshold over `min_samples`, `trend()` query, defensive handler | **Property 2** (`test_p2_longterm_crossing_threshold_emits`, `test_p2_longterm_below_threshold_emits_none`, `test_p2_window_strictly_bounded`), `test_p5_malformed_events_never_raise` |
| 3 | Skill layer (per-capability count/mean-error/verified-rate; `reflection.skill` candidate on verified low-error; `summaries()` query; bounded; never raise) | `SkillReflector`: per-capability window, verified-rate + error thresholds, `candidate: True` proposal, `summaries()` | **Property 3** (`test_p3_skill_verified_low_error_emits_candidate`, `test_p3_skill_unverified_emits_none`, `test_p3_skill_window_bounded`) |
| 4 | Architectural layer (cross-capability meta-signal; single deduped advisory `reflection.architectural`; mutates nothing; bounded; never raise) | `ArchitecturalReflector`: hot-capability count vs `min_capabilities`, latched single advisory, emits events only | **Property 4** (`test_p4_architectural_single_advisory_deduped`, `test_p4_architectural_below_threshold_no_emit`) |
| 5 | Reflection proposes, memory decides (no memory/competence/recovery import; only `memory.candidate`/`reflection.*`; existing engine outputs unchanged) | Module isolation; emit-only side effects; additive layers | **Property 5** (`test_p5_module_does_not_import_memory_competence_recovery`, `test_p5_layers_emit_only_reflection_or_memory_candidate`), **Property 6** (`test_p6_existing_engine_outputs_unchanged_with_layers`, `test_p6_engine_still_emits_reflection_completed_with_layers`) |
| 6 | Replay-safe, event-driven integration (JSON-serializable payloads; single reusable wiring helper; inert without kernel; safe wiring failure) | JSON-safe proposal dicts; `attach_reflection_layers`; no-op without kernel; per-layer exception isolation | **Property 5** (`test_p5_attach_without_kernel_is_noop`, `test_p5_bus_helper_isolates_layer_attach_failures`), JSON asserts in P2/P3/P4 |
| 7 | Additive, safe integration (attach only in guarded path; default byte-unchanged; suite green) | Guarded `server.py` wiring exposing `kernel.reflection_layers`; no default change | Full-suite checkpoint (§1); guarded-bootstrap wiring |
| 8 | Verification artifacts (property/unit tests; hermetic non-baselined benchmark; FAS+matrix+review+checkpoint) | 23 tests + deterministic benchmark; FAS/matrix updated; this review | `test_m20_reflection_benchmark.py` (5 tests); §4 below; §1 checkpoint |

## 4. Benchmark results (hermetic, not baselined)

`ReflectionBenchmark` fed the 4 domain-general default scenarios through fresh
Long-Term / Skill / Architectural layers attached to a real `CognitiveKernel` (in-memory
event store):

| Metric | Value |
|---|---|
| total_scenarios | 4 |
| precision | **1.0** (every expected proposal emitted; no false positives) |
| recall | **1.0** (no expected proposal missed) |
| exact_match_rate | **1.0** (4/4 scenarios' emitted type set == expected set) |
| `reflection.longterm` emissions | **1** |
| `reflection.skill` emissions | **1** |
| `reflection.architectural` emissions | **1** |

- Scenario coverage: (1) a below-threshold mid-band stream that stays silent
  (no false positives, counts as an exact match against the empty expected set);
  (2) a single high-error capability → one long-term adverse-trend proposal;
  (3) a verified low-error capability → one skill-pipeline candidate proposal;
  (4) several moderately-hot capabilities → one cross-capability architectural
  advisory (and no per-capability long-term/skill proposals). The benchmark
  thresholds deliberately place the long-term error band above the architectural
  band so the meta-signal trips without also tripping a per-capability trend.
- **Deterministic + hermetic:** no LLM, no network, no wall-clock; identical runs yield
  identical metrics (`test_run_is_deterministic`), and an empty scenario set yields zero
  rates without crashing (`test_empty_scenarios_zero_metrics`).
- **Policy:** domain-general (Axiom 15), **NOT** part of the 5-domain competence
  scorecard, and **never** recorded into the committed competence baseline (mirrors the
  M19 / M23 / M24 policy).

## 5. Verification

- **Full-suite checkpoint:** `python -m pytest tests -q` → **1637 passed, 0 failed,
  113 warnings in 185.81s (0:03:05)**. The run started on a clean process table (no
  stale pytest suites), so it represents one clean repo-root checkpoint.
- **A8 targeted verification:**
  `python -m pytest tests/kernel/test_kernel.py::TestBenchmark::test_a8_100_ticks_per_second_sustained -q`
  → **1 passed in 6.20s**. The ≥100 ticks/sec architectural threshold holds; no timing
  flake observed in the full suite or the targeted run.
- **M20 property tests (Properties 1–6)** and **M20 benchmark tests (5)** are all green
  as part of the full checkpoint. Taxonomy totality/ordering, long-term/skill/architectural
  aggregation + threshold proposals, bounded windows, malformed-event resilience,
  no-op-without-kernel, per-layer attach isolation, and byte-unchanged engine outputs are
  all included.
- **Diagnostics:** this review file was checked after writing; no diagnostics reported.

## 6. Traceability

- **A2.10 Layered reflection (5 layers): Partial → Built.**
  - `docs/architecture/FAS_v2.1_AMENDMENTS.md` — A2.10 marked **Built** with a
    code-state line pointing at `friday/cognition/reflection_layers.py` (the three
    higher layers + `attach_reflection_layers`), the `ReflectionLayer` taxonomy in
    `friday/cognition/reflection.py`, the guarded `server.py` wiring, and the hermetic
    `friday/benchmarks/reflection.py`.
  - `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` — A2.10 row flipped
    **Partial → Built** (M20).
- Consumes the existing `reflection.completed` stream (no duplicate reflection
  system); feeds the §A2.5 skill pipeline via a `reflection.skill` candidate proposal.
  No direct memory writes; no application-specific logic (Axiom 15).
- FAS reference: Ch 13; v2.1 amendment A2.10.

## 7. Decision

- **PROCEED — zero-failure gate satisfied.** A previously-*Partial* architectural
  capability (A2.10 Layered reflection) is now built and verified as one general
  mechanism layered additively over the existing engine: the five-layer taxonomy plus
  three higher consumer layers that PROPOSE (emit `reflection.*` events) and never
  DECIDE (no memory writes, no subsystem mutation). No duplicate reflection system,
  bounded aggregates with defensive handlers (A2.14.2), byte-unchanged existing engine
  outputs, and additive kernel-guarded wiring with no default change. All **1637 tests
  pass**; the hermetic M20 benchmark scores 1.0 across precision / recall /
  exact-match over 4 domain-general scenarios.
- The M1 A8 kernel throughput benchmark remains green (≥100 ticks/sec) in both the full
  suite and a targeted re-run, with no shared-load contamination.
- **Working tree left uncommitted for user review.** No commit was made; changes remain
  in the working tree for inspection.
- Recommended next: (a) enrich the `reflection.completed` payload with explicit
  `capability` / `environment` / `verified` fields (the layers already read them
  defensively) so the higher layers aggregate on first-class signals rather than
  fallbacks; (b) have the skill-evolution pipeline (§A2.5) and observability consume the
  `reflection.skill` / `reflection.architectural` proposals.

Reviewer / date: FRIDAY orchestrator, M20 close-out.
