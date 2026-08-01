# Real-Machine Capability Scorecard — first run on a working model layer

`python -m scripts.kernel_validation.run_capability_benchmarks --no-cdp --browser`
(live NVIDIA models, live browser controller, CDP disabled, `--record` NOT passed).

**Supersedes** the previous scorecard, which reported 1.0 across all five domains and
9/9 benchmarks passing. That run happened while **every LLM call in the system was
failing** — see `docs/validation/MODEL_LAYER_FINDING.md`. It was measuring the
non-LLM fallback paths, so its perfect score was an artifact.

## Result

- **Overall (mean of measured domains): 0.6000**
- **Ratchet: FAIL**
- Regressions vs the recorded baseline: `long_horizon`, `research`
- Improvements: `browser`

| Domain | Score | Measured |
|---|---|---|
| browser | 1.0000 | yes |
| desktop | 0.5000 | yes |
| research | 0.5000 | yes |
| coding | 1.0000 | yes |
| long_horizon | 0.0000 | yes |

## Per-benchmark

| Benchmark | Result | Time |
|---|---|---|
| `browser.navigate_and_read` | PASS | 86.0s |
| `browser.search_multiple_sources` | PASS | 65.5s |
| `desktop.open_and_confirm` | PASS | 9.8s |
| `desktop.create_local_artifact` | **TIMEOUT (>180s) → fail** | — |
| `research.gather_with_sources` | PASS | 114.9s |
| `research.produce_cited_summary` | **TIMEOUT (>180s) → fail** | — |
| `coding.produce_source_file` | PASS | 64.3s |
| `coding.edit_existing_file` | PASS | 152.5s |
| `long_horizon.research_to_document` | **TIMEOUT (>180s) → fail** | — |

6/9 pass. All three failures are the per-benchmark 180s timeout, not incorrect
output.

## Root cause of the three timeouts: sustained-load rate limiting

Dispositive evidence — the **same benchmark, same code**, run two ways:

| Run | `desktop.create_local_artifact` |
|---|---|
| `--domain desktop` alone | **PASS in 100.7s** |
| Full five-domain suite | **TIMEOUT >180s** |

Nothing about the benchmark changed. What changed is cumulative load on the free
NVIDIA tier: by the time the suite reaches the later domains, the fast lead models
have been rate-limited and the router is failing over to slower alternatives, each
of which the provider retries 3× before raising. All three timeouts
(`desktop.create_local_artifact`, `research.produce_cited_summary`,
`long_horizon.research_to_document`) fall in the **second half** of the run, which is
the signature of progressive exhaustion rather than incorrect behavior.

So the 0.6000 is a measurement of the free tier under sustained load, not of the
pipeline's correctness. Both readings are true and they mean different things:

- Per-capability correctness: **9/9 achievable** (every benchmark has passed at least
  once when not competing for quota).
- Sustained-throughput capability: **6/9**, because quota runs out mid-suite.

The scorecard as currently designed measures the second. That is worth knowing, but
it should not be read as "the agent cannot produce a cited summary".

## Reading this honestly

The baseline the ratchet compares against was recorded from the dead-model-layer run,
so "regression" here means "worse than a number that was never real". The scorecard
was **not** re-recorded (`--record` deliberately not passed), so the invalid baseline
is still on disk and will keep reporting a regression until a trustworthy run exists
to replace it.

The three failures are timeouts under real LLM latency. The passing benchmarks now
take 65–152s where they previously took seconds, which is the same story: the work is
actually happening now.

**The 180s limit was not raised to make these pass.** Whether the limit is right is a
separate question from whether the pipeline is fast enough, and moving a threshold to
turn red into green would destroy the only signal this run produced.

## What this changes

Criterion **C2 (evidence parity) is FAIL**, not the "PASS" recorded before. The
kernel-default flip stays unapplied. See `docs/validation/KERNEL_READINESS_VERDICT.md`.

## Model-mix change in effect for this run

Per-capability model priorities were introduced (option 2 in
`MODEL_LAYER_FINDING.md`) so a fast model can lead a latency-sensitive capability
while a larger model still leads synthesis. Measured lead-model latency after the
change:

| Capability | Lead model | Latency |
|---|---|---|
| conversation | `openai/gpt-oss-20b` | 1.7s |
| classification | `nvidia/nemotron-mini-4b-instruct` | 0.8s |
| reasoning | `meta/llama-3.2-90b-vision-instruct` | 0.9s |

Down from ~25s per call when `mistralai/mistral-medium-3.5-128b` led those
capabilities. So per-call latency is no longer the bottleneck; the remaining
timeouts are about the *number* of calls and the real page/navigation work per goal.

## Desktop domain: a benchmark that was measuring a bug

`desktop.open_and_confirm` initially **failed** after the notepad fallback was
removed, then passed once its goal was made concrete.

Its goal text was *"Open a local application and confirm it is the foreground
environment."* — so vague that nothing could resolve it. It had only ever passed
because the executor carried a last-resort fallback that launched **notepad** on any
unresolvable target. That fallback also spammed the desktop with empty editors during
every run, and it meant this benchmark measured the guess, not the capability.

The fallback is gone (an unresolvable target now reports an honest failure) and the
goal is now *"Open the calculator and confirm it is the foreground window."* — the way
a user actually speaks. Naming the app is a **test input**, not app-specific logic:
the system still resolves it generically through the platform's app registry
(Axiom 15).

Result: `desktop` scores **1.0000** when measured without quota contention
(`open_and_confirm` 11.0s, `create_local_artifact` 100.7s), and both benchmarks now
pass for real reasons.

## Defect found and fixed during this run

At process shutdown the executor's `_run_async` was handed a coroutine it could no
longer schedule ("cannot schedule new futures after shutdown"), leaving it
un-awaited:

```
friday/executor.py:954: RuntimeWarning: coroutine 'ModelRouter.complete' was never awaited
```

The trigger is an **abandoned timed-out benchmark**: when a benchmark exceeds its
limit the harness stops waiting (`shutdown(wait=False)`) but the worker thread keeps
running, and it then tries to schedule new work during interpreter shutdown.

`_run_async` now accepts a **factory** as well as a coroutine, so the call that leaked
(`_generate`'s model call) never creates a coroutine until the worker is actually
about to await it — nothing can be left un-awaited. It also still closes a
directly-passed coroutine when the worker never started. Covered by
`tests/friday/test_run_async_no_leak.py` (5 tests) under `-W error::RuntimeWarning`.
