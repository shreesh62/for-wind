# Evaluation: Memory OS / MemOS

**Tier**: VERY HIGH (already used as blueprint)
**Sources**:
- Paper: "Memory OS of AI Agent" (arXiv 2506.06326)
- Paper: "MemOS: A Memory Operating System for AI System" (arXiv 2507.03724)
- Implementation: ClaudioDrews/memory-os (7-layer, Hermes Agent, Qdrant)
**Date**: 2026-06-09
**Verdict**: Already adopted as our memory blueprint. Adopt ONE new idea: temporal edges.

---

## What It Provides

Memory OS treats memory as a manageable system resource — like an operating
system managing RAM/disk. Key concepts (rephrased for compliance):

- A layered memory stack (the reference implementation uses 6-7 layers:
  flat markdown files → structured facts → vector DB like Qdrant → auto-curated
  knowledge → surgical context injection).
- MemOS unifies representation, scheduling, and evolution of different memory
  types (plaintext, activation-based, parameter-level) for cost-efficient
  storage and retrieval.
- The "temporal edges" pattern: store every fact with `valid_at` and
  `invalid_at` timestamps instead of overwriting — enabling temporal reasoning
  and knowledge updates without losing history.

Sources: arXiv 2506.06326 / 2507.03724, roborhythms.com, everydev.ai.
*Content was rephrased for compliance with licensing restrictions.*

## How FRIDAY Already Uses It

FRIDAY's memory system was DESIGNED from the Memory OS blueprint (ADR
references). We have 4 tiers:
- Working (volatile session) ← Memory OS short-term
- Episodic (interaction history) ← Memory OS episodic
- Procedural (learned patterns) ← Memory OS procedural
- Semantic (facts + embeddings) ← Memory OS semantic + vector layer

Our `MemoryStore` interface mirrors the "memory as manageable resource" idea
and allows backend swapping (JSON → Qdrant → cloud).

## Gap Analysis — What We're Missing

| Memory OS feature | FRIDAY status |
|-------------------|---------------|
| Layered tiers | ✅ Have 4 tiers |
| Vector/semantic recall | ✅ NVIDIA embeddings |
| Backend abstraction | ✅ MemoryStore interface |
| **Temporal edges (valid_at/invalid_at)** | ❌ We overwrite facts |
| User profile auto-build | ⚠ Partial (preference category) |
| Surgical context injection | ⚠ Basic (get_context) |
| Consolidation/curation | ❌ Not yet |

## Recommendation

**Adopt the temporal edges concept now** — it's the highest-value, lowest-cost
improvement and requires no external dependency:

1. Add `valid_at` and `invalid_at` (nullable) to `Fact` in `semantic.py`.
2. On "forget"/update, set `invalid_at` instead of deleting — preserves history.
3. Filter retrieval by temporal validity (default: currently-valid facts).
4. Enables: "what did I believe last week?" and clean knowledge updates.

**Defer**: Qdrant backend (only when JSON scale becomes a problem — gated by
MemoryStore interface), consolidation/curation (post-v1).

**Do NOT** copy Memory OS wholesale — our blueprint usage is already correct.
The temporal-edge upgrade is the one concrete win to schedule.

**Priority**: HIGH for temporal edges (small, isolated change to semantic tier).
