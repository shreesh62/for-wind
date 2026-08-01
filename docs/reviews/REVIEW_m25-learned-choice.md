# After-Milestone Review — M25 Learned Choice & Preference Resolution

> Governance gate. Implements **A2.15 Learned Choice & Preference Resolution** —
> the first post-v2.1 amendment (previously *planned* in the v2.1 traceability
> matrix). Introduces `friday/deliberation/decision_point.py` (`DecisionPoint`
> frozen dataclass: fail-fast construction, JSON round-trip, no application-specific
> fields) and `friday/deliberation/preference_resolver.py` (`PreferenceResolver`:
> full pipeline Detect → Query → Evaluate → Gate → Apply/Infer/Ask → Verify →
> Learn; `compute_preference_confidence` — pure, evidence-only, never
> LLM-asserted; `contains_secret_material` — hard security boundary, vault refs
> allowed; `attach_preference_resolver` — reusable wiring helper). Events emitted:
> `decision.required`, `decision.resolved`, `preference.learned`,
> `preference.applied`, `preference.corrected`, `preference.superseded`.
> Reversibility gating integrates A2.3 irreversibility penalties and A2.12
> `should_interrupt`. Bootstrap wiring exposes `kernel.preference_resolver` in the
> guarded path. All code additive and inert without a kernel.

## 0. Milestone under review

- Milestone: `M25 — Learned Choice & Preference Resolution`
- Target capability: FAS §A2.15 — a general-purpose Preference Resolution Pipeline
  that eliminates repeated clarification for recurring, context-identical choices.
  When FRIDAY reaches an ambiguous multi-option state, the pipeline detects the
  decision point, queries Preference Memory (M21) via the Retrieval Router (M19),
  evaluates contextual similarity + empirical confidence + freshness, and either
  applies a learned preference autonomously (when confident and safe) or escalates
  to the user (when unsure or risky).
- Summary of what M25 delivered:
  - **`DecisionPoint` frozen dataclass** (`friday/deliberation/decision_point.py`).
    Immutable representation of a recurring choice — keyed by semantic identity
    (`decision_id`), never by application name, dialog, or window handle (Axiom 15).
    Fields: `decision_id`, `goal_context`, `environment`, `options` (tuple),
    `risk` (clamped [0, 1]), `reversible`, `category`, `candidates` (tuple),
    `metadata` (dict). Fail-fast construction (empty `decision_id` or empty
    `options` → `ValueError`). Lossless `to_dict()` / `from_dict()` JSON
    round-trip. Imports only stdlib.
  - **`PreferenceResolver` pipeline coordinator**
    (`friday/deliberation/preference_resolver.py`). Full pipeline:
    Detect → Understand semantics → Determine context → Query Preference Memory
    via Retrieval Router → Evaluate contextual similarity + confidence + freshness
    → If confident & safe: apply automatically | Else if safely inferable: infer &
    verify | Else: ask user → Execute → Verify → Determine reusability →
    Store/update preference if appropriate. Emits lifecycle events on the kernel
    bus (`decision.required`, `decision.resolved`, `preference.learned`,
    `preference.applied`, `preference.corrected`, `preference.superseded`).
    Handlers never raise into the bus.
  - **`compute_preference_confidence`** — pure, deterministic function computing
    empirical confidence in [0, 1] from evidence only (source type, reuse count,
    correction count, recency, contradictions). Never LLM-asserted (Property 4 /
    the 4th law).
  - **`contains_secret_material`** — heuristic filter enforcing the hard security
    boundary: known token prefixes (`sk-`, `ghp_`, `gho_`, `glpat-`, `xoxb-`,
    `xoxp-`), high-entropy base64 blocks ≥ 20 chars, PEM markers are all rejected.
    Vault references (`vault://...`) explicitly allowed (opaque identity refs).
  - **Reversibility gating** — integrates A2.3 irreversibility/safety penalties
    (from Expanded Deliberation) and A2.12 `should_interrupt` (from Cognitive State
    Manager). Low-risk + reversible + high-confidence → autonomous apply;
    irreversible/consequential/security-sensitive → require confirmation; user
    deeply focused + low urgency → defer non-critical questions.
  - **Event emission** — six lifecycle events, all JSON-serializable, all carrying
    sufficient context for replay (decision key, context, resolved option,
    confidence, provenance, timestamp). Replay-safe for the append-only EventStore.
  - **Bootstrap wiring** (`friday/api/server.py`). Within the guarded
    `FRIDAY_USE_KERNEL_EXECUTION=1` block, `attach_preference_resolver` constructs
    and attaches the resolver, wires it to Preference Memory, Retrieval Router,
    Cognitive State Manager, and Failure Memory, and exposes it as
    `kernel.preference_resolver`. Additive; default (flag-off) path byte-unchanged;
    wiring failure logged with structured context, never crashes bootstrap.
  - **Additive PreferenceRecord fields** (`friday/memory/preference_memory.py`).
    Eight fields added with safe defaults (context_scope, preference_class,
    confidence, reuse_count, last_verified, corrections, superseded_by,
    provenance) — existing usage unchanged.

## 1. Regression safety (automated)

- Full-suite checkpoint (established gate command, from repo root):
  `python -m pytest tests -q` → **1707 passed, 0 failed**. Total collected
  **1707** = prior baseline + the **24** new M25 tests
  (`tests/friday/test_m25_learned_choice.py`), so the M25 tests are confirmed
  included and the zero-failure checkpoint is satisfied.
- **A8 kernel throughput benchmark green.** The M1 benchmark
  `tests/kernel/test_kernel.py::TestBenchmark::test_a8_100_ticks_per_second_sustained`
  passed — **1 passed in 5.70s** — confirming the ≥100 ticks/sec architectural
  threshold holds with no timing flake.
- **No production default changed.** The resolver is attached only in the guarded
  `FRIDAY_USE_KERNEL_EXECUTION=1` bootstrap; it is inert without a kernel and
  hermetic tests perform no unbidden disk I/O or bus subscriptions (all
  collaborators are duck-typed fakes). Rollback = leave the flag off
  (byte-unchanged default path).

## 2. Architecture compliance

- **General mechanism (Axiom 15, no application-specific logic).** `DecisionPoint`
  is keyed by semantic `decision_id` and contextual scope — never by application
  name, window handle, dialog identity, site, or URL. Neither the detection logic
  nor the resolution logic contains conditional branches based on specific
  application identifiers. Works equally for profile selection, download paths,
  default apps, device choices, template preferences, permission grants, etc.
- **Reuses Preference Memory + Retrieval Router (no new persistence).** The pipeline
  queries Preference Memory via the existing Retrieval Router (M19) — no direct
  store bypass, no parallel retrieval mechanism, no duplicate persistence. All
  reads go through `route(query, tiers={PREFERENCE})`.
- **Credential separation (identity refs only, secret material rejected —
  Property 6).** `contains_secret_material` is a hard security boundary. Secret
  material is never stored in preference memory, events, logs, or bus payloads.
  Vault references (`vault://...`) are allowed as opaque identity pointers.
- **Empirical confidence (never LLM-asserted — Property 4).**
  `compute_preference_confidence` is a pure, deterministic function of evidence
  signals only. The 4th law (Ch 28.20) is preserved: confidence is derived from
  empirical data, never self-reported by an LLM.
- **Proposes then learns (not self-deciding without verification).** The pipeline
  resolves and verifies outcomes before persisting learned preferences. Failure in
  verification → confidence reduction + escalation on next occurrence. The resolver
  never self-promotes a preference without evidence.
- **Additive / kernel-guarded wiring.** `attach_preference_resolver` wires in the
  guarded path only; the flag-off path is byte-unchanged; wiring failure is logged,
  never crashes. Existing test suite green with zero new flaky tests.
- **Event-driven + replay-safe.** All six lifecycle events are JSON-serializable,
  published via `make_event` with source `"preference_resolver"`, and carry replay
  fields (decision key, context, option, confidence, provenance, timestamp). The
  append-only EventStore stays replay-compatible.

## 3. Requirements coverage

| Req | Requirement | How satisfied | Validating tests / properties |
|---|---|---|---|
| 1 | DecisionPoint representation (semantic identity, options, context, risk, reversibility, JSON round-trip, fail-fast) | Frozen dataclass with all fields; `to_dict`/`from_dict`; `ValueError` on invalid construction | **Property 1** |
| 2 | Decision detection (ambiguous state recognition, `decision.required` event, no app-specific logic) | Pipeline entry emits `decision.required`; detection based on structural choice properties | **Property 7**, Scenario A |
| 3 | Preference resolution pipeline (full Detect→Query→Evaluate→Gate→Apply/Infer/Ask→Verify→Learn) | `resolve_sync` implements all stages; queries via Retrieval Router; verifies outcomes | **Property 8**, Scenarios A/B/C |
| 4 | Contextual scoping + precedence hierarchy (strict ordering, explicit instruction overrides, similarity threshold) | `_evaluate_candidates` enforces precedence; similarity gating with configurable threshold | **Property 2**, **Property 3**, Scenarios C/D |
| 5 | Preference lifecycle (learn/apply/correct/supersede; preference classes; empirical confidence; provenance) | Full lifecycle methods + additive PreferenceRecord fields; confidence from evidence only | **Property 4**, **Property 10**, Scenarios D/E |
| 6 | Reversibility-gated asking (autonomous when safe, confirm when risky, integrate A2.3 + A2.12) | `_gate_decision` integrates irreversibility scoring + `should_interrupt` | **Property 5**, Scenario F |
| 7 | Credential separation (identity refs only, secret material rejected, vault refs allowed) | `contains_secret_material` hard boundary; `credential-reference` class stores key only | **Property 6**, Scenario G |
| 8 | Explainability + provenance (full audit trail on automatic choices) | `explain(decision_id)` returns source, timestamp, context, confidence, reuse, corrections, last_verified | **Property 10**, Scenario H |
| 9 | General mechanism — no application-specific logic (Axiom 15) | All modules generic; `decision_id` semantic-only; no app/site/dialog identity anywhere | Structural (code review); all properties generic |
| 10 | Event-driven + replay-safe (six lifecycle events, JSON-serializable, replay fields) | `make_event` + JSON-safe payloads; defensive handlers never raise | **Property 7**, **Property 9** |
| 11 | Additive, safe integration (opt-in wiring, flag-off unchanged, suite green) | Guarded bootstrap; inert without kernel; 1707 passed, 0 failed | Full-suite checkpoint (§1) |
| 12 | Verification artifacts (property tests, acceptance scenarios, FAS/matrix update, review) | 10 properties + 8 scenarios + docs update + this review | §5, §6, this document |

## 4. Benchmark results

**No new benchmark.** A2.15 is a *pipeline coordinator*, not a measured capability —
it integrates existing subsystems (Preference Memory, Retrieval Router, Deliberation,
Cognitive State) into a resolution workflow; it produces no scored output of its own.
Consistent with the M17 / M19 / M20 / M22 / M24 coordinator policy, no benchmark is
introduced and **the 5-domain competence scorecard is unchanged**. The existing
capability benchmarks remain the scorecard.

## 5. Verification

- **Full-suite checkpoint:** `python -m pytest tests -q` → **1707 passed, 0 failed**.
  The M25 tests (24 tests in `tests/friday/test_m25_learned_choice.py`) are confirmed
  included in the total.
- **M25 property tests (Properties 1–10 + acceptance scenarios A–H) green:** all 24
  tests passed in 4.51s — Property 1 (DecisionPoint round-trip + fail-fast),
  Property 2 (precedence hierarchy), Property 3 (contextual scope gating),
  Property 4 (confidence determinism + bounds + monotonicity), Property 5
  (reversibility gating + should_interrupt), Property 6 (secret-material rejection),
  Property 7 (event JSON round-trip), Property 8 (pipeline idempotence), Property 9
  (defensive handlers), Property 10 (provenance completeness), plus acceptance
  scenarios A through H.
- **A8 throughput green:** 1 passed in 5.70s — the ≥100 ticks/sec architectural
  threshold holds.
- **Diagnostics:** doc files checked after writing; no diagnostics reported.

## 6. Traceability

- **A2.15 Learned Choice & Preference Resolution: planned → Built (first post-v2.1
  milestone).**
  - `docs/architecture/FAS_v2.1_AMENDMENTS.md` — A2.15 code-state line updated from
    "planned — all required foundations exist…" to "M25 — built" pointing at
    `friday/deliberation/decision_point.py` (`DecisionPoint`) and
    `friday/deliberation/preference_resolver.py` (`PreferenceResolver` +
    `compute_preference_confidence` + `contains_secret_material` +
    `attach_preference_resolver`), wired as `kernel.preference_resolver` in the
    guarded bootstrap. Note: "Was **planned**; this is the first post-v2.1 milestone."
  - `docs/architecture/TRACEABILITY_MATRIX_v2.1.md` — A2.15 row added as **Built**
    (M25 done). Summary prose updated to note A2.15 is built (first post-v2.1
    milestone).
- FAS reference: Ch 10/14/36; v2.1 amendment A2.15. No application-specific logic
  (Axiom 15); reuses Preference Memory + Retrieval Router (no new persistence);
  credential separation enforced (identity refs only); empirical confidence only
  (never LLM-asserted — the 4th law); event-driven + replay-safe; additive +
  kernel-guarded wiring.

## 7. Decision

- **PROCEED — zero-failure gate satisfied.** The first *post-v2.1* amendment (A2.15
  Learned Choice & Preference Resolution) is now built and verified: `DecisionPoint`
  frozen dataclass (fail-fast, JSON round-trip, no app-specific fields),
  `PreferenceResolver` (full pipeline coordinator integrating Preference Memory,
  Retrieval Router, Deliberation, Cognitive State, and Failure Memory),
  `compute_preference_confidence` (pure, evidence-only, never LLM-asserted),
  `contains_secret_material` (hard security boundary), six lifecycle events
  (replay-safe), and reversibility gating (A2.3 + A2.12 integration). All **1707
  tests pass** (0 failed); the 24 M25 property/scenario tests are green and the M1
  A8 kernel throughput benchmark holds ≥100 ticks/sec.
- **No new benchmark** — A2.15 is a pipeline coordinator, not a measured capability;
  the 5-domain scorecard is unchanged.
- **A2.15 is the first post-v2.1 milestone.** The entire Architecture v2.1
  (A2.1–A2.14) was previously closed; A2.15 extends the architecture with a new
  amendment that builds on all existing foundations.
- **Working tree left uncommitted for user review.** No commit was made; changes
  remain in the working tree for inspection.
- Recommended next: integrate the resolution pipeline into the planner/executor path
  so `DecisionPoint` detection activates automatically when ambiguous multi-option
  states are encountered during live execution.

Reviewer / date: FRIDAY orchestrator, M25 close-out.
