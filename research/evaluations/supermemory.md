# Evaluation: Supermemory

**Tier**: 1 (HIGH)
**Source**: https://github.com/supermemoryai/supermemory
**Date**: 2026-06-09
**Verdict**: Adopt as an optional, interface-gated memory backend. Keep local JSON default.

---

## What It Provides

Supermemory is a memory API/engine for AI agents. Based on current docs
(content rephrased for licensing compliance):

- A memory layer that sits beneath an existing AI stack without changing
  model calls or provider setup.
- A memory graph tracking relationships across sessions.
- User profiles built automatically from behavior.
- Sub-300ms retrieval claimed, with reported 85.4% accuracy on the
  LongMemEval benchmark, processing 100B+ tokens monthly.
- A universal MCP server making memories available to any LLM, plus
  integrations for Claude Code and other harnesses.

Sources: supermemory.ai blog (Best Memory APIs for Stateful AI Agents 2026,
AI SDK guide), GitHub README. *Content was rephrased for compliance with
licensing restrictions.*

## How FRIDAY Could Use It

- As an alternative backend behind our existing `MemoryStore` interface
  (`friday/memory/interfaces.py`), replacing or augmenting `JSONFileStore`
  for the episodic and semantic tiers.
- Its memory-graph + temporal relationship tracking maps well onto our
  semantic tier and the "unified agentic memory across harnesses" goal
  (shared memory between Kiro, future coding agents, and FRIDAY).
- The universal MCP angle aligns with cross-harness memory sharing.

## Fit Assessment

| Criterion | Assessment |
|-----------|-----------|
| Capability | Strong — graph memory + temporal reasoning exceed our current cosine search |
| Reliability | Unknown at our scale; benchmark numbers are vendor-reported |
| Maintainability | Adds an external dependency / hosted service — increases ops surface |
| Scalability | Designed for scale (100B+ tokens/mo) — far beyond our needs today |
| UX | Faster, smarter recall would improve assistant continuity |
| Cost | Hosted tiers exist; must confirm free/student tier covers our usage |
| Vendor lock-in | Mitigated IF we keep it behind our MemoryStore interface |

## Risks

- **Dependency on a hosted service** conflicts with our local-first principle
  unless self-hosted. The repo is open source (self-host path exists).
- **Privacy** — sending interaction memory to a third party needs explicit
  owner consent (our content_safety + local-first stance).
- **Premature optimization** — our current 4-tier memory with NVIDIA
  embeddings is sufficient for v1 scale.

## Recommendation

**Adopt later, interface-gated.** Concretely:
1. Do NOT integrate now. Current semantic memory is adequate.
2. When memory scale/quality becomes a bottleneck, implement a
   `SupermemoryStore(MemoryStore)` backend — self-hosted first.
3. Keep `JSONFileStore` as the default; Supermemory becomes opt-in via config.
4. Never send memory off-device without explicit owner opt-in.

**Priority**: Medium. Our `interfaces.py` already makes this a clean, low-risk
future swap. No core changes needed to prepare.
