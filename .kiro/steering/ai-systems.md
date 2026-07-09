---
inclusion: manual
---

# Skill: AI Systems (LLM apps, agents, RAG)

## Prime Framing
The model is an unreliable, expensive, high-latency, *untrusted* dependency. Engineer around it like any flaky third-party service — plus treat its output as user input for security purposes.

## Reliability Engineering
- Timeouts, retries with backoff on transient errors, fallback models/paths, circuit breakers.
- Cost & latency budgets per request; token counting before sending; caching identical calls (key = model + prompt version + params + input).
- Streaming for UX on long generations; cancellation propagated.
- Idempotency where model calls trigger side effects — a retried call must not double-execute the action.

## Prompts Are Code
- Versioned, reviewed, diffed like source. Never hot-edit prompts in production by vibes.
- **Evals before tuning**: build a golden set (inputs → graded expected outputs) BEFORE optimizing prompts; every prompt/model change runs the evals; track regressions like test failures. Grading: exact-match where possible, rubric/LLM-judge where not (and spot-check the judge).
- Few-shot examples are load-bearing — treat editing them as editing logic.
- Separate system instructions / context / user input structurally; never concatenate untrusted input into the instruction section.

## Structured Output
- Schema-constrain everything consumed by code: tool-use/function-calling or JSON schema + validation (zod/pydantic) on every response. Parse-or-reject-and-retry; never regex-scrape prose and hope.
- Never eval/execute model output without a sandbox. Never let model output form SQL/shell/URLs without the same taint discipline as user input.

## Prompt Injection & Agent Security
- Any content the model reads (retrieved docs, web pages, user messages, tool results) can carry adversarial instructions. Therefore: the model's *capabilities* are the security boundary, not its judgment.
- Least-privilege tools: allowlist actions, scope credentials to the task, spend caps, step/iteration limits, no destructive tools without human confirmation.
- Human-in-the-loop for irreversible actions (sends, payments, deletes, deploys).
- Log full trajectories (prompt, context, tool calls, outputs) for post-hoc debugging — you cannot debug an agent you cannot replay.

## RAG
- Retrieval quality dominates prompt cleverness — invest there first: chunking tuned to content structure, embedding model fit, hybrid (BM25+vector) retrieval, reranking, metadata filters.
- Log retrieved chunks alongside every answer; measure groundedness (does the answer cite retrieved content?) and retrieval hit-rate against the eval set separately — they fail independently.
- Stale index = confidently wrong answers: define the reindex trigger when source data changes.

## Agents
- Constrain the loop: max steps, max cost, explicit termination conditions, progress detection (an agent repeating the same failing action needs a circuit breaker).
- Sub-task delegation must be self-contained: goal, context, constraints, definition of done, return format.
- State outside the context window (files, task lists) for anything that must survive summarization.

## Evaluation & Ops
- Ship-gating eval suite + online monitoring: cost per request, latency percentiles, refusal/error rates, output-validation failure rates, drift after provider model updates (pin model versions; upgrades are deliberate migrations with eval runs).
- A/B prompt changes where feasible; keep a rollback path to the previous prompt version.

## Checklist
- [ ] Every model output schema-validated before use?
- [ ] Untrusted content structurally separated from instructions?
- [ ] Tools least-privilege with caps? Irreversible actions gated?
- [ ] Eval set exists and ran on this change?
- [ ] Costs bounded, calls cached, model version pinned?
