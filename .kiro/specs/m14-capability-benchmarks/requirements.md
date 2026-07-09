# Requirements Document

M14 — Capability Benchmarks & Competence Ratchet

## Introduction

Before implementing the v2.1 subsystems, M14 builds the ability to **measure** FRIDAY's demonstrated
competence across the five domains named by the maintainer — browser operation, desktop operation,
research, coding, and long-horizon execution — and enforces a **competence ratchet**: no milestone may
regress a measured capability. This operationalizes the governance rule "every milestone must improve a
measurable capability rather than simply adding components," and establishes the after-every-milestone
review protocol (run benchmarks → architecture review → verify no regression → continue). Benchmarks
are capability-based, evidence-scored (via the Evidence Law, never LLM self-report), and domain-general
(no application-specific logic, Axiom 15). Real scores are produced only on a real machine; the sandbox
fabricates none.

## Glossary

- **Capability benchmark**: a realistic goal with a measurable, evidence-based acceptance criterion.
- **Domain score**: weighted `[0,1]` pass ratio for one domain (browser/desktop/research/coding/
  long_horizon).
- **Evidence-based scoring**: a benchmark passes iff the required `EvidenceKind` artifacts are present;
  generated text alone never passes a gather/deliver/file benchmark.
- **Competence ratchet**: persisted per-domain baselines + a gate that fails on regression below
  baseline − tolerance.
- **Measured / unmeasured baseline**: a baseline is `measured` only after a real run records it;
  unmeasured baselines block nothing.
- **After-milestone review**: the repeatable protocol every future milestone completes before work
  continues.

## Requirements

### Requirement 1: Measurable capability benchmarks for five domains

**User Story:** As the maintainer, I want objective, evidence-based benchmarks for browser, desktop,
research, coding, and long-horizon execution, so competence is measured, not asserted.

#### Acceptance Criteria

1. WHEN the benchmark catalog is defined THEN it SHALL include at least one `CapabilityBenchmark` for
   each of: browser, desktop, research, coding, long_horizon — each with a measurable acceptance
   criterion and the required evidence that proves it.
2. WHEN a benchmark is scored THEN it SHALL pass ONLY if every `required_evidence` kind is present in
   the execution's `ExecutionEvidence` (Evidence Law is the judge).
3. WHEN a benchmark lacks its required evidence THEN it SHALL score FAIL regardless of any generated
   text (no false competence).
4. WHEN a domain is scored THEN the score SHALL be a weighted `[0,1]` pass ratio (0.0 when empty),
   deterministic for deterministic inputs.
5. WHEN benchmark definitions are scanned THEN they SHALL contain no banned application/site name and
   no URL scheme literal (Axiom 15) — benchmarks measure capability, not a specific application.

### Requirement 2: Competence ratchet (must-improve gate)

**User Story:** As the maintainer, I want a gate that fails when a milestone regresses a measured
capability, so competence only moves forward.

#### Acceptance Criteria

1. WHEN new domain scores are checked THEN the ratchet SHALL return `passed=False` iff some MEASURED
   domain's new score is below its baseline − tolerance.
2. WHEN a new score is equal to or greater than the baseline THEN the ratchet SHALL pass for that
   domain and MAY record the improvement.
3. WHEN a domain's baseline is unmeasured THEN the ratchet SHALL NOT block on it (the first real run
   establishes the baseline) and SHALL NOT fabricate a score.
4. WHEN the ratchet records scores THEN it SHALL persist per-domain baselines to `baseline.json`,
   marking a domain `measured` only when a real score is supplied.

### Requirement 3: Scorecard and after-milestone review protocol

**User Story:** As the maintainer, I want a repeatable review protocol and a human-readable scorecard,
so every future milestone verifies competence before continuing.

#### Acceptance Criteria

1. WHEN a benchmark run completes THEN a `CompetenceScorecard` SHALL aggregate the five domain scores +
   the ratchet verdict + an overall (mean of measured domains).
2. WHEN M14 concludes THEN a repeatable `docs/reviews/AFTER_MILESTONE_REVIEW_TEMPLATE.md` SHALL exist
   defining the protocol: run benchmarks → produce architecture review → confirm no regression →
   continue.
3. WHEN real scores are unavailable in the sandbox THEN the scorecard/baseline SHALL be UNMEASURED and
   SHALL NOT fabricate results; real scores come only from a real-machine run.

### Requirement 4: Reuse, isolation, regression safety

**User Story:** As a maintainer, I want M14 to reuse existing primitives and stay additive.

#### Acceptance Criteria

1. WHEN M14 is implemented THEN it SHALL reuse the M11 benchmark primitives and the M8 competence model
   rather than reinventing scoring, and SHALL NOT change any production default.
2. WHEN M14 modules are added THEN each SHALL carry a `"""..."""` docstring and preserve the invariants
   (one Kernel/World Model/Goal Graph/Competence Model; general mechanisms; no app-specific logic).
3. WHEN the full suite runs under `FRIDAY_DRY_RUN=1` THEN all pre-existing tests (≥ 1234) SHALL still
   pass and M14 SHALL add benchmark-framework tests only.

## Property-to-Requirement Mapping

| Correctness Property (design.md) | Validates Requirements |
|---|---|
| P1 Evidence is the judge, never self-report | 1.2, 1.3 |
| P2 Domain score is a bounded weighted ratio | 1.4 |
| P3 Ratchet blocks regressions, allows improvements | 2.1, 2.2 |
| P4 Ratchet never fabricates baselines | 2.3, 3.3 |
| P5 All five domains are covered | 1.1 |
| P6 No application/site names in benchmark definitions | 1.5 |
