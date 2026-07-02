# Evaluation: Local LLM Agent Infrastructure

**Tier**: 1 (HIGH — architectural inspiration)
**Source**: "The infrastructure behind making local LLM agents actually useful"
(Towards Data Science) + Hermes Agent (Nous Research) patterns
**Date**: 2026-06-09
**Verdict**: Architectural inspiration only. FRIDAY already aligns with the patterns.

---

## What It Provides

Patterns for making local/agentic LLM systems actually useful in production
(rephrased for compliance). Core themes across the sources:

- **Planning systems** — decompose goals into steps, replan on failure.
- **Tool systems** — structured action vocabulary the agent can invoke.
- **Verification systems** — confirm actions achieved their intent.
- **State management** — persistent, layered memory across sessions; schedule
  recurring work; improve behavior over time (Hermes Agent model).
- **Temporal fact storage** — store facts with validity windows, don't overwrite.

Sources: towardsdatascience.com, turingpost.com (Hermes), roborhythms.com.
*Content was rephrased for compliance with licensing restrictions.*

## How FRIDAY Compares

| Infrastructure pattern | FRIDAY status |
|------------------------|---------------|
| Planning system | ✅ `planner/` (goal parser + decomposer + replanner) |
| Tool/action system | ✅ `actions/` (system, browser) with ActionResult contract |
| Verification system | ✅ `verification/` (8 strategies + evidence) |
| State management | ✅ 4-tier memory (working/episodic/procedural/semantic) |
| Replanning on failure | ✅ `replanner.py` |
| Model routing | ✅ `models/router.py` (provider-agnostic) |
| Scheduling recurring work | ⚠ Legacy `core/routine_scheduler.py` exists; not in friday/ |
| Self-improvement | 🔲 Deferred (SIA territory, post-v1) |
| Temporal facts | 🔲 Recommended via Memory OS eval |

## Key Insight

FRIDAY's architecture independently arrived at the same infrastructure the
industry converged on for useful local agents: plan → act → verify → learn,
with layered memory and provider-agnostic model routing. This is validation,
not a gap.

The notable additions worth scheduling (both already captured elsewhere):
- **Temporal facts** (see memory_os.md) — store validity windows.
- **Recurring work scheduler** — port `routine_scheduler.py` into the
  friday/ architecture so JARVIS/FRIDAY can run proactive routines.

## Recommendation

**Inspiration only — no new dependency.** Concretely:
1. Confirm our plan/act/verify/state architecture matches best practice (it does).
2. Schedule two ports/upgrades already identified:
   - Temporal facts in semantic memory (from Memory OS eval).
   - Proactive scheduler into friday/ (low priority, post core wiring).
3. Defer self-improvement (SIA) to post-v1 per the Research Integration Guide.

**Priority**: Low (validation + two small scheduled upgrades). No integration
of external code — these are patterns we already implement.
