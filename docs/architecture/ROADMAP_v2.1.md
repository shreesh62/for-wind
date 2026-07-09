# Architecture v2.1 — Dependency Graph & Revised Roadmap

**Status:** planning only. **No subsystem is implemented in M13.** Implementation resumes only after
this revised architecture is reviewed and approved. Each future milestone follows the proven
discipline: additive/behind-a-flag where it touches live paths, characterization/parity nets before
any refactor, full regression green at every checkpoint.

---

## 1. What M13 did and did not do

**Did:** (Part 1) built the validation harness + evidence framework + parity report + explicit
promotion criteria, and delivered an honest, real-machine-gated readiness verdict; (Part 2) amended
the FAS to v2.1 (normative), and produced this traceability matrix + dependency graph + roadmap.

**Did NOT:** change any production default; implement any v2.1 subsystem. The kernel default remains
off pending real-machine validation (see the Readiness Verdict).

---

## 2. Dependency graph (build order among v2.1 subsystems)

```mermaid
graph TD
    PV[Production Validation\n(M13 harness → real-machine run)] --> FLIP[Kernel default flip\n(gated on C1–C8)]

    WM[M14 World Model v2\nfreshness/provenance/staleness]
    ENV[M15 Environment Intelligence\nfingerprints/invalidation]
    DEL[M16 Deliberation v2\nutility + recovery contracts]
    SKILL[M17 Skill Evolution pipeline]
    RES[M18 Resource Manager v2\neconomics/reallocation]
    RET[M19 Retrieval Router]
    REF[M20 Reflection v2\n5 layers]
    MEM[M21 Memory v2\n7 tiers + failure memory]
    COG[M22 Cognitive State Manager]

    WM --> ENV
    WM --> DEL
    WM --> RET
    MEM --> RET
    MEM --> REF
    REF --> SKILL
    RES --> DEL
    ENV --> SKILL
    DEL --> COG
    REF --> COG
    RES --> COG
```

**Reading the graph:** World Model v2 (freshness/provenance) is foundational — Environment
Intelligence, Deliberation v2, and the Retrieval Router all read richer beliefs. Memory v2 underpins
the Retrieval Router and layered Reflection. Reflection feeds the Skill pipeline. The Resource Manager
feeds Deliberation (resource cost is a utility term). The Cognitive State Manager sits on top,
coordinating focus/attention across Deliberation, Reflection, and Resources, so it comes last.

---

## 3. Affected existing milestones

| Existing | Affected by | Nature of change |
|---|---|---|
| M6 environments/verification | M15 Environment Intelligence | add fingerprints to environment contract (additive) |
| M8 reflection/memory/competence | M20 Reflection v2, M21 Memory v2 | extend layers/tiers (additive) |
| M9 temporal/learning | M14 World Model v2, M17 Skill pipeline | reuse aging precedent; formalize pipeline |
| M4 resources/safety/cognition | M18 Resource Manager, M16 recovery, M22 Cognitive State | expand to normative scope |
| M11 evolution/benchmarks | A2.4/A2.9 | already built — ratify as normative, no rebuild |
| M12 kernel execution | Production Validation → flip | validated, then default flip (isolated commit) |

No existing milestone is invalidated; all changes are additive expansions consistent with the v2.1
amendments.

---

## 4. Recommended implementation order (with rationale)

**Phase 0 — Qualify what exists (no new subsystems):**
0. **Run M13 validation on a real machine.** Produce the parity report; if C1–C8 pass, apply the
   single isolated kernel-default-flip commit with the documented rollback. *Rationale: unblock the
   architecture we already built before adding more.*

**Phase 0.5 — Measurement foundation (competence-driven development) — DONE (M14):**
0.5. **M14 Capability Benchmarks & Competence Ratchet** — measurable, evidence-scored acceptance tests
   for browser/desktop/research/coding/long-horizon; a persisted per-domain baseline + a regression
   gate; the mandatory `docs/reviews/AFTER_MILESTONE_REVIEW_TEMPLATE.md`. *Rationale (per governance
   decision): every subsequent milestone must improve a MEASURED capability, verified by real-world
   benchmarks, before continuing — so the measurement framework must exist first.* Built additive
   (1245 tests); real baselines are captured by the maintainer on a real machine (sandbox fabricates
   none). **Note the numbering: the World Model v2 milestone below is now M15, shifted by the M14
   insertion; the ordinal labels here are indicative, not literal spec ids.**

**Phase 1 — Foundations (richer reality + resources):**
1. **World Model v2** (freshness/TTL/provenance/staleness). *Rationale: everything downstream
   reasons over beliefs; make them trustworthy and explainable first. Target domain: research +
   long_horizon competence.*
2. **Resource Manager v2** (economics + dynamic reallocation). *Rationale: independent of World Model
   v2; a utility term Deliberation v2 needs; can proceed in parallel.*

**Governance (binding for every milestone from here on):** after each milestone, complete the
after-milestone review — run the capability benchmarks on a real machine, produce an architecture
review, and confirm the competence ratchet PASSES (target domain improved or held) before starting the
next milestone. A ratchet FAIL blocks continuation.

**Phase 2 — Smarter environment + decisions:**
3. **M15 Environment Intelligence** (fingerprints + capability invalidation). *Depends on M14.*
4. **M16 Deliberation v2** (expanded utility + recovery contracts). *Depends on M14 + M18.*

**Phase 3 — Retrieval + memory + reflection:**
5. **M21 Memory v2** (seven tiers + failure memory). *Depends on M8 memory.*
6. **M19 Retrieval Router.** *Depends on M14 + M21.*
7. **M20 Reflection v2** (five layers). *Depends on M21.*

**Phase 4 — Learning loop + coordination:**
8. **M17 Skill Evolution pipeline.** *Depends on M15 + M20.*
9. **M22 Cognitive State Manager.** *Depends on M16 + M18 + M20; coordinates the rest — build last.*

**Ratification (no build):** M11 lifecycle/benchmarks and M8/M11 statistical competence and M7
exploration are already implemented and tested — v2.1 elevates them to normative FAS with no new code.

---

## 5. Guardrails carried into every future milestone

- No production default flips without validation evidence + a rollback plan + a single isolated commit.
- Additive-first: new behavior behind a flag; characterization/parity nets before any refactor.
- Full regression green at every checkpoint (currently 1234 tests).
- Preserve invariants: one Kernel / World Model / Goal Graph / Competence Model; general mechanisms;
  no app-specific logic; no hardcoded workflows; evidence over assertion.

---

## 6. Approval gate

**This document set is the deliverable of M13 Part 2.** Implementation of M14+ begins only after you
review and approve: (a) the FAS v2.1 amendments, (b) this traceability matrix, and (c) this roadmap /
recommended order. Until then, no v2.1 subsystem is built and no default is changed.
