# Architecture v2.1 — Traceability Matrix

Maps each v2.1 concept → FAS chapter(s) → current code state → owning milestone. Code state:
**Built** (implemented + tested on the kernel substrate), **Partial** (pieces exist, not fully
normative/wired), **Absent** (not yet built). No implementation occurs in M13; "owning milestone" is
the recommended future home.

| # | v2.1 Concept (amendment) | FAS Ch | Current code | State | Owning milestone |
|---|---|---|---|---|---|
| A2.1 | World Model belief freshness/TTL/refresh | Ch 9.22 | `world/belief.py`, M9 `temporal/aging.py` | Partial | M14 (World Model v2) |
| A2.1 | Belief provenance / evidence graph | Ch 9.24 | `world/belief.py` (confidence only) | Partial | M14 |
| A2.1 | Staleness handling | Ch 9.22 | M9 `KnowledgeAging.stale_items` | Partial | M14 |
| A2.2 | Environment fingerprints | Ch 23/9.23 | — | Absent | M15 (Environment Intelligence) |
| A2.2 | UI fingerprints | Ch 23 | `environments/` observation | Absent | M15 |
| A2.2 | Capability invalidation on fingerprint change | Ch 23/25 | — | Absent | M15 |
| A2.2 | Version-aware adaptation | Ch 16/28 | competence per (cap, env) | Partial | M15 |
| A2.3 | Expanded deliberation utility | Ch 10 | `deliberation/` (simpler utility) | Partial | M16 (Deliberation v2) |
| A2.3 | Action safety term | Ch 10/35 | M4 `safety/permission.py` | Partial | M16 |
| A2.3 | Recovery contracts (undo/rollback/compensation) | Ch 34 | M11 `evolution/rollback.py` (capability-level) | Partial | M16 |
| A2.4 | Capability lifecycle | Ch 16.21/27 | M11 `evolution/lifecycle.py` | **Built** | M11 (done) — make normative |
| A2.4 | Capability profile (version/success/deps/failures/benchmarks) | Ch 16 | M11 registry + benchmarks | **Built** | M11 (done) |
| A2.4 | Statistical competence | Ch 28 | M8 `competence/model.py` | **Built** | M8 (done) |
| A2.5 | Skill evolution pipeline | Ch 15/27 | M9 learning + M11 evolution | Partial | M17 (Skill Evolution) |
| A2.6 | Resource Manager (unified) | Ch 45-48 | M4 `resources/` (registry+scheduler) | Partial | M18 (Resource Manager v2) |
| A2.6 | Cost-aware selection / economics | Ch 48 | — | Absent | M18 |
| A2.6 | Dynamic reallocation | Ch 46 | — | Absent | M18 |
| A2.7 | Retrieval Router | Ch 14.13 | ad hoc retrieval | Absent | M19 (Retrieval Router) |
| A2.8 | Exploration Engine | Ch 25/66 | M7 `environments/unknown/` | **Built** | M7 (done) — make normative |
| A2.9 | Statistical evaluation / scoring | Ch 28 | M8/M11 competence | **Built** | M8/M11 (done) |
| A2.10 | Layered reflection (5 layers) | Ch 13 | M8 reflection engine | Partial | M20 (Reflection v2) |
| A2.11 | Seven-tier memory | Ch 14/50 | M8 (4 tiers) | Partial | M21 (Memory v2) |
| A2.11 | Failure memory | Ch 14 | — | Absent | M21 |
| A2.12 | Cognitive State Manager | Ch 67 | M4 `cognition/state.py` (partial) | Partial | M22 (Cognitive State) |

## Summary by state

- **Built / normative-ready (no new build, just spec ratification):** A2.4 lifecycle + profile, A2.4/
  A2.9 statistical competence, A2.8 exploration. These are already implemented and tested; v2.1 only
  elevates them to normative FAS status.
- **Partial (expand + wire):** A2.1 World Model freshness/provenance, A2.3 deliberation utility +
  recovery contracts, A2.5 skill pipeline, A2.6 resource manager, A2.10 layered reflection, A2.11
  seven-tier memory, A2.12 cognitive state.
- **Absent (new build):** A2.2 environment intelligence, A2.6 economics/reallocation, A2.7 retrieval
  router, A2.11 failure memory.
