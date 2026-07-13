# Requirements Document

## Introduction

M17 — Long-Horizon Synthesis moves a **measured** capability: the `long_horizon`
benchmark domain currently scores **0.0** and must rise after this milestone. The
single benchmark `long_horizon.research_to_document` (goal: "Complete a multi-stage
goal: research a topic, then produce and save a document summarizing it with
citations.") requires four evidence kinds — `GATHERED_INFO`, `SOURCE_URL`,
`GENERATED_CONTENT`, and `FILE_ARTIFACT`.

Live diagnosis confirms the failing kind is **`GENERATED_CONTENT`** (not
`FILE_ARTIFACT`). A live run recorded `GATHERED_INFO=13`, `SOURCE_URL=10`,
`FILE_ARTIFACT=1` (8863 bytes), and `GENERATED_CONTENT=0`, producing a score of 0.0.
The root cause is in the deterministic fallback planner: `OperatorPlanner.
_generic_capabilities` gates the content-synthesis (`GENERATE_TEXT`) step on a
`needs_content` keyword list that the goal's words ("produce", "summarizing",
"document") do not match. As a result no synthesis step is planned; the plan runs
`SEARCH_WEB → EXTRACT_WEB_CONTENT → CREATE_FILE → VERIFY`, the file is written from
raw gathered text with no synthesis, and `GENERATED_CONTENT` is never recorded.

A secondary defect masks the failure: `RequirementsDiscovery` (`_fallback` and
`_augment_structural`) also misses these words, so no `PRODUCE` requirement is
emitted; the Operator therefore self-reports `completed=True` with all requirements
met (a false-complete), and no per-requirement repair fires. (This is masking, not
the scoring cause — the benchmark scorer reads evidence directly.) The run had
degraded to the non-LLM fallback path, which is why the deterministic keyword gap
was hit.

M17 fixes this with a **general planning mechanism**, not keyword patching. The
primary fix is a structural planning invariant: a plan that both gathers information
and saves an output SHALL include a content-synthesis step between them, because
saving "a document summarizing X" is impossible without first synthesizing the
summary. Keyword/verb broadening and the requirements-discovery fix are complementary
robustness improvements. The end state: on a real machine the benchmark produces all
four evidence kinds and the `long_horizon` domain score rises above 0.0, recorded to
`baseline.local.json`, with no regression to other domains (ratchet PASS).

## Glossary

- **Operator_Planner**: The `friday/planner/operator_planner.py::OperatorPlanner`
  component that converts a goal into an ordered `OperatorPlan` of capability steps.
- **Generic_Capabilities**: The deterministic fallback method
  `OperatorPlanner._generic_capabilities`, used when the LLM decomposition path is
  unavailable or degraded. It infers capabilities from the structural shape of a goal.
- **Requirements_Discovery**: The `friday/planner/requirements.py::
  RequirementsDiscovery` component that determines what must be true for a goal to be
  complete, driving the Evidence Law.
- **Evidence_Law**: The `friday/verification/evidence_law.py` mechanism that marks a
  requirement satisfied only when a matching evidence artifact exists.
- **Gather_Step**: A plan step whose capability collects information from external
  sources — `SEARCH_WEB` or `EXTRACT_WEB_CONTENT`.
- **Synthesis_Step**: A plan step whose capability is `GENERATE_TEXT`, producing
  synthesized content.
- **Save_Step**: A plan step whose capability is `CREATE_FILE`, writing output to
  disk.
- **PRODUCE_Requirement**: A `Requirement` classified by `Evidence_Law.
  classify_requirement` as `RequirementKind.PRODUCE`, demanding
  `GENERATED_CONTENT` evidence.
- **GENERATED_CONTENT**: The `EvidenceKind.GENERATED_CONTENT` artifact — synthesized
  text with a character count greater than zero.
- **FILE_ARTIFACT**: The `EvidenceKind.FILE_ARTIFACT` artifact — a file on disk with
  byte size greater than zero.
- **Gather_Save_Goal**: A goal whose structural shape requires both gathering
  information and saving an output to a file.
- **Synthesis_Verb**: A word indicating content synthesis, including "produce",
  "summariz", "document", "paper", "cite", "citation", "essay", and "brief".
- **Ratchet**: The `friday/benchmarks/capability/ratchet.py` regression gate that
  compares per-domain scores against recorded baselines.
- **Axiom_15**: The general-over-specific invariant — mechanisms must be general
  planning rules, never application-, site-, or topic-specific logic.

## Requirements

### Requirement 1: Structural gather-plus-save-implies-synthesize invariant (PRIMARY)

**User Story:** As a benchmark operator, I want any plan that both gathers
information and saves an output to include a synthesis step between them, so that a
document "summarizing" gathered research is actually synthesized and
`GENERATED_CONTENT` evidence is produced.

#### Acceptance Criteria

1. WHERE a goal's inferred capabilities include both a Gather_Step and a Save_Step,
   THE Generic_Capabilities SHALL include a Synthesis_Step in the resulting
   capability list.
2. WHERE a Synthesis_Step is included because a goal has both a Gather_Step and a
   Save_Step, THE Generic_Capabilities SHALL order the Synthesis_Step after the last
   Gather_Step and before the first Save_Step.
3. WHERE a goal's inferred capabilities include a Gather_Step but no Save_Step, THE
   Generic_Capabilities SHALL NOT insert a Synthesis_Step solely due to the
   gather-plus-save invariant.
4. WHERE a goal's inferred capabilities include a Save_Step but no Gather_Step, THE
   Generic_Capabilities SHALL NOT insert a Synthesis_Step solely due to the
   gather-plus-save invariant.
5. THE Generic_Capabilities SHALL derive the gather-plus-save-implies-synthesize
   decision solely from the goal text and inferred capabilities, using no
   application-specific, site-specific, or topic-specific branching.

### Requirement 2: Broadened synthesis detection (COMPLEMENTARY)

**User Story:** As a maintainer, I want the content-synthesis detection to recognize
common synthesis verbs and nouns, so that goals phrased with words like "produce" or
"summarizing" are classified as needing content even outside the primary structural
rule.

#### Acceptance Criteria

1. WHEN a goal text contains a Synthesis_Verb, THE Generic_Capabilities SHALL
   classify the goal as needing content and include a Synthesis_Step.
2. THE Generic_Capabilities SHALL continue to classify goals containing the existing
   content keywords ("write", "create", "generate", "summary", "report", "compose",
   "draft", "spreadsheet", "table", "list", "compare", "comparison") as needing
   content.
3. WHEN a goal text contains neither a Synthesis_Verb nor an existing content keyword
   and has no gather-plus-save shape, THE Generic_Capabilities SHALL NOT include a
   Synthesis_Step.

### Requirement 3: PRODUCE requirement emission (FALSE-COMPLETE FIX)

**User Story:** As a verification engineer, I want Requirements_Discovery to emit a
PRODUCE requirement when a goal implies producing or saving a document, so that the
Evidence_Law enforces `GENERATED_CONTENT` evidence and per-requirement repair can
trigger when content is missing.

#### Acceptance Criteria

1. WHEN Requirements_Discovery produces its fallback requirements for a goal that
   contains a Synthesis_Verb, THE Requirements_Discovery SHALL include a requirement
   that classifies as a PRODUCE_Requirement.
2. WHEN Requirements_Discovery augments a requirement set for a Gather_Save_Goal that
   lacks a PRODUCE_Requirement, THE Requirements_Discovery SHALL append a requirement
   that classifies as a PRODUCE_Requirement.
3. WHILE an execution has produced no GENERATED_CONTENT evidence, THE Evidence_Law
   SHALL classify a PRODUCE_Requirement as unmet.
4. IF a goal implies gather, save, and document production, THEN THE Evidence_Law
   SHALL mark the requirement set complete only when GENERATED_CONTENT evidence
   exists.

### Requirement 4: Data-flow correctness and citation of synthesized content

**User Story:** As a benchmark operator, I want the synthesized content to be derived
from the gathered information, to cite the gathered sources, and the saved file to
contain that synthesized content, so that both `FILE_ARTIFACT` and `GENERATED_CONTENT`
are real, mutually consistent, and grounded in the gathered evidence.

#### Acceptance Criteria

1. WHEN a Synthesis_Step executes after a Gather_Step, THE Operator_Planner SHALL
   produce the synthesized content from the gathered information.
2. WHEN a Save_Step executes after a Synthesis_Step, THE Operator_Planner SHALL write
   the synthesized content to the saved file such that the saved file content is the
   synthesized document and not a raw dump of the gathered search results.
3. WHEN a Gather_Save_Goal executes end-to-end, THE Operator_Planner SHALL record
   both a GENERATED_CONTENT artifact and a FILE_ARTIFACT artifact.
4. WHEN a Synthesis_Step produces content for a goal that gathered sources, THE
   Operator_Planner SHALL include references to the gathered source URLs in the
   synthesized content so that the content is a cited summary rather than ungrounded
   generation.

### Requirement 5: Measurable capability improvement and regression safety

**User Story:** As a governance reviewer, I want the `long_horizon` benchmark to
produce all four evidence kinds and score above 0.0 with no regressions, so that M17
demonstrably moves a measured capability.

#### Acceptance Criteria

1. WHEN `long_horizon.research_to_document` runs on a real machine, THE
   Operator_Planner SHALL produce GATHERED_INFO, SOURCE_URL, GENERATED_CONTENT, and
   FILE_ARTIFACT evidence.
2. WHEN the capability benchmarks run on a real machine after M17, THE `long_horizon`
   domain score SHALL exceed 0.0 and be recorded to `baseline.local.json`.
3. THE committed baseline seed SHALL remain all-unmeasured after M17.
4. WHEN the Ratchet evaluates the post-M17 run, THE Ratchet SHALL report PASS with no
   regression to the research, coding, browser, or desktop domains.
5. WHEN the full test suite runs after M17, THE test suite SHALL pass with no fewer
   than the 1322 tests green prior to M17, with new tests placed in new files and
   existing planner and requirements tests still passing.
6. WHERE a pre-existing test asserts the old plan shape for a Gather_Save_Goal, THE
   test SHALL be updated to the corrected contract and the update SHALL be recorded
   in the change notes.

### Requirement 6: Additive, deterministic, replay-safe behavior

**User Story:** As a maintainer, I want the M17 changes to be additive and
deterministic, so that no production default changes and tests need no live calls.

#### Acceptance Criteria

1. THE Operator_Planner SHALL derive the gather-plus-save-implies-synthesize decision
   as a pure function of the goal text and inferred capabilities, using no clock,
   randomness, or network access.
2. THE M17 changes SHALL preserve existing production defaults and public method
   signatures where behavior is not the target of the fix.
3. THE Evidence_Law SHALL remain the sole judge of requirement satisfaction, such
   that generated text satisfies a PRODUCE_Requirement but never a GATHER
   requirement.
4. WHEN the M17 tests run, THE tests SHALL exercise the planning and requirements
   logic without live network or model calls.

## Property-to-Requirement Mapping

| # | Testable Property | Type | Requirement(s) |
|---|-------------------|------|----------------|
| a | Any goal implying gather+save yields a plan with a Synthesis_Step ordered after the gather step and before the CREATE_FILE step | Invariant | 1.1, 1.2 |
| b | Broadened keyword/verb detection classifies synthesis goals as needs_content and inserts a Synthesis_Step | Metamorphic | 2.1, 2.2 |
| c | Requirements_Discovery emits a PRODUCE requirement for document/produce/summarize goals | Invariant | 3.1, 3.2 |
| d | A gather+save+document goal cannot be marked complete without GENERATED_CONTENT evidence | Invariant / Error condition | 3.3, 3.4, 6.3 |
| e | Plans for pure-research or pure-file goals are unchanged (no spurious Synthesis_Step) | Invariant | 1.3, 1.4, 2.3 |
| f | No regression to existing plan shapes; full suite green; ratchet PASS | Model-based / Regression | 5.4, 5.5, 5.6 |
| g | Synthesized content derives from gathered info, is written to the saved file (not a raw dump), and cites the gathered source URLs | Data-flow / Round-trip | 4.1, 4.2, 4.3, 4.4 |
| h | The planning decision is pure over goal + capabilities (deterministic, replay-safe) | Invariant | 6.1, 6.4 |
| i | Benchmark produces all four evidence kinds; long_horizon score > 0.0; seed stays unmeasured | Measurable acceptance | 5.1, 5.2, 5.3 |
