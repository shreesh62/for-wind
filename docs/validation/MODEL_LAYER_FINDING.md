# Critical Finding — the model layer was entirely non-functional

Found while gathering live product-path evidence for the kernel-default decision.
It invalidates the latency numbers in earlier validation runs, so it is recorded
separately rather than folded quietly into a verdict.

## What was wrong

`ModelRouter.complete` failed over between **providers**, never between **models**.
It selected one model per provider (`_best_model_for`, the single highest priority)
and, if that call raised, moved to the next *provider*. With NVIDIA as the only
registered provider that meant: **one model attempted, then total failure** — while
the same provider offered nine other models, several of them working.

The highest-priority model for reasoning/conversation/classification,
`qwen/qwen3.5-397b-a17b`, returns **HTTP 404** on the current key (the hosted
function id no longer exists). So every LLM call in the entire system failed:

```
RuntimeError: All providers failed for capability=conversation.
Last error: NVIDIA API returned 404: ... Specified function in account ... is not found
```

One HTTP request per call, then give up. The router's own usage stats showed it
plainly once looked at: **`failure_rate: 1.0`, `total_tokens: 0`** across 7 requests.

## Why it went unnoticed

Every consumer degrades gracefully, which is normally a virtue and here was
camouflage:

- `RequirementsDiscovery` falls back to heuristic requirements.
- `LLMDecomposer` falls back to generic capability inference.
- `GoalExecutor._generate` falls back to returning gathered info verbatim.
- `FridayBridge._handle_jarvis` fell through to "I'm ready to help, but no language
  model is configured." — the one place the failure was user-visible.

Research still produced real source URLs and real files, because research is
search-plus-read and needs no LLM. Requirements were still satisfied because the
Evidence Law scores artifacts, not prose. So goals "completed", benchmarks scored,
and parity was perfect — all on non-LLM fallbacks.

## Model reachability, measured

Each registered model id probed directly with a minimal chat request:

| Model | Priority | Result |
|---|---|---|
| `qwen/qwen3.5-397b-a17b` | 12 | **404 Not Found** (retired function id) |
| `mistralai/mistral-medium-3.5-128b` | 11 | OK, **25.2s** |
| `meta/llama-3.2-90b-vision-instruct` | 10 | OK, 5.3s |
| `openai/gpt-oss-20b` | 5 | OK, **1.0s** |
| `nvidia/nemotron-mini-4b-instruct` | 3 | OK, 0.8s |
| `openai/gpt-oss-120b` | 6 | **timeout >45s** |
| `nvidia/nemotron-content-safety-reasoning-4b` | 8 | **410 Gone** |
| `microsoft/phi-4-multimodal-instruct` | 7 | **410 Gone** |
| `meta/llama-guard-4-12b` | 10 | 400 — a guard model, rejects a plain chat shape |
| `nvidia/nv-embed-v1` | 10 | n/a — embedding-only, correctly not a chat model |

The registry itself is fine; `nv-embed-v1` and `llama-guard-4-12b` are declared with
`EMBEDDING` / `CLASSIFICATION` only, so probing them for chat was the probe's error,
not a misclassification.

Also worth noting: the endpoint returned a `Deprecation: 2026-07-27T00:00:00Z`
header.

## The fix

1. **Per-model failover.** `complete()` now iterates the provider's candidate models
   for the capability in priority order, and only moves to the next provider once
   they are exhausted. An explicitly requested `model=` is still the only candidate —
   asking for a model by name must not silently get a different one.
2. **Dead-model circuit breaker.** A model whose error looks permanent (404 / 410 /
   400 / "not found" / "gone") is skipped for the rest of the process, so a retired
   id is not re-attempted on every request. Marked per-process, so it self-heals on
   restart instead of hardcoding a dead-model list that would rot. If *every*
   candidate has been marked, the full list is retried rather than reporting a
   silent "no models" condition.
3. **Timeout strikes.** One timeout is forgiven; a model that times out twice is
   treated as a latency sink and skipped.
4. **Per-model usage accounting.** A failure is recorded against the model id that
   actually failed instead of `"unknown"`, so stats show *which* model is broken.
5. **Observability.** `ModelRouter.unavailable_models` exposes what dropped out and
   why, and each drop is logged. Previously the degradation was silent.

Verified: all three capabilities that failed before now succeed, and the dead
primary is skipped on subsequent calls. 13 regression tests in
`tests/friday/test_router_failover.py`.

## Consequence for earlier evidence

**Latency figures in prior validation runs are not valid** and must be re-measured.
They were fast because LLM calls failed instantly and fell back — not because the
pipeline was efficient. Concretely, the same live goals went from ~6s (no LLM) to
~170–290s (real LLM calls).

Correctness evidence is less affected: parity, evidence artifacts, files, and source
URLs were real. But it was measuring the **fallback** behavior of the system, so it
under-tested the LLM-dependent paths (planning quality, decomposition, synthesis).

## Model mix — decided (option 2), implemented

Latency was dominated by model choice. Option 2 was taken: fast models lead the
latency-sensitive capabilities, a large model still leads synthesis.

A single global `priority` per model cannot express that, so `ModelInfo` gained an
optional `capability_priority` map plus `priority_for(capability)`, and selection
ranks by it (falling back to `priority` for any capability not listed, so unlisted
models keep their exact previous ordering). `get_models_for_capability` was ranking by
the global priority, which disagreed with what `complete()` actually picked — now both
use the same ranking.

Effective leads and measured latency after the change:

| Capability | Lead model | Latency |
|---|---|---|
| conversation | `openai/gpt-oss-20b` | 1.7s |
| classification | `nvidia/nemotron-mini-4b-instruct` | 0.8s |
| reasoning | `meta/llama-3.2-90b-vision-instruct` | 0.9s |

Down from ~25s per call. Two further ordering corrections came out of the measurements:

- `openai/gpt-oss-120b` was demoted to last on conversation/classification. It times
  out and the provider retries 3× before raising, so merely being *tried* cost ~135s.
- The two moderation models (`meta/llama-guard-4-12b`,
  `nvidia/nemotron-content-safety-reasoning-4b`) were zeroed for general
  classification. `llama-guard` led it at global priority 10 and failed **every**
  request with HTTP 400 before failover, because it rejects a plain single-turn chat
  shape. Both stay registered — `llama-guard` is the safety-gate model, selected
  explicitly by name — they just never lead the general path.

`SUMMARIZATION` still leads with the 404 model. That is deliberate: "dead" is a runtime
fact, not a permanent one, and the circuit breaker removes it after one attempt. If the
hosted function returns, it is genuinely the best model for that capability.

### Original options, for the record

- `mistralai/mistral-medium-3.5-128b` (priority 11) is the top *working* model for
  reasoning and conversation at **~25s per call**. A multi-step goal makes many
  calls, hence ~3–5 minutes per goal.
- `openai/gpt-oss-20b` answers the same prompts in **~1s** but sits at priority 5.

Options:

1. **Leave priorities as they are** — best available quality, minutes per goal.
2. **Raise the fast models** for latency-sensitive capabilities (classification,
   conversation) and keep the larger model for reasoning/synthesis only.
3. **Latency-aware selection** — track observed latency and prefer a fast model when
   the caller passes a latency budget. The most flexible, and the most new machinery.

Option 2 was taken, as described above.
