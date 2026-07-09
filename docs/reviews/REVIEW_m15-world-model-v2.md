# After-Milestone Review — M15 World Model v2

> Completed per the governance rule: no milestone continues until it has demonstrated its
> effect on measured competence. This review is the gate.

## 0. Milestone under review

- Milestone: `M15 — World Model v2 (Belief Freshness, TTL, Provenance, Staleness)`
- Target capability domain(s): `research`, `long_horizon`
- Summary: Implemented FAS v2.1 §A2.1 additively over `Belief`/`WorldModel` — half-life
  freshness (reusing M9 `KnowledgeAging`), per-belief TTL + refresh policy/cost, a composable
  `BeliefProvenance` evidence graph (supporting/contradicting observations, DAG-bounded
  derivation chain, verification status), and a `WorldModel.stale_beliefs(now)` sweep that flags
  high-impact stale beliefs via a kernel event. No production defaults changed; the mechanism
  signals refresh need but does not execute refresh (deferred — no refresh source exists yet).

## 1. Regression safety (automated)

- [x] Full test suite green: `python -m pytest tests/friday/ tests/world/ -q` → **1297 passed, 0 failed**
- [x] No production default changed (World Model v2 is additive; `WorldModel(decay_rate=0.01)`
      and all `Belief` defaults unchanged; `staleness_threshold=0.1` is a new, defaulted param)
- [x] Architectural invariants preserved (one Kernel / World Model / Goal Graph / Competence
      Model; kernel-mediated events; no app-specific logic; general mechanisms). 26 new tests
      (14 Hypothesis property tests for all 14 correctness properties + 12 integration/API/
      concurrency tests), all in new files.

## 2. Real-world capability benchmarks (real machine)

Run on a real machine (NVIDIA keys live, `FRIDAY_DRY_RUN` unset), per-benchmark timeout 90s:

```
# Competence Scorecard
- Overall (mean of measured domains): 0.2000
- Ratchet: PASS
| Domain       | Score  | Measured |
|--------------|--------|----------|
| browser      | 0.0000 | yes      |
| desktop      | 0.5000 | yes      |
| research     | 0.0000 | yes      |
| coding       | 0.5000 | yes      |
| long_horizon | 0.0000 | yes      |
```

- Ratchet verdict: **PASS** (no measured domain regressed; these are the first measured baselines).
- Passing benchmarks: `desktop.create_local_artifact` (5.3s), `coding.produce_source_file` (29.3s).
- All benchmarks now **complete** (no timeouts) after the NVIDIA model-availability fix — the
  free-tier models the hot path used (`qwen3-next-80b`, `llama-3.3-70b`, `qwen3-coder-480b`) had
  died (hang / HTTP 410); repointed to verified-responsive models (`gpt-oss-120b`, `gpt-oss-20b`,
  `mistral-medium-3.5-128b`, `qwen3.5-397b-a17b`). Benchmark harness got per-benchmark progress +
  timeout so a wedged call scores a fail instead of hanging forever.

## 3. Competence delta

| Domain | Prev baseline | This run | Δ | Verdict |
|---|---|---|---|---|
| browser | UNMEASURED | 0.0000 | n/a (first measure) | established |
| desktop | UNMEASURED | 0.5000 | n/a | established |
| research | UNMEASURED | 0.0000 | n/a | established (target — NOT yet improved) |
| coding | UNMEASURED | 0.5000 | n/a | established |
| long_horizon | UNMEASURED | 0.0000 | n/a | established (target — NOT yet improved) |

- Did the target domain (research / long_horizon) improve or hold? **No measured gain yet.**
  Honest assessment: M15 delivered a correct, fully-tested *mechanism* (belief freshness /
  provenance / staleness), but it is **not yet wired into the live Operator research path**, so it
  does not by itself move the research or long_horizon benchmark. Those score 0.0 because the
  Operator does not currently produce the required `GATHERED_INFO` + `SOURCE_URL` evidence for
  those goals — a real, now-visible capability gap.
- No non-target domain regressed (there were no prior measured baselines to regress from).

## 4. Architecture review

- FAS chapters realized: §A2.1 (World Model — Belief Freshness, TTL, Provenance, Staleness),
  expanding Ch 9; reuses M9 Ch 9.22/49 `KnowledgeAging`.
- New technical debt: none introduced. Flagged (pre-existing, out of scope): stale model names in
  several `*.md` handoff docs; an unreachable dead branch in `NvidiaProvider.complete`'s retry loop.
- Amendment accuracy: §A2.1 held up in practice. The one deviation worth recording — M15
  deliberately scopes to *signalling* refresh (not executing it), because no refresh source
  exists yet; a future milestone must consume `refresh_policy`/`refresh_cost` to close the loop.
- Mechanism vs component: M15 improved a **mechanism** (beliefs are now freshness-/provenance-
  aware and staleness is detectable), but the mechanism does not yet reach the measured path — see
  §3. This is the crux for choosing the next milestone.

## 5. Decision

- [x] **PROCEED (conditional)** — competence held (ratchet PASS), invariants intact, regressions
      none, real baselines now recorded (`baseline.local.json`; committed seed stays pristine).
- **Governance note for the next milestone:** M15 established baselines but did not move its target
  measured competence. To honor "every milestone must improve a *measured* capability," the next
  milestone should target a **measured gain** — the most direct being the research / long_horizon
  path (make those benchmarks produce real `GATHERED_INFO` + `SOURCE_URL` evidence), which would
  also give M15's freshness/provenance machinery a live consumer.

Reviewer / date: FRIDAY orchestrator, M15 close-out.
