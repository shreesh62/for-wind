# After-Milestone Review — M21 (slice 1) Failure Memory

> Governance gate. Delivers A2.11 failure memory (previously **Absent**) as a consumer of
> the M24 failure→recovery loop, so failures — and their attempted recoveries — persist and
> inform future planning. Directly advances "Can it improve through experience?".

## 0. Milestone under review

- Milestone: `M21 (slice 1) — Failure Memory`
- Target capability: **learning from failure / experience** ("Can it improve through
  experience?") and self-explanation ("what failed before, and what did we do?").
- Summary: Added `friday/memory/failure_memory.py::FailureMemory` — the seventh memory
  tier (`MemoryTier.FAILURE`). It subscribes to the M24 events (`verification.completed`
  to record a failure, `recovery.proposed` to annotate it with the proposed recovery),
  exposes `record_structured` for M24 `StructuredFailure` objects, and answers
  `has_failed_before` / `recall` / `failure_count` / `statistics`. Backed by the existing
  bounded `JSONFileStore`. Wired (opt-in) through `attach_reactive_loop` and attached in
  the production bootstrap. No duplicate persistence or failure taxonomy.

## 1. Regression safety (automated)

- [x] Full suite green: `python -m pytest tests/friday/ tests/world/ -q` → **1438 passed,
      0 failed** (pre-M21 floor 1431 post-M24; +7 new failure-memory tests).
- [x] No production default changed. Failure memory is opt-in in `attach_reactive_loop`
      (attached only when supplied) — hermetic tests/benchmarks write no files; it is
      attached only in the guarded `FRIDAY_USE_KERNEL_EXECUTION=1` bootstrap.
- [x] Invariants preserved: one memory subsystem (reuses `JSONFileStore`/`MemoryEntry`/
      `MemoryTier`); no duplicate failure taxonomy (consumes M24 `StructuredFailure`);
      Axiom 15 (records generic domain/capability/environment, no app/site logic);
      structured error model (handlers never raise into the bus); bounded storage.

## 2. Real-world capability benchmarks (real machine)

Not a scored competence domain; the 5-domain scorecard is untouched (failure memory is
attached only under the kernel-execution flag and is opt-in elsewhere). Correctness is
proven by the integration test: attaching `FailureMemory` to a real `CognitiveKernel` via
`attach_reactive_loop` and publishing a failed verdict records the failure AND annotates it
with the synchronously-proposed recovery (recovery_actionable True), while a satisfied
verdict records nothing.

## 3. Competence delta

| Domain | Prev | This run | Δ | Verdict |
|---|---|---|---|---|
| 5-domain scorecard | (unchanged) | (unchanged) | 0 | held — not touched |
| failure memory (A2.11) | Absent | **Built** | + | new capability: failures persist + inform planning |
| experience/learning | recovery loop active but ephemeral | failures + recoveries remembered | + | improved |

- Target improved? **Yes** — failures are now durable, queryable, and annotated with their
  recoveries; no non-target domain regressed.

## 4. Architecture review

- FAS realized: **A2.11(f) — Failure Memory** (§A2.11f.1–.4), expanding Ch 14/50.
  Traceability matrix updated (A2.11 failure memory Absent → Built).
- Ordering fix (design invariant): in `attach_reactive_loop`, failure memory subscribes
  BEFORE recovery so the failure is recorded before the nested `recovery.proposed`
  annotates it — verified by the integration test.
- Mechanism vs component: a reusable memory tier + event consumer, not a task feature.
- Follow-ons (carried): the full seven-tier memory expansion and integration with a
  Retrieval Router (M19) / Reflection v2 (M20) remain roadmap work; planners can already
  query failure memory but are not yet wired to consult it during planning (a natural next
  step).

## 5. Decision

- [x] **PROCEED** — a previously-absent architectural capability (A2.11 failure memory) is
      built and verified, consuming the M24 loop with no duplicate systems; full suite green
      (1438, 0 failed); additive and safe (opt-in, bounded, no default change).
- Recommended next: (a) have the planner/deliberator consult `has_failed_before` to avoid
  repeating known failures; (b) roadmap **M19 Retrieval Router** (unifies retrieval across
  tiers incl. failure memory) and **M20 Reflection v2**; (c) continue the seven-tier memory
  expansion.

Reviewer / date: FRIDAY orchestrator, M21 (slice 1) close-out.
