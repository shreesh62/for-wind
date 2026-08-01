# After-Milestone Review — M19 Retrieval Router

> Governance gate. Delivers **A2.7 Retrieval Router** (previously *Absent* in the v2.1
> traceability matrix) as one general mechanism over the existing uniform retrieval
> surface — no duplicate memory system, tier selection is data (not code branches),
> and the FAILURE tier (M21) participates as a first-class source. Advances "Can it
> retrieve the right knowledge from the right place?" without a vector-first default.

## 0. Milestone under review

- Milestone: `M19 — Retrieval Router`
- Target capability: **unified retrieval / routing** — selecting the correct information
  source(s) per request *before* any search runs, then merging, ranking, de-duplicating,
  and returning a single provenance-carrying result set (FAS §A2.7.1).
- Summary of what M19 delivered:
  - **Retrieval Router over the uniform `retrieve(query, top_k)` surface**
    (`friday/memory/retrieval_router.py` — `RetrievalRouter`, `RetrievedItem`). Any object
    exposing `retrieve(query, top_k) -> List[MemoryEntry]` (every `MemoryStore`, and
    `FailureMemory`) registers under a unique name + owning `MemoryTier` + optional weight.
    The router fans out to registered sources, scores each source's results by best-first
    **rank** scaled by weight (backend-agnostic), merges, sorts descending, de-duplicates,
    and caps at `top_k`.
  - **Controller factory** (`friday/memory/controller.py::build_retrieval_router`) — a thin,
    additive helper that registers the backing `MemoryStore` (`._store`) of the
    episodic/semantic/procedural tiers and, when supplied, a `FailureMemory` under
    `MemoryTier.FAILURE`. It changes no existing `FridayMemory` method behavior.
  - **FAILURE-tier participation** — `FailureMemory.retrieve` (added in M21) satisfies the
    same source contract, so prior failures surface interleaved with other tiers by score,
    or alone under a `{FAILURE}` filter.
  - **Guarded bootstrap wiring** (`friday/api/server.py`) — the router is constructed via the
    factory only inside the `FRIDAY_USE_KERNEL_EXECUTION=1` block and exposed for planning;
    the default (flag-off) path is byte-unchanged and wiring failure degrades safely.
  - **Hermetic benchmark** (`friday/benchmarks/retrieval.py`) — a deterministic, in-memory
    routing-quality harness (coverage / correct-tier-rate / dedup-rate / mean-rank) over
    synthetic multi-tier sources; no LLM, network, or wall-clock; not part of the 5-domain
    scorecard and never written to the committed baseline.

## 1. Regression safety (automated)

- Full-suite checkpoint (established gate command, from repo root):
  `python -m pytest tests -q` → **1614 passed, 0 failed, 113 warnings in 137.59s
  (0:02:17)**. Total collected **1614** = baseline floor **1593** + the **21** new
  M19 tests (15 router + 6 benchmark), so the M19 tests are confirmed included and the
  zero-failure Requirement 7.3/8.3 checkpoint is satisfied.
- **A8 benchmark reliability defect fixed.** Investigation found no kernel tick-performance
  defect: `CognitiveKernel._tick` advances the logical clock and dispatches each registered
  runtime directly, while `CognitiveScheduler.stop` signals and joins its worker; every
  test that starts a kernel scheduler shuts it down. The old benchmark methodology started
  the scheduler on a daemon thread, slept on the test thread for five seconds, and divided
  daemon-thread progress by elapsed wall time. That conflated kernel tick execution capacity
  with how much CPU the OS granted a background thread under unrelated load. Two stale
  full-suite pytest processes from the prior run were also still active, providing concrete
  shared-load contamination; they were terminated before the clean checkpoint.
- The benchmark now drives the **same real `CognitiveKernel._tick` callback used by
  `CognitiveScheduler` synchronously for a five-second `time.perf_counter` window**, with a
  real `EchoRuntime` registered. This isolates unrelated daemon-thread scheduling while
  retaining the complete measured tick path (logical-clock advance + runtime dispatch +
  `EchoRuntime.tick`) and the unchanged **≥100 ticks/sec** assertion. It does not mock time,
  reduce the threshold, skip/xfail the test, or manipulate the measured count. Five
  consecutive targeted runs passed: **1 passed in 5.97s, 5.73s, 5.70s, 5.66s, and 5.63s**.
- **All M19 tests green:** `tests/friday/test_m19_retrieval_router.py` +
  `tests/friday/test_m19_retrieval_benchmark.py` are included in the 1614-test green
  checkpoint, covering Properties 1–6 and the deterministic retrieval benchmark.
- **No production default changed.** The router is constructed only in the guarded
  `FRIDAY_USE_KERNEL_EXECUTION=1` bootstrap; hermetic tests/benchmark perform no unbidden
  disk I/O. Rollback = leave the flag off (byte-unchanged default path).

## 2. Architecture compliance

- **No duplicate memory system.** The router reuses `MemoryEntry` / `MemoryTier` and the
  existing uniform `retrieve(query, top_k)` surface implemented by every `MemoryStore` and by
  the M21 `FailureMemory`. It introduces no new persistence, no second taxonomy, and touches
  no tier internals — it is a routing/merge layer over what already exists.
- **Tier selection is data, not code branches (Axiom 15).** Sources are registered under a
  name + owning `MemoryTier` + weight; routing is `tiers=None` (all) or an explicit tier
  filter (set membership). There is no per-tier `if/else` anywhere in `route`. The factory's
  only tier knowledge is a generic `(name, tier, attribute)` mapping table; any source
  missing the uniform surface is skipped by the same registration validation — no per-tier
  special-casing. Scoring is rank-based (best-first position × weight), independent of any
  backend's internal score scheme, so heterogeneous sources merge fairly.
- **No application-specific logic.** No app/site/window-title identity anywhere; the benchmark
  scenarios are domain-general (generic topics: photosynthesis, prime numbers, bread recipe,
  meeting notes, permission-denied/upload failures). Vector search is one strategy, never the
  universal default (FAS §A2.7.1/§A2.7.4).
- **Structured-error-model compliance (A2.14.2 / Requirement 5.3).** The only broad catch is
  the per-source **degradation boundary** in `route`: a source that raises is skipped so it
  cannot break retrieval for the rest. It is **not a silent swallow** — the exception `repr`
  is recorded in an observable `last_errors` map (reset per `route` call) and logged at
  WARNING with structured context (source name, tier, `exc_info`). `BaseException`
  (KeyboardInterrupt/SystemExit) intentionally propagates. Registration fails fast with
  `TypeError` on a source lacking `retrieve`.
- **Additive / kernel-guarded wiring (no default change).** The factory adds a new function
  and alters no existing `FridayMemory` method; the bootstrap builds the router only inside
  the guarded kernel-execution path and degrades safely on wiring failure. The flag-off path
  is unchanged.

## 3. Requirements coverage

| Req | Requirement | How satisfied | Validating tests / properties |
|---|---|---|---|
| 1 | Uniform source registration (name+tier+weight; fail-fast on missing `retrieve`; unregister/count/tiers; name replacement) | `register_source` validates `retrieve` (→ `TypeError`), clamps weight ≥ 0, replaces by name; `unregister`, `source_count`, `tiers()` | `test_register_rejects_invalid_source`, `test_register_replaces_name_and_reports_count_and_tiers`, `test_unregister_returns_bool_and_decrements`, `test_weight_clamped_non_negative` |
| 2 | Cross-source routing (all vs tier-filtered; empty→`[]`; `per_source_k`/`top_k` bounds) | `route(tiers=None)` queries all; filter → set membership; empty/degenerate → `[]`; sizes clamped ≥ 0 | **Property 1** (`test_p1_routing_and_tier_filter`), **Property 5** (`test_p5_no_sources_returns_empty`, `test_p5_tier_filter_matching_none_returns_empty`, `test_p5_top_k_and_per_source_k_bounds`) |
| 3 | Merge, rank, cap (rank×weight; sort desc; cap `top_k`; higher weight ranks ≥) | `rank_score = 1 - i/n`, ×weight; `sort(reverse=True)`; slice `[:top_k]` | **Property 2** (`test_p2_weighted_rank_ordering`) |
| 4 | Provenance + de-dup + JSON (`source`/`tier`/score/entry_id/timestamp/metadata; de-dup by entry_id else (tier,content); `to_dict` JSON round-trip) | `RetrievedItem` carries full provenance; `_dedupe` keeps highest-scored; `to_dict()` JSON-safe | **Property 3** (`test_p3_provenance_dedup_and_json`), `test_retrieved_item_to_dict_json_roundtrip` |
| 5 | Failing-source isolation (skip raising source; healthy results still returned; never a silent `except: pass`) | per-source degradation boundary → skip + record `last_errors` + WARN log; `route` never raises | **Property 4** (`test_p4_failing_source_isolated`, `test_p4_all_sources_failing_returns_empty_without_raising`) |
| 6 | Failure-memory participation (register `FailureMemory` under FAILURE; unfiltered interleaves by score; `{FAILURE}` filter returns only failures) | real `FailureMemory.retrieve` registered under `MemoryTier.FAILURE` | **Property 6** (`test_p6_failure_memory_participation`) |
| 7 | Integration (factory over persistent tiers; guarded bootstrap; suite green) | `build_retrieval_router` factory; guarded `server.py` wiring; no default change | `test_factory_registers_tiers_and_route_has_provenance`; full-suite checkpoint (§1) |
| 8 | Verification artifacts (property/unit tests; hermetic non-baselined benchmark; FAS+matrix+review+checkpoint) | 21 tests + deterministic benchmark; FAS/matrix updated; this review | `test_m19_retrieval_benchmark.py` (6 tests); §4 below; §1 checkpoint |

## 4. Benchmark results (hermetic, not baselined)

`RetrievalBenchmark` routed the 6 domain-general default scenarios through a real
`RetrievalRouter` with in-memory synthetic multi-tier sources:

| Metric | Value |
|---|---|
| total_scenarios | 6 |
| coverage | **1.0** (6/6 planted relevant items retrieved) |
| correct_tier_rate | **1.0** (6/6 attributed to their planted tier) |
| dedup_rate | **1.0** (6/6 outputs free of duplicate keys) |
| mean_rank | **1.0** (relevant item ranked #1 in every scenario; ranks `[1,1,1,1,1,1]`) |
| relevant-item tiers | semantic ×2, failure ×2, procedural ×1, episodic ×1 |

- **Deterministic + hermetic:** no LLM, no network, no wall-clock; identical runs yield
  identical metrics (verified by `test_run_is_deterministic`). Scenarios deliberately plant a
  duplicate `entry_id` across two sources to exercise de-duplication, and one FAILURE-only
  tier-filter scenario to exercise the filter path.
- **Policy:** domain-general (Axiom 15), **NOT** part of the 5-domain competence scorecard,
  and **never** recorded into the committed competence baseline (mirrors the M23/M24 policy).

## 5. Verification

- **Repeated A8 targeted verification:**
  `python -m pytest tests/kernel/test_kernel.py::TestBenchmark::test_a8_100_ticks_per_second_sustained -q`
  passed **5 consecutive runs**: **1 passed in 5.97s, 5.73s, 5.70s, 5.66s, and 5.63s**.
- **Full-suite checkpoint:** `python -m pytest tests -q` → **1614 passed, 0 failed,
  113 warnings in 137.59s (0:02:17)**. The run started after terminating two stale prior
  pytest suite processes, so it represents one clean repo-root checkpoint rather than
  multiple competing suites.
- **M19 property tests (Properties 1–6)** and **M19 benchmark tests (6)** are all green as
  part of the full checkpoint. Registration fail-fast, weight clamping, `to_dict` JSON
  round-trip, factory-over-real-`FridayMemory`, and empty/degenerate routing are included.
- **Diagnostics:** `tests/kernel/test_kernel.py` and this review were checked after the
  final edits; no file diagnostics were reported.

## 6. Traceability

- **A2.7 Retrieval Router: Absent → Built.**
  - `docs/architecture/FAS_v2.1_AMENDMENTS.md` — A2.7 code-state updated to **built**,
    pointing at `friday/memory/retrieval_router.py`, the controller factory, the FAILURE-tier
    surface, and the guarded `server.py` wiring; normative clauses §A2.7.1–§A2.7.7 recorded.
  - `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` — A2.7 row flipped **Absent → Built**
    (M19), and the summary note updated to reflect the router is now built.
- Consumes the M21 failure tier (`FailureMemory.retrieve`) and the existing `MemoryStore`
  uniform surface — no duplicate memory system, no application-specific logic.
- FAS reference: Ch 14.13; v2.1 amendment A2.7.

## 7. Decision

- **PROCEED — zero-failure gate satisfied.** A previously-absent architectural capability
  (A2.7 Retrieval Router) is built and verified as one general mechanism over the uniform
  retrieval surface: no duplicate system, data-driven tier selection (Axiom 15), observable
  per-source degradation (A2.14.2), first-class FAILURE-tier participation, and additive
  kernel-guarded wiring with no default change. All **1614 tests pass**; the hermetic M19
  benchmark scores 1.0 across coverage / correct-tier-rate / dedup-rate / mean-rank.
- The M1 A8 benchmark now measures five seconds of real, steady-state kernel tick execution
  without folding unrelated daemon-thread scheduling into the result. Its ≥100 ticks/sec
  architectural threshold is unchanged, and it passed five consecutive targeted runs plus
  the full-suite checkpoint.
- **Working tree left uncommitted for user review.** No commit was made; changes remain in
  the working tree for inspection.
- Recommended next: (a) have the planner/deliberator consult the router (including the FAILURE
  tier) during planning; (b) extend registration to the World Model / Capability Registry /
  connectors as they expose the uniform surface.

Reviewer / date: FRIDAY orchestrator, M19 close-out.
