---
inclusion: manual
---

# Skill: Code Review

## Posture
Review the diff as a hostile-but-fair senior maintainer. Verify claims against the code, not the description. Rank findings by severity; report only what survives verification — a plausible-sounding non-bug erodes trust.

## Pass 1 — Intent
- Does the diff do exactly what it claims — all of it, nothing extra?
- Root cause or symptom patch? Right layer for the fix?
- Any unrelated hunks (drive-by refactors, reformatting)? → split out.

## Pass 2 — Correctness (trace, don't skim)
- Simulate the main path with a concrete input, line by line.
- Simulate the unhappy paths: empty/null input, callee throws, timeout, partial completion mid-way — what state remains?
- Off-by-one audit: every loop bound, slice, `<` vs `<=`.
- Resources released on ALL paths including exceptions?
- Concurrency: two interleaved invocations on the same entity — safe? Retried — idempotent? Check-then-act races?
- Silent failure modes: what could go wrong here *without throwing*?

## Pass 3 — Contracts & Blast Radius
- Grep every changed symbol: all callers updated? Mocks/overrides/docs too?
- Error types/messages that callers match on preserved?
- Anything persisted or on the wire changed (schema, format, API)? Migration path? Backward compatibility for in-flight data and N-1 clients?

## Pass 4 — Security Taint Walk
- Untrusted data: validated at entry (allowlist), parameterized into sinks, encoded at exits?
- New endpoint/resource access: authn + per-object authz + rate limits?
- Secrets in code/logs/errors? High-entropy strings in the diff?

## Pass 5 — Tests
- Do new tests fail if the new code is broken? (Mentally mutate the code.)
- Bug fix → regression test proven to fail pre-fix?
- Tests assert outcomes, not implementation details? Hermetic and deterministic?

## Pass 6 — Quality
- Names still accurate after the change? (Stale names are bugs.)
- Dead code, debug prints, commented-out blocks, unused imports gone?
- Comments say why and are still true? No reviewer-directed narration ("fixed the bug")?
- Consistent with the file's existing conventions?
- Every abstraction introduced paid for by a present need?

## Reporting Findings
- Each finding: file:line, one-sentence defect statement, concrete failure scenario (inputs/state → wrong outcome). Severity order. Distinguish CONFIRMED (traced/verified) from PLAUSIBLE (couldn't fully verify).
- Blocking (correctness, security, data loss) vs non-blocking (style, nit) clearly separated. Nits don't gate merges.
- The final question before approving: **"What is the single most likely way this is still wrong?"** — go check that one thing.
