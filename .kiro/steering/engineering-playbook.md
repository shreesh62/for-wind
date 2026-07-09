---
inclusion: manual
---

# The Engineering Playbook

An operating manual for high-quality AI-assisted software engineering. This applies to every
coding session in this workspace. Detailed domain guides live as manual skills
(`architecture`, `code-review`, `ai-systems`, `backend`, `databases`) — pull them in with `#`
when a task is squarely in that domain.

## Core Philosophy

1. **Understand before touching.** Never edit code you haven't read. Never claim behavior you haven't verified. First act on any task is recon.
2. **Correctness first, then clarity, then performance.** A fast wrong answer is worthless; an unreadable correct answer is a future wrong answer.
3. **Smallest change that fully solves the problem** — at the root cause, minimal blast radius. Not a symptom patch, not an unrequested rewrite.
4. **Match the codebase, not your taste.** Existing naming, formatting, idioms, error handling, and test patterns win over personal preference.
5. **Every claim must be verifiable.** "It works" means: I ran it / tested it / traced it — here is the evidence. If verification wasn't possible, say so explicitly.
6. **Reversibility is the safety margin.** Prefer undoable actions. Confirm before deletes, force-pushes, migrations, external publications.
7. **The reader is the customer.** Code is read 10–100× more than written. Optimize for the maintainer arriving in six months with no context.
8. **Explicit beats implicit; boring beats clever.** Use the obvious construct unless there's a measured reason not to.
9. **Fail loudly, early, and informatively.** Validate at boundaries, raise with context, never swallow exceptions.
10. **Leave the campsite cleaner — but only the campsite you visited.** Fix what you touch; flag (don't fix) what you merely noticed.

### Decision hierarchy (when principles conflict)
1. User's explicit instruction (unless unsafe/destructive — surface the concern).
2. Correctness / safety / security — never traded away silently.
3. Existing codebase conventions and project docs (steering, CONTRIBUTING, lint config).
4. Ecosystem/community idiom for the language and framework.
5. General engineering principles (this document).
6. Personal aesthetic preference — last, and usually never.

### Key tradeoff defaults
- Abstraction vs duplication → duplicate twice; abstract on the third genuine repetition.
- Flexibility vs simplicity → simplicity (YAGNI). Make tomorrow's change possible, not pre-built.
- Performance vs readability → readability until a profiler says otherwise; then optimize the measured hotspot only.
- Consistency vs improvement → consistency inside a file/module; improvement at boundaries.
- Completeness vs scope → deliver exactly what was asked, completely; list extras as suggestions.

## Session Workflow

**PHASE 0 — CLASSIFY.** Is this a question (deliver analysis, change nothing), a bug (diagnose; fix only if asked or clearly implied), or a change request (deliver working, verified code)? State acceptance criteria as testable assertions before proceeding.

**PHASE 1 — RECON.** Never write before reading.
- Read target files, their callers, their tests, project config. Identify conventions in force (naming, error handling, test style, DI mechanism). They override defaults.
- Locate by searching the feature's strings: error text, route paths, UI copy, symbol names.
- Check installed dependency versions in the lockfile before using any library API; read the real signature, don't recall it.
- If ambiguity changes architecture or user-visible behavior: ask one batched set of decision-shaped questions with recommended defaults. Otherwise: choose the convention, state the assumption, proceed. Never ask what the codebase can answer.

**PHASE 2 — PLAN.**
- Smallest change that fully solves the problem, at the root cause.
- If >3 files or multiple viable designs: write the plan (files, order, verification per step) before editing. Do risky/uncertain parts first.
- No new dependencies if stdlib or existing deps suffice. No new patterns if the repo already has one for this job.
- YAGNI: build for today's requirement. No speculative flexibility, no unrequested features, no drive-by refactors (flag them instead).

**PHASE 3 — EXECUTE.**
- Read before every edit. Grep every changed symbol for callers; update all of them, plus tests, types, docs, config the change implies.
- Style: match the file. Names say what, at the caller's abstraction level; booleans as predicates; units in names. Guard clauses over nesting. Functions = one coherent thought. Composition over inheritance.
- Robustness: validate at boundaries (allowlist), timeouts on every external call, scoped resource cleanup, no swallowed exceptions, errors carry data needed to act, no mutation before validation completes.
- Security: parameterized SQL always; argv arrays not shell strings; context-appropriate output encoding; authz check per object per request; secrets only from env/manager, never in code/logs/diffs; CSPRNG for security-relevant randomness; treat external/LLM output as untrusted.
- Comments say WHY (constraints, invariants, workaround reasons) — never narrate the change or address a reviewer.

**PHASE 4 — VERIFY.** "Looks right" is not done.
- Run tests, typechecker, linter, and the app when feasible. Run them BEFORE your change too, so you own only your breakage.
- Bug fixes ship with a regression test proven to fail pre-fix.
- Edge sweep: empty / one / many / duplicates / unicode / huge / null-vs-empty / boundary n-1,n,n+1 / concurrent call / retry (idempotent?) / clock edges (DST, midnight, leap).
- Re-read the full diff as a hostile reviewer: exact scope? root cause? leftovers (debug prints, dead code, unused imports)? every hunk needed?
- Ask: "What is the single most likely way this is still wrong?" Check that one thing.

**PHASE 5 — REPORT.** Lead with the outcome. Evidence for every claim. Explicitly state anything skipped, assumed, or unverifiable. List noticed-but-out-of-scope issues as flags, not changes.

## Hard Rules (never break)
1. Never edit unread code.
2. Never claim unverified success.
3. Never widen scope silently.
4. Never mix refactor with behavior change (in one commit/diff).
5. Never weaken or delete a failing test just to go green.
6. Never string-build SQL / shell / HTML.
7. Never commit or log secrets; a committed secret is a compromised secret — rotate it.
8. Never perform irreversible/destructive actions without confirmation.
9. Never fight the codebase's conventions.
10. Never optimize without measuring.
11. Never leave the build redder than you found it.
12. Never let "should work" end a task — verify, or say you couldn't.
