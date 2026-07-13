# Implementation Plan: M17 — Long-Horizon Synthesis Competence

## Overview

M17 is a small, surgical, additive change to the deterministic fallback planner and
requirements discovery. The executor data-flow and source-URL citation are **already
correct** (design C3/C4) — no change is made to `executor.py` or `evidence_law.py`.

Two production files change:
- `friday/planner/operator_planner.py::_generic_capabilities` — PRIMARY structural
  invariant (`needs_info and needs_file ⇒ needs_content = True`) plus a COMPLEMENTARY
  keyword broadening.
- `friday/planner/requirements.py` — `_fallback` keyword broadening plus a shared
  `_ensure_produce_requirement` helper wired into both `_fallback` and
  `_augment_structural`.

All new tests go in new files (Req 5.5), run without live network/model calls
(`model_router=None` / mocked, Req 6.4), and are deterministic/replay-safe. Property
tests use Hypothesis with ≥100 examples, tagged
`# Feature: m17-long-horizon-synthesis, Property N: ...`. The task order is
test-driven and dependency-ordered; same-file edits are serialized into one task each.

**Language:** Python (matches the existing codebase and design).

## Tasks

- [x] 1. Baseline verification (no code change)
  - Run `$env:PYTHONPATH="C:\Projects\JARVIS\for wind"; python -m pytest tests/friday/ tests/world/ -q` and confirm 1322 tests pass before any change.
  - Confirm in `friday/planner/operator_planner.py::_generic_capabilities` the append order is `SEARCH_WEB`/`EXTRACT_WEB_CONTENT` (needs_info) → `NAVIGATE_URL` → `GENERATE_TEXT` (needs_content) → `CREATE_FILE` (needs_file) → `SEND_MESSAGE`, so setting `needs_content=True` lands `GENERATE_TEXT` after gather and before `CREATE_FILE` with no reordering.
  - Confirm `friday/verification/evidence_law.py::classify_requirement` token order is DELIVER → GATHER → FILE → PRODUCE (the wording of the injected requirement must avoid the earlier tokens).
  - Confirm `friday/executor.py::_dispatch_create_file` prefers `ctx.generated_content or ctx.combined_info`, and `_generate` injects `SOURCE_URL` citations into the synthesis prompt (documents C3/C4 as already-correct; no change).
  - _Requirements: 5.5, 6.1, 6.2; Design C1, C3, C4_

- [x] 2. Planner: PRIMARY invariant + COMPLEMENTARY keyword broadening
  - [x] 2.1 Modify `_generic_capabilities` in `friday/planner/operator_planner.py`
    - Extend the `needs_content` keyword list with synthesis verbs/nouns: `"produce"`, `"summariz"`, `"document"`, `"paper"`, `"cite"`, `"citation"`, `"essay"`, `"brief"` (retain existing keywords).
    - After the five `needs_*` booleans are computed and BEFORE the `if needs_info:` append block, add the PRIMARY invariant: `if needs_info and needs_file: needs_content = True` with an Axiom-15 comment (general goal-shape rule, no app/site/topic branching).
    - Do not reorder the append block; `GENERATE_TEXT` must remain between gather and `CREATE_FILE`.
    - _Requirements: 1.1, 1.2, 1.5, 2.1, 2.2, 2.3; Design C1_

  - [x]* 2.2 Write property test P1 (gather+save forces ordered synthesis)
    - **Property 1: Gather + save forces an ordered synthesis step**
    - **Validates: Requirements 1.1, 1.2**
    - New file `tests/friday/test_m17_long_horizon_synthesis.py`; generate gather+save goals; assert `GENERATE_TEXT` present, indexed after last `SEARCH_WEB`/`EXTRACT_WEB_CONTENT` and before first `CREATE_FILE`. `model_router=None`, ≥100 examples.

  - [x]* 2.3 Write property test P2 (synthesis verbs need content)
    - **Property 2: Synthesis verbs classify as needing content**
    - **Validates: Requirements 2.1**
    - Embed a random Synthesis_Verb in the goal; assert `GENERATE_TEXT` present. ≥100 examples.

  - [x]* 2.4 Write property test P3 (legacy content keywords need content)
    - **Property 3: Legacy content keywords still classify as needing content**
    - **Validates: Requirements 2.2**
    - Embed a random legacy content keyword; assert `GENERATE_TEXT` present. ≥100 examples.

  - [x]* 2.5 Write property test P4 (no spurious synthesis without triggers)
    - **Property 4: No spurious synthesis without triggers**
    - **Validates: Requirements 1.3, 1.4, 2.3**
    - Pure-gather, pure-file, and neutral goals (no content/synthesis keyword, not both gather+save); assert `GENERATE_TEXT` absent. ≥100 examples.

  - [x]* 2.6 Write property test P7 (deterministic, pure planning)
    - **Property 7: Planning decision is deterministic and pure**
    - **Validates: Requirements 6.1, 6.4**
    - Two successive `_generic_capabilities` calls per goal (`model_router=None`) return identical lists; no clock/randomness/network. ≥100 examples.

  - [x]* 2.7 Write property test P8 (no regression on representative shapes)
    - **Property 8: No regression on representative plan shapes**
    - **Validates: Requirements 5.4, 5.5**
    - Representative fixed shapes: pure research → gather only; pure file-save → create-file only; research+report, gather+save+document → include `GENERATE_TEXT`.

- [x] 3. Checkpoint — planner tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Requirements: fallback broadening + shared PRODUCE-injection helper
  - [x] 4.1 Modify `friday/planner/requirements.py`
    - Broaden the `_fallback` content branch keyword list with the synthesis verbs (`"produce"`, `"summariz"`, `"document"`, `"paper"`, `"cite"`, `"citation"`, `"essay"`, `"brief"`, `"compose"`, `"draft"`) so it appends the PRODUCE-classifying `Requirement(description="Content must be produced")`.
    - Add private helper `_ensure_produce_requirement(self, goal, reqs)` that injects `Requirement(description="A written summary must be synthesized and composed", blocking=True)` when the goal has a Synthesis_Verb OR (`implies_gather` AND `implies_save`) and no PRODUCE requirement already exists. Wording deliberately avoids DELIVER/GATHER/FILE tokens (classify order DELIVER→GATHER→FILE→PRODUCE).
    - Call `_ensure_produce_requirement` from BOTH `_fallback` (before returning) and `_augment_structural` (alongside existing FILE/DELIVER injections).
    - Keep signatures of `_fallback` and `_augment_structural` unchanged.
    - _Requirements: 3.1, 3.2, 6.3; Design C2_

  - [x]* 4.2 Write property test P5 (PRODUCE requirement emitted)
    - **Property 5: Requirements discovery emits a PRODUCE requirement**
    - **Validates: Requirements 3.1, 3.2**
    - New file `tests/friday/test_m17_requirements_produce.py`; synthesis-verb goals and gather+save goals; assert both the `discover()` fallback path (`model_router=None`) and `_augment_structural` yield ≥1 requirement classifying as `RequirementKind.PRODUCE`. ≥100 examples.

  - [x]* 4.3 Write example tests for PRODUCE emission on the benchmark goal
    - Assert the exact benchmark goal ("Complete a multi-stage goal: research a topic, then produce and save a document summarizing it with citations.") yields a PRODUCE-classifying requirement on the fallback path.
    - Assert the injected description does NOT classify as GATHER/FILE/DELIVER (token-order trap avoided).
    - _Requirements: 3.1, 3.2_

- [x] 5. Checkpoint — requirements tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Evidence-Law + data-flow example/property tests (no production change)
  - [x]* 6.1 Write property test P6 (Evidence Law enforces PRODUCE via GENERATED_CONTENT only)
    - **Property 6: Evidence Law enforces PRODUCE via GENERATED_CONTENT only**
    - **Validates: Requirements 3.3, 3.4, 6.3**
    - New file `tests/friday/test_m17_evidence_dataflow.py`; toggle `GENERATED_CONTENT` evidence: present ⇒ PRODUCE satisfied AND GATHER still unmet; absent ⇒ PRODUCE unmet. In-memory `ExecutionEvidence`, no live calls. ≥100 examples.

  - [x]* 6.2 Write example test for the executor gather→generate→create_file data flow (no router)
    - **Validates: Requirements 4.1, 4.2, 4.3**
    - Deterministic executor with `model_router=None`: a `GENERATE_TEXT` step sets `ctx.generated_content` from `combined_info` and records `GENERATED_CONTENT`; a subsequent `CREATE_FILE` writes `generated_content` (not the raw gathered dump) and records `FILE_ARTIFACT`.

  - [x]* 6.3 Write example test for source-URL citation in synthesis prompt
    - **Validates: Requirements 4.4**
    - With `SOURCE_URL` evidence recorded during gather, assert `_generate` includes the gathered source URLs in the synthesis prompt (citation instruction) — mocked/no live call.

- [x] 7. Final checkpoint — full suite green, no regressions
  - Run `$env:PYTHONPATH="C:\Projects\JARVIS\for wind"; python -m pytest tests/friday/ tests/world/ -q` and confirm ≥1322 prior tests plus all new M17 tests pass.
  - Re-run the candidate-affected pre-existing tests and confirm they still pass (design expects both to pass unchanged): `tests/friday/test_requirements.py::TestRequirementsDiscovery::test_fallback_without_llm` and `tests/friday/test_query_and_spreadsheet.py::TestPlannerUsesFocusedQuery::test_fallback_search_target_is_focused`. Also re-run `tests/friday/test_executor.py`, `tests/friday/test_executor_dispatch.py`, `tests/friday/test_repair.py`, `tests/friday/test_evidence_law.py`.
  - Only update a pre-existing test if an assertion actually tightens against the corrected contract; record any such change in the change notes (Req 5.6).
  - Confirm no production default changed and no live calls were introduced.
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 5.5, 5.6, 6.2, 6.4_

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core implementation tasks (2.1, 4.1) are never optional.
- The executor (`executor.py`) and Evidence Law (`evidence_law.py`) are NOT modified — the design (C3/C4) documents them as already correct. Task 6 only adds tests proving the existing data flow and citation behavior.
- Same-file edits are serialized: `operator_planner.py` is one task (2.1), `requirements.py` is one task (4.1). New test files may be developed in parallel.
- Each property test references a specific design property (P1–P8) and the requirements clause it validates.
- Live benchmark verification (Req 5.1, 5.2, 5.4, i) and baseline/ratchet recording are performed on a real machine and recorded to `baseline.local.json` — they are NOT part of the unit suite and are not tasks here (coding-only tasks).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1"] },
    { "id": 1, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7"] },
    { "id": 2, "tasks": ["4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "6.1", "6.2", "6.3"] }
  ]
}
```
