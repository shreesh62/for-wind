# After-Milestone Review — M21 (slice 2) Seven-Tier Memory Completion

> Governance gate. Completes **A2.11 seven-tier memory** (previously *Partial* in the
> v2.1 traceability matrix) **additively** by adding the two remaining FAS §A2.11.1
> tiers — **Capability** and **Preference** — over the proven M21 `FailureMemory`
> template. Each is a bounded `JSONFileStore`-backed, kernel-driven, defensive memory
> tier that consumes events already on the bus (or its direct API), exposes the uniform
> `retrieve(query, top_k)` surface so it plugs into the M19 Retrieval Router, and is
> attached only within the guarded kernel-execution path. No new persistence mechanism,
> no duplicate memory framework, no application-specific logic. Critically, the
> **Capability tier is a memory VIEW, not an authority**: the evidence-only
> `CompetenceModel` (Ch 28) remains the sole competence authority — the tier records
> only what `competence.updated` reported and never recomputes or overrides it. All new
> code is additive and inert without a kernel. **With the seven tiers complete, this
> closes the Architecture v2.1 build-out entirely — nothing remains Partial or Absent.**

## 0. Milestone under review

- Milestone: `M21 (slice 2) — Seven-Tier Memory Completion (Capability + Preference tiers)`
- Target capability: the full FAS §A2.11.1 seven-tier memory model —
  `Working, Episodic, Semantic, Procedural, Capability, Failure, Preference` — with the
  two previously-unformalized tiers (Capability + Preference) now first-class, persistent,
  queryable memory on the live path, participating in the M19 Retrieval Router through the
  uniform `retrieve` surface.
- Summary of what this slice delivered:
  - **Tier identifiers** (`friday/memory/interfaces.py`). Added
    `MemoryTier.CAPABILITY = "capability"` and `MemoryTier.PREFERENCE = "preference"`
    additively — existing members (`WORKING`/`EPISODIC`/`SEMANTIC`/`PROCEDURAL`/`USER`/
    `FAILURE`) unchanged — so all seven canonical FAS §A2.11.1 tiers are now representable
    by a `MemoryTier` value.
  - **The Capability tier** (`friday/memory/capability_memory.py::CapabilityMemory`). A
    memory VIEW formed from `competence.updated` events, upserting by
    `(capability, environment)` so there is at most one current record per key (no
    unbounded duplicates). `CapabilityRecord` carries capability / environment /
    confidence / attempts / summary / timestamp and projects to a
    `MemoryEntry(tier=CAPABILITY, ...)`. It exposes `attach(kernel)` (subscribes to
    `competence.updated`), a defensive `_on_competence` handler that never raises, a
    direct `record_capability(...)` API, `recall(capability?, environment?, limit)`, and
    the uniform `retrieve(query, top_k)`. It is **not a competence authority**: it performs
    no competence math, exposes no gate / confidence-authority method, and imports no
    `friday.competence` — it records only what the event reported.
  - **The Preference tier** (`friday/memory/preference_memory.py::PreferenceMemory`). A
    persistent, queryable record of user preferences as upsertable `(key, value)` records
    (with an optional description); a newer value for the same key supersedes the older.
    `PreferenceRecord` projects to a `MemoryEntry(tier=PREFERENCE, ...)`. It exposes
    `attach(kernel)`, a defensive `_on_preference` handler, a direct
    `record_preference(key, value, description="")` API, `get(key)` / `all()` queries, and
    the uniform `retrieve(query, top_k)`. Per Axiom 15, no preference event type was
    invented: a grep of the bus found none, so `attach` stores the kernel handle and
    subscribes to nothing today — the single place a real event type would be wired later.
    JSON-safe values (including `False` / `0` / `None`) are preserved exactly.
  - **Retrieval-router participation** (`friday/memory/controller.py`).
    `build_retrieval_router(...)` gained keyword-only `capability_memory=None` /
    `preference_memory=None`, registering each (when supplied) under `MemoryTier.CAPABILITY`
    / `MemoryTier.PREFERENCE` using the same `callable(getattr(store, "retrieve", None))`
    guard as the FAILURE tier. The signature/behavior for existing parameters is preserved.
  - **Opt-in reactive-loop wiring** (`friday/kernel/reactive_loop.py`).
    `attach_reactive_loop(...)` gained optional `capability_memory=` / `preference_memory=`
    params, attaching each only when supplied (exactly like `failure_memory`) and adding
    both to the `ReactiveLoop` holder. Default `None` → not attached → hermetic runs write
    no disk files.
  - **Guarded bootstrap wiring** (`friday/api/server.py`). Within the
    `FRIDAY_USE_KERNEL_EXECUTION=1` block, bounded `CapabilityMemory()` +
    `PreferenceMemory()` are constructed, passed to `attach_reactive_loop(...)`, and passed
    to `build_retrieval_router(...)` so they participate in routing. Additive; the default
    (flag-off) path is byte-unchanged; a wiring failure is logged and never crashes
    bootstrap (A2.14.2).
  - **Traceability true-up** (`docs/architecture/*`). A2.11 seven-tier memory marked
    **Built**; the matrix now shows nothing Partial or Absent across all of A2.1–A2.14.

## 1. Regression safety (automated)

- Full-suite checkpoint (established gate command, from repo root):
  `python -m pytest tests -q` → **1683 passed, 0 failed, 113 warnings in 171.08s
  (0:02:51)**. Total collected **1683** = baseline floor **1677** (post-M22) + the **6**
  new M21 property tests (`tests/friday/test_m21_memory_seven_tiers.py`), so the M21 tests
  are confirmed included and the zero-failure Requirement 7.2 checkpoint is satisfied.
- **Clean process table.** Before running, the process table was checked and no
  stale/background pytest suites were active (only MCP servers and the Jedi language
  server), so the load-sensitive M1 throughput benchmark ran on a clean machine with no
  shared-load contamination.
- **A8 kernel throughput benchmark green.** The M1 benchmark
  `tests/kernel/test_kernel.py::TestBenchmark::test_a8_100_ticks_per_second_sustained`
  passed both inside the full suite (0 failed) and in a targeted re-run bundled with the
  M21 suite (**7 passed in 13.68s** = 1 A8 + 6 M21), confirming the ≥100 ticks/sec
  architectural threshold with no timing flake.
- **Router / reactive-loop / server-touching tests green.** Tasks 6/7/8 changed
  `build_retrieval_router`, `attach_reactive_loop`, and `server.py`; all existing tests
  touching the retrieval router, the reactive loop, and the server bootstrap passed inside
  the 0-failed full suite. The router changes are strictly additive (new keyword-only
  params default `None`), so the existing FAILURE-tier and base-tier routing behavior is
  unchanged.
- **No production default changed.** Both tiers are attached only in the guarded
  `FRIDAY_USE_KERNEL_EXECUTION=1` bootstrap and only when supplied to the reactive loop; they
  are inert without a kernel and hermetic tests perform no unbidden disk I/O (every store in
  the property tests is confined to pytest `tmp_path`, so no `friday_data/` files are
  written). Rollback = leave the flag off (byte-unchanged default path).

## 2. Architecture compliance

- **Reuse, not duplicate (Req 4.1 / 4.2, Property 6).** Both tiers are backed by the
  existing bounded `JSONFileStore` and the `MemoryEntry` contract — no new persistence
  mechanism — and both mirror the `FailureMemory` pattern exactly (`attach(kernel)`,
  defensive handler, bounded store, direct `record_*` API, uniform `retrieve`). No duplicate
  memory framework is introduced. `test_p6_reuse_and_isolation` asserts both modules import
  only `friday.memory.*` / `friday.events.*` (+ stdlib).
- **Capability-is-memory-not-authority invariant (Req 2.3, Properties 2 / 6).** The
  Capability tier performs no competence math, exposes no `is_permitted` /
  `effective_confidence` (or any gate/authority) method, and imports no `friday.competence`
  — it records only the values carried on the `competence.updated` event and defers
  entirely to the `CompetenceModel` (Ch 28, the sole competence authority).
  `test_p2_capability_record_recall_upsert_and_memory_not_authority` asserts `not
  hasattr(cm, "is_permitted")`, `not hasattr(cm, "effective_confidence")`, and that no
  imported target starts with `friday.competence`; `test_p6_reuse_and_isolation` reasserts
  the import isolation (also excluding `friday.recovery`).
- **No application-specific logic (Axiom 15, Req 4.3).** Capability keys are the generic
  `(capability, environment)` pair and preferences are the generic `(key, value)` pair; no
  app / site / window-title identity appears anywhere. No preference event type was invented
  — a bus grep found none, so `PreferenceMemory.attach` subscribes to nothing and the tier
  is driven by its documented direct API, keeping the append-only `EventStore` free of any
  fabricated type.
- **Bounded storage + defensive handlers never raise (Req 2.4 / 3.3, §A2.11.4).** Both
  stores are bounded via `JSONFileStore(max_entries=...)` (oldest evicted); upserts delete
  the prior record for a key before storing so there are no unbounded duplicates. Every event
  handler (`_on_competence`, `_on_preference`) catches narrowly and degrades to a no-op,
  never raising into the bus (`BaseException` still propagates).
  `test_p4_bounded_storage_and_uniform_retrieve` drives arbitrary `max_entries` and asserts
  `count() <= max_entries`; the malformed-event arms of Properties 2 and 3 drive empty /
  missing-field / `None` / junk-typed payloads and assert the store count is unchanged and
  nothing raises.
- **Opt-in wiring → hermetic runs write no disk files (Req 6.1, Property 6).** The tiers are
  attached only when a caller supplies an instance to `attach_reactive_loop` (default `None`
  → not attached) and only constructed inside the guarded bootstrap block. The property tests
  confine every store to `tmp_path`, so no `friday_data/` file is written by the suite.
- **Default (flag-off) path byte-unchanged (Req 6.3).** All new bootstrap and router code is
  additive: the router's new params are keyword-only with `None` defaults and the server
  wiring lives inside the existing `FRIDAY_USE_KERNEL_EXECUTION=1` guard. The default
  execution path is unchanged, confirmed by the 0-failed full suite.

## 3. Requirements coverage

| Req | Requirement | How satisfied | Validating tests / properties |
|---|---|---|---|
| 1 | Capability + Preference tier identifiers (`MemoryTier.CAPABILITY` / `PREFERENCE` added additively; all seven canonical FAS tiers representable; existing members unchanged) | Two members appended to `MemoryTier`; existing members untouched | **Property 1** (`test_p1_seven_tier_ids_complete`) |
| 2 | Capability memory tier (record by `(capability, environment)` from `competence.updated`; malformed events ignored, handlers never raise; memory VIEW only — no competence math/override/authority; `recall` + uniform `retrieve`; bounded) | `CapabilityMemory` upserts by key, defensive `_on_competence`, no competence import/authority method, bounded `JSONFileStore` | **Property 2** (`test_p2_capability_record_recall_upsert_and_memory_not_authority`), **Property 4** (bounded + retrieve), **Property 6** (isolation) |
| 3 | Preference memory tier (upsert-by-key `(key, value)` + description; bus signal ignored-if-malformed + direct `record_preference` API; `get`/`all` + uniform `retrieve`; bounded) | `PreferenceMemory` upserts by `key`, defensive `_on_preference`, direct API, `get`/`all`, bounded store; JSON-safe values preserved exactly | **Property 3** (`test_p3_preference_upsert_get_all_and_malformed_safe`), **Property 4** (bounded + retrieve) |
| 4 | Reuse, not duplicate (backed by `JSONFileStore` / `MemoryEntry`; `FailureMemory` pattern; no application-specific logic) | Both tiers reuse the existing store + entry contracts and the `FailureMemory` template; generic keys only | **Property 6** (`test_p6_reuse_and_isolation`), **Property 2** (no `friday.competence`) |
| 5 | Retrieval-router participation (both satisfy the source contract via `retrieve`; `build_retrieval_router` registers both when supplied) | Factory registers `capability`/`preference` sources under CAPABILITY/PREFERENCE with the `callable(retrieve)` guard | **Property 5** (`test_p5_router_participation`) |
| 6 | Additive, safe integration (opt-in in loop/bootstrap → no unbidden disk I/O; production bootstrap attaches both + registers in router; default path byte-unchanged; suite green) | Opt-in `attach_reactive_loop` params; guarded `server.py` construction + router registration; default path untouched | **Property 6** (opt-in / no-disk), full-suite checkpoint (§1) |
| 7 | Verification artifacts (property/unit tests covering tier ids, capability recording + memory-not-authority, preference upsert + query, bounded storage, defensive handlers, uniform retrieve, router participation; FAS A2.11 → Built + matrix true-up; after-milestone review + zero-failure checkpoint) | 6 Hypothesis property tests (Properties 1–6, ≥100 examples each); FAS + matrix updated; this review | §5, §6 below; §1 checkpoint |

## 4. Benchmark results

**No new benchmark.** Memory tiers are not measured capabilities — the Capability and
Preference tiers are persistent stores consumed through a uniform `retrieve` surface, not
scored capabilities that produce competence output. This is consistent with the M21 slice 1
(Failure memory) policy and the M17/M19/M20/M22 coordinator/infrastructure policy. No
benchmark is introduced and **the 5-domain competence scorecard is unchanged**. The existing
capability benchmarks remain the scorecard.

## 5. Verification

- **Full-suite checkpoint:** `python -m pytest tests -q` → **1683 passed, 0 failed,
  113 warnings in 171.08s (0:02:51)**, started on a clean process table (no stale pytest
  suites) so it represents one clean repo-root checkpoint. **1683** = 1677 baseline floor
  (post-M22) + 6 new M21 property tests.
- **M21 property tests (Properties 1–6) green:** all 6 tests in
  `tests/friday/test_m21_memory_seven_tiers.py` — Property 1 (`test_p1_seven_tier_ids_complete`),
  Property 2 (`test_p2_capability_record_recall_upsert_and_memory_not_authority`),
  Property 3 (`test_p3_preference_upsert_get_all_and_malformed_safe`),
  Property 4 (`test_p4_bounded_storage_and_uniform_retrieve`),
  Property 5 (`test_p5_router_participation`),
  Property 6 (`test_p6_reuse_and_isolation`) — are included in the 1683-test green
  checkpoint and passed in a targeted re-run bundled with A8 (**7 passed in 13.68s**).
- **A8 throughput green:** the ≥100 ticks/sec architectural threshold holds in both the full
  suite and the targeted re-run; no timing flake observed.
- **Router / reactive-loop / server-touching tests green:** all existing tests exercising the
  changed `build_retrieval_router`, `attach_reactive_loop`, and `server.py` bootstrap passed
  within the 0-failed full suite; the changes are strictly additive with `None` defaults.
- **Diagnostics:** this review file was checked after writing; no diagnostics reported.

## 6. Traceability

- **A2.11 seven-tier memory: Partial → Built.**
  - `docs/architecture/FAS_v2.1_AMENDMENTS.md` — A2.11 marked **Built** noting all seven
    FAS §A2.11.1 tiers now exist on the live path, with §A2.11.2 (Capability is a memory
    view, not an authority), §A2.11.3 (Preference is upsert-by-key), and §A2.11.4 (reuse /
    bounded / defensive / routed) added, pointing at
    `friday/memory/capability_memory.py::CapabilityMemory` and
    `friday/memory/preference_memory.py::PreferenceMemory`.
  - `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` — the A2.11 seven-tier row flipped
    **Partial → Built** (M21 slice 2), citing both new modules and their router
    registration.
- **The matrix now reflects reality — nothing remains Partial or Absent.** The "Summary by
  state" prose now states every v2.1 concept (A2.1–A2.14) is **Built**: *Built* enumerates
  all seven memory tiers; *Partial (remaining expansion)* is **none** (the last Partial row,
  A2.11 seven-tier memory, is now Built); *Absent (new build)* is **none**.
- **This closes the Architecture v2.1 build-out entirely.** A2.11 was the sole remaining
  Partial capability after M22 closed A2.12; with the Capability and Preference tiers built,
  the full seven-tier model is complete and the entire v2.1 amendment set (A2.1–A2.14) is
  Built.
- FAS reference: Ch 14/50; v2.1 amendment A2.11. Reuses `JSONFileStore` / `MemoryEntry`, the
  `FailureMemory` pattern, and the M19 Retrieval Router. The `CompetenceModel` remains the
  competence authority (Capability tier is a memory view); no duplicate systems; no
  application-specific logic (Axiom 15); handlers never raise into the bus (A2.14.2).

## 7. Decision

- **PROCEED — zero-failure gate satisfied.** The last *Partial* capability (A2.11
  seven-tier memory) is now built and verified additively: the Capability tier
  (`CapabilityMemory` — a memory view from `competence.updated`, upsert by
  `(capability, environment)`, never a competence authority) and the Preference tier
  (`PreferenceMemory` — upsert-by-key user preferences), both bounded, `JSONFileStore`-backed
  with the uniform `retrieve(query, top_k)` surface, registered in `build_retrieval_router`,
  wired opt-in through `attach_reactive_loop`, and constructed in the guarded `server.py`
  bootstrap. Reuse not duplicate (no new persistence), Capability-is-memory-not-authority
  preserved (Properties 2/6), no application-specific logic (Axiom 15), bounded storage with
  defensive handlers that never raise, and additive wiring with the default flag-off path
  byte-unchanged. All **1683 tests pass** (0 failed); the 6 M21 property tests (Properties
  1–6) are green and the M1 A8 kernel throughput benchmark holds ≥100 ticks/sec in both the
  full suite and a targeted re-run, with no shared-load contamination.
- **No new benchmark** — memory tiers are not measured capabilities; the 5-domain scorecard
  is unchanged (consistent with M21 slice 1).
- **Architecture v2.1 build-out closed entirely.** With the seven-tier memory model complete
  and A2.11 flipped Partial → Built, the v2.1 traceability matrix reflects reality: every
  v2.1 concept (A2.1–A2.14) is **Built** — nothing remains Partial or Absent.
- **Working tree left uncommitted for user review.** No commit was made; changes remain in
  the working tree for inspection.
- Recommended next: have planning/deliberation consult `CapabilityMemory.recall(...)` and the
  router's CAPABILITY/PREFERENCE tiers on the live path so the new tiers are exercised in
  production, and wire a real preference event type into `PreferenceMemory.attach` if/when one
  is introduced on the bus.

Reviewer / date: FRIDAY orchestrator, M21 (slice 2) close-out.
