---
description: Superpowers methodology — brainstorm before building, debug systematically, execute plans with verification. Prevents the agent from rushing in and touching too many files.
---

# Superpowers

## Brainstorm Before Building

Before any creative work (features, components, new functionality, behavior changes):

1. Understand current project context (files, docs, recent commits)
2. Ask clarifying questions one at a time — understand purpose, constraints, success criteria
3. Propose 2-3 approaches with trade-offs and a recommendation
4. Present design, get user approval before implementing
5. Only then proceed to implementation

Never skip the design step. "Simple" projects are where unexamined assumptions waste the most work. The design can be brief for small tasks, but it must exist and be confirmed.

## Systematic Debugging

For ANY bug, test failure, or unexpected behavior — find root cause before attempting fixes.

**Phase 1 — Root Cause Investigation:**
- Read error messages completely (stack traces, line numbers, error codes)
- Reproduce consistently — exact steps, every time
- Check recent changes (git diff, new deps, config changes)
- Trace data flow backward to find where bad values originate

**Phase 2 — Pattern Analysis:**
- Find working examples of similar code in the codebase
- Compare working vs broken — list every difference
- Understand dependencies and assumptions

**Phase 3 — Hypothesis and Testing:**
- Form a single hypothesis: "X is the root cause because Y"
- Make the smallest possible change to test it
- One variable at a time — don't fix multiple things at once
- If it doesn't work, form a NEW hypothesis (don't pile fixes)

**Phase 4 — Implementation:**
- Create a failing test case first
- Implement a single fix addressing root cause
- Verify: test passes, no regressions
- If 3+ fixes fail, stop and question architecture with the user

**Red flags (stop and return to Phase 1):**
- "Quick fix for now, investigate later"
- "Just try changing X and see"
- "I don't fully understand but this might work"
- Proposing solutions before tracing data flow

## Executing Plans

When implementing a plan:
- Review plan critically first — raise concerns before starting
- Follow each step exactly
- Run verifications at each step
- Stop and ask when blocked — don't guess
- Never start implementation on main/master without explicit consent
