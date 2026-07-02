# FRIDAY Research Evaluations

Strategic evaluations of technologies that could influence FRIDAY's architecture.

**Principle (from Research Integration Guide)**: Do NOT integrate technologies
because they are new. Integrate only if they improve capability, reliability,
maintainability, scalability, or user experience. Avoid technology collection
syndrome.

These are EVALUATION REPORTS — not commitments to integrate.

## Reports

| # | Technology | Tier | Recommendation | Report |
|---|-----------|------|----------------|--------|
| 1 | Supermemory | 1 | Adopt as optional backend (interface-gated) | [supermemory.md](evaluations/supermemory.md) |
| 2 | Memory OS / MemOS | VERY HIGH | Already used as blueprint; adopt temporal edges idea | [memory_os.md](evaluations/memory_os.md) |
| 3 | Open Browser Use | 1 | Study patterns; do not replace existing browser stack | [open_browser_use.md](evaluations/open_browser_use.md) |
| 4 | Scrapling | 2 | Adopt for research/extraction subsystem (deferred) | [scrapling.md](evaluations/scrapling.md) |
| 5 | Local Agent Infrastructure | 1 | Architectural inspiration only | [local_agent_infra.md](evaluations/local_agent_infra.md) |

## Decision Summary

**Adopt now (low risk, high value):**
- Memory OS *temporal edges* concept (valid_at/invalid_at timestamps on facts)
  — strengthens our existing semantic tier without new dependencies.

**Adopt later (interface-gated, deferred):**
- Supermemory as an optional `MemoryStore` backend (our `interfaces.py` already
  supports backend swapping). Keep local JSON as default.
- Scrapling for a future `research/` extraction subsystem.

**Study only (no integration):**
- Open Browser Use — validate our perceive→plan→act→verify loop against theirs.
- Local Agent Infrastructure patterns — already largely aligned.

**Architectural fit**: FRIDAY's memory `interfaces.py` (MemoryStore protocol)
and `models/router.py` (provider protocol) were designed for exactly this kind
of optional, swappable integration. Nothing here requires core rewrites.
