# Implementation Plan: M13 — Production Validation & Architecture v2.1

## Overview

Two-part, review-gated milestone. **No production default changes. No new subsystem implementation.**
Deliverables are (Part 1) runnable validation tooling + evidence framework + parity report + explicit
promotion criteria + an honest readiness verdict gated on the user running the harness on a real
machine; and (Part 2) the FAS v2.1 normative amendments + traceability matrix + dependency graph +
revised roadmap. Implementation of the new subsystems resumes only after review/approval.

All tooling lives under `scripts/kernel_validation/` (non-production); all documents under
`docs/validation/` and `docs/architecture/`. Tooling tests run under `FRIDAY_DRY_RUN=1`; no real-world
results are asserted by automated tests.

**Test command:** `python -m pytest tests/friday/ -q`.

## Tasks

- [ ] 1. Validation scenario suite + evidence schema
  - [ ] 1.1 Author the scenario catalog and evidence records
    - Create `scripts/kernel_validation/__init__.py`, `scripts/kernel_validation/scenarios.py`
      (frozen `ValidationScenario`; the 18 required categories, each with `requires_live` flags), and
      `scripts/kernel_validation/evidence.py` (frozen `ValidationEvidence`, JSON-serializable)
    - _Requirements: 1.3, 1.5, 5.1_

  - [ ]* 1.2 Tests: evidence serializable, all 18 categories present, live flags set
    - **Property 3: Evidence is structured and serializable**
    - **Validates: Requirements 1.3, 1.5**

- [ ] 2. Validation runner + evidence collector
  - [ ] 2.1 Implement the dual-path runner and collector
    - Create `scripts/kernel_validation/runner.py`: run each scenario on legacy + kernel paths with
      identical goal text, restore `FRIDAY_USE_KERNEL_EXECUTION` and bridge state after each run,
      record a `ValidationEvidence` per path; SKIP `requires_live` scenarios under `FRIDAY_DRY_RUN`
    - Subscribe an evidence collector to the kernel bus for event logs / goal transitions / timings
    - _Requirements: 1.1, 1.2, 1.4_

  - [ ]* 2.2 Tests: no default mutation, identical workload, live-skip
    - **Property 1: Validation runner changes no production default**
    - **Property 2: Identical workload on both paths**
    - **Property 4: Live-only scenarios skipped safely in DRY_RUN**
    - **Validates: Requirements 1.1, 1.2, 1.4**

- [ ] 3. Parity report generator
  - [ ] 3.1 Implement the report generator
    - Create `scripts/kernel_validation/report.py`: compare legacy vs kernel across behavior /
      correctness / reliability / performance / recovery / determinism; emit Markdown + a
      machine-readable summary; deterministic for identical evidence
    - _Requirements: 2.1_

  - [ ]* 3.2 Test: deterministic report
    - **Property 5: Parity report is deterministic for deterministic inputs**
    - **Validates: Requirements 2.1**

- [ ] 4. Validation plan + promotion criteria + readiness verdict (documents)
  - [ ] 4.1 Author the validation plan and explicit promotion criteria
    - Create `docs/validation/KERNEL_PRODUCTION_VALIDATION_PLAN.md`: how to run the harness on a real
      machine, the evidence schema, and the explicit, measurable promotion criteria (all must pass)
    - _Requirements: 2.2_

  - [ ] 4.2 Author the readiness verdict (honestly gated)
    - Create `docs/validation/KERNEL_READINESS_VERDICT.md`: current verdict = NOT-YET-QUALIFIED because
      real-world runs require the user's machine; enumerate exactly what is outstanding; include the
      rollback strategy + single-isolated-commit flip plan to be executed ONLY after criteria pass
    - _Requirements: 2.3, 2.4_

- [ ] 5. Architecture v2.1 normative amendments (document)
  - [ ] 5.1 Author the FAS v2.1 amendments
    - Create `docs/architecture/FAS_v2.1_AMENDMENTS.md` with normative sections for ALL twelve concept
      areas (World Model freshness/provenance; Environment Intelligence; Deliberation utility + recovery
      contracts; Capability lifecycle + statistical competence; Skill Evolution; Resource Manager;
      Retrieval Router; Exploration Engine; Statistical Evaluation; layered Reflection; seven-tier
      Memory; Cognitive State Manager), each cross-referencing existing FAS chapters + code state,
      preserving the one-Kernel/one-World-Model/one-Goal-Graph/one-Competence-Model invariants
    - _Requirements: 3.1, 3.2, 3.3_

- [ ] 6. Traceability, dependency graph, revised roadmap (documents)
  - [ ] 6.1 Author the traceability matrix
    - Create `docs/architecture/TRACEABILITY_MATRIX_v2.1.md`: concept → FAS chapter(s) → code state
      (built/partial/absent) → owning milestone
    - _Requirements: 4.1_

  - [ ] 6.2 Author the dependency graph + revised roadmap
    - Create `docs/architecture/ROADMAP_v2.1.md`: build-order DAG among new/expanded subsystems,
      affected-milestone analysis, recommended implementation order + rationale; explicitly state that
      implementation resumes only after approval and that NO subsystem was implemented in M13
    - _Requirements: 4.2, 4.3, 4.4_

- [ ] 7. Final checkpoint
  - [ ] 7.1 Run the full suite and confirm green; confirm no production change
    - Run `python -m pytest tests/friday/ -q`; confirm ≥ 1227 pre-existing tests plus M13 tooling tests
      pass; confirm no production default changed and no new subsystem implemented
    - _Requirements: 4.4, 5.2_

## Notes

- Tasks marked `*` are tooling tests.
- STRICT: no edits to production execution defaults; no implementation of the v2.1 subsystems. M13 is
  validation tooling + planning + architecture documents, stopping at the review/approval gate.
- The readiness verdict must be honest: real browser/desktop/network/GPU runs cannot execute in this
  sandbox (`FRIDAY_DRY_RUN`), so the verdict is gated on the user running the harness. No fabricated
  results.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "5.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "6.1"] },
    { "id": 3, "tasks": ["3.2", "4.1", "6.2"] },
    { "id": 4, "tasks": ["4.2", "7.1"] }
  ]
}
```
