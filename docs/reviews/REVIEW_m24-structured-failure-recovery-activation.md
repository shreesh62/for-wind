# After-Milestone Review — M24 Structured Failure Taxonomy & Verification-Event Activation

> Governance gate. M24 implements audit architectural objectives 1–4 (structured error model,
> unified observability, failure classification, recovery framework) by fixing a concrete
> root-cause defect: the failure→recovery/competence/reflection loop was dormant because nothing
> published the `verification.completed` event its subscribers listen for.

## 0. Milestone under review

- Milestone: `M24 — Structured Failure Taxonomy & Verification-Event Activation`
- Target capability domain(s): cross-cutting — **failure recovery** ("Can it recover from failures?")
  and **self-explanation/verification** ("Can it explain and verify its own behavior?"). Architectural
  mechanism improvement.
- Summary: Recon of the FRIDAY package established that `RecoveryEngine`, `CompetenceModel`, and
  `ReflectionEngine` all subscribe to the `verification.completed` kernel event, but **no module
  published it** — the whole reactive loop was inert in production. M24 adds (1) a structured failure
  model (`FailureDomain` stage taxonomy + `Severity` + a total, data-driven `classify_error_category`
  + a first-class `StructuredFailure`), reusing — not duplicating — the existing `FailureClass`/
  `RecoveryLevel` recovery taxonomy; (2) the missing `VerificationEventPublisher` that emits
  `verification.completed`, activating the loop; (3) a `FailureLogSubscriber` that makes logging a
  consumer of the event system; and (4) additive, kernel-gated wiring in the `Operator` verdict path.

## 1. Regression safety (automated)

- [x] Full test suite green: `python -m pytest tests/friday/ tests/world/ -q` → **1431 passed, 0 failed**
      (pre-M24 floor 1403; +28 new M24 tests across 6 files, incl. property tests ≥100 examples, the
      end-to-end reactive-loop activation test, and the deterministic recovery-rate benchmark).
- [x] No production default changed. All new code is **additive and inert without a kernel**: the
      `Operator` publishes verdicts only when a `kernel` is injected; the benchmark runner and existing
      tests construct the `Operator` without one, so behavior is byte-identical. Rollback = do not inject
      a kernel.
- [x] Architectural invariants preserved: one Kernel / World Model / Goal Graph / Competence Model;
      **no duplicate systems** (the existing `FailureClass`/`RecoveryLevel`/`RecoveryEngine`/event bus
      are reused; `FailureDomain` is an orthogonal *stage* dimension, not a second recovery taxonomy);
      Axiom 15 (the classifier is a data map over generic category tokens, no app/site identity);
      structured error model (no new `except Exception: pass` — the publisher/subscriber catch narrowly
      and degrade to a no-op, never raising into the tick loop or bus); replay-safe (event payloads stay
      JSON-serializable via an evidence summary).

## 2. Real-world capability benchmarks (real machine)

M24 is cross-cutting plumbing, not a new benchmark domain; it does not alter the 5-domain scorecard
(the benchmark runner builds the `Operator` without a kernel, so no events fire and scoring is
unchanged). No probabilistic scores were recorded. The competence-relevant proof is the **integration
test** (P4) demonstrating the mechanism end-to-end:

```
test_p4_activates_recovery_loop:
  CognitiveKernel + RecoveryEngine.attach(kernel) + VerificationEventPublisher.attach(kernel)
  publish_verdict(satisfied=False, requirement="gather information about renewable energy")
  => a `recovery.proposed` event is emitted  (previously: nothing — the loop was dormant)
test_p4_satisfied_verdict_does_not_trigger_recovery:
  publish_verdict(satisfied=True) => no recovery proposed
```

- Ratchet verdict: **N/A for the scorecard** (unchanged by design); the milestone is gated instead on
  the activation integration test + full-suite green, both PASS.

## 3. Competence delta

| Domain | Prev baseline | This run | Δ | Verdict |
|---|---|---|---|---|
| browser / desktop / research / coding / long_horizon | (unchanged) | (unchanged) | 0 | held — scorecard not touched |
| failure recovery (mechanism) | dormant (loop never fired) | **active** (verdict → recovery.proposed) | **+** | improved — root-cause defect fixed |
| observability | prints / kernel-only logging | failures/recoveries → structured records | **+** | improved |

- Did the target improve or hold? **Improved.** The failure→recovery/competence/reflection loop is now
  activatable in production (previously dead code), and failures are first-class, classified, and logged
  through the event system. No non-target domain regressed.

## 4. Architecture review

- FAS chapters/amendments realized: **A2.14 — Structured Failure & Recovery Activation** (§A2.14.1–.5),
  expanding Ch 21 (events/observability), Ch 34 (recovery), Ch 52 (kernel-driven). Traceability matrix
  updated (A2.13 + A2.14 rows, marked Built).
- Mechanism vs component: improved a **mechanism** — the previously inert reactive loop now fires, and a
  canonical failure classification replaces free-form strings — not a task-specific feature.
- Production activation (done in this milestone): `friday/kernel/reactive_loop.py::attach_reactive_loop`
  is a single reusable helper that wires recovery + competence + reflection + observability to a kernel;
  `friday/api/server.py` now calls it and passes `kernel=` to the Operator in the guarded
  `FRIDAY_USE_KERNEL_EXECUTION=1` block. An end-to-end test proves one failed verdict drives
  `recovery.proposed` + `competence.updated` + a structured log record together — the loop is LIVE, not
  merely activatable.
- Recovery-rate measurement (audit objective 5): `friday/benchmarks/recovery.py::RecoveryBenchmark` is a
  deterministic, hermetic harness that feeds synthetic failure verdicts through the active loop and
  reports recovery rate, proposal rate, and failure-domain/-class distributions. Measured run: **6/6
  recoverable failures → actionable recovery plans (recovery rate 1.0000)** across 4 failure domains
  (perception/execution/environment/verification; failure classes precondition×4, capability×1,
  environmental×1). Excluded from the 5-domain scorecard; not recorded to the committed baseline.
- New technical debt / follow-ons (carried, not introduced):
  - Recovery currently diagnoses against an **empty** evidence bundle on the event path (the live
    `ExecutionEvidence` is summarized to keep events JSON/replay-safe). Faithful for unmet requirements
    (their demanded evidence is absent); richer in-process evidence delivery is a future enhancement.
  - Recovery-rate benchmarking (audit objective 5) builds on this producer and remains future work.
  - Legacy error-swallowing (audit #3/#6) in non-migrated top-level modules is intentionally untouched
    per the directive's legacy-cleanup policy.

## 5. Decision

- [x] **PROCEED** — a real root-cause architectural defect is fixed (the dormant recovery loop is
      activated, proven by an integration test), failures are now first-class and classified, logging is
      an event-system consumer, the full suite is green (1422, 0 failed), invariants intact, no duplicate
      systems, and no production default changed (additive, kernel-gated, rollback trivial).
- Recommended next targets (continuing the roadmap + audit objectives): (a) [DONE this milestone]
  reactive loop wired live in the production bootstrap; (b) [DONE this milestone] a deterministic
  recovery-rate benchmark (objective 5) measuring the now-active loop; (c) roadmap Phase 3 — **M21
  Memory v2 + failure memory** (a natural consumer of `StructuredFailure`, so recovery outcomes and
  failure causes persist and inform future planning), then M19 Retrieval Router and M20 Reflection v2.

Reviewer / date: FRIDAY orchestrator, M24 close-out.
