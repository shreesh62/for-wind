# Cognitive Kernel — Production Readiness Verdict

**Milestone:** M13 — Production Validation & Architecture v2.1 (Part 1)
**Date of assessment:** current session (sandbox, `FRIDAY_DRY_RUN=1`)

---

## Verdict

> **NOT YET QUALIFIED — pending real-machine execution of the validation harness.**

This is an honest, evidence-gated verdict, not a failure judgment. The kernel path is
**architecturally ready and behaviorally proven equivalent in every check that can run without live
resources**, but production promotion **requires** the real-world validation runs, which cannot be
performed in this sandbox.

## Why "not yet" — exactly what is outstanding

The promotion criteria C1–C8 (see the Validation Plan) require realistic end-to-end goals on a real
machine: a live browser (Chrome/CDP), desktop control, network access, model providers, and GPUs.
This agent runs under `FRIDAY_DRY_RUN=1` with **none** of those, so 13 of the 18 scenarios are
`requires_live` and are correctly **skipped** rather than fabricated. Specifically outstanding:

- **C1/C2 on live scenarios** — correctness + evidence parity for browser, desktop, multi-environment,
  research, long-running, unknown-app, concurrent, world-model, and goal-graph categories.
- **C3 Recovery** — crash, browser-failure, and interruption/resume must be exercised against real
  failures.
- **C6 Performance** — latency/throughput/memory must be measured against real model + browser I/O.
- **C7 Safety** — the human-confirmation gate must be observed with a real irreversible action.

## What IS already established (no live resources required)

The following have automated evidence in the suite (1234 tests green) and require no real machine:

- **Behavioral parity harness** (`test_m12_parity.py`) — the kernel path and legacy path produce
  equivalent human-readable results for the same `OperatorOutcome` (C1 shape confirmed in-process).
- **Fail-safe execution** (`test_m12_failure_injection.py`) — operator/factory/sink failures never
  crash the tick loop; malformed events ignored; garbage outcomes default to `goal.failed` (C8 shape).
- **Determinism + replay** (`test_m12_failure_injection.py`, `test_m13_validation_tooling.py`) — the
  goal lifecycle is persisted and deterministically replayable from the durable event log (C4 shape).
- **Isolation** (`test_m12_isolation.py`) — the execution runtime imports only events + kernel
  contracts; no coupling to operator/memory/bridge/executor.
- **No-default-change guarantee** (`test_m12_bridge_compat.py`, `test_m13_validation_tooling.py`) —
  with the flag off (default), the legacy path is used; the harness restores env and never mutates the
  default.

In short: the **software** is ready; the **evidence** is not yet complete because it can only be
produced by the maintainer running the harness on a real machine.

## The gate

```
IF (maintainer runs the harness on a real machine)
   AND (docs/validation/PARITY_REPORT.md satisfies C1–C8)
THEN  verdict → PRODUCTION-READY  → execute the rollback strategy + flip commit below
ELSE  verdict remains NOT-QUALIFIED, naming the failing criteria
```

---

## Rollback strategy (to be used ONLY after C1–C8 pass)

The flip is deliberately trivial to revert because M12 built it as a pure superset:

1. **Flip mechanism:** the default lives in one place — `BridgeConfig.use_kernel_execution` — plus the
   server env gate `FRIDAY_USE_KERNEL_EXECUTION`. Promotion = change that single default to `True`
   (and/or default the env gate on in `api/server.py`).
2. **Instant rollback (no redeploy):** set `FRIDAY_USE_KERNEL_EXECUTION=0` (or leave unset) — the
   bridge immediately routes multi-step goals back through the legacy Operator path. Runtime kill
   switch, zero code change.
3. **Code rollback:** revert the single flip commit; the legacy inline Operator branch is retained
   (not deleted) until at least one full release cycle proves the kernel default in production.
4. **Blast radius:** Level-1 simple-action path (FridayEngine) is unaffected either way; only
   multi-step/complex routing changes.

## The single isolated flip commit (prepared, NOT applied)

When qualified, apply exactly one commit containing only:

```python
# friday/bridge.py — BridgeConfig
    use_kernel_execution: bool = True   # was False; flipped after M13 validation C1–C8 passed
```
and optionally:
```python
# friday/api/server.py — default the env gate on (still overridable to "0")
    use_kernel = os.getenv("FRIDAY_USE_KERNEL_EXECUTION", "1") == "1"   # was default "0"
```

No other file changes. The legacy branch stays in place as the rollback target. Do **not** apply this
commit until the parity report satisfies every promotion criterion on a real machine.
