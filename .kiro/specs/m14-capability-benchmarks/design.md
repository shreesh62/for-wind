# Design Document: M14 — Capability Benchmarks & Competence Ratchet

## Overview

The v2.1 roadmap was approved with one binding governance change: **every future milestone must
improve (or at minimum not regress) a *measured* capability, verified by real-world benchmarks, before
work continues.** Before implementing v2.1 subsystems (World Model v2, etc.), we must first be able to
*measure* FRIDAY's demonstrated competence. M14 builds that measurement foundation.

M14 delivers three things:

1. **A Capability Benchmark suite** — measurable acceptance tests for the five domains the user named:
   **browser operation, desktop operation, research, coding, and long-horizon execution.** Each
   benchmark is a realistic goal with an objective, evidence-based scorer (not a self-report), yielding
   a per-domain competence score in `[0,1]`.

2. **A Competence Ratchet** — a persisted baseline of the latest scores plus a gate that fails if a
   new run regresses a domain below its recorded baseline (minus tolerance). This operationalizes
   "every milestone must improve a measurable capability rather than simply adding components."

3. **The After-Milestone Review Protocol** — a repeatable template (`docs/reviews/`) that every future
   milestone must complete: run benchmarks → produce an architecture review → confirm competence did
   not regress → only then continue.

M14 reuses the M11 benchmark primitives (`friday/benchmarks/`: `BenchmarkScenario`, `BenchmarkRunner`,
`BenchmarkReport`, `RegressionDetector`) and the M11 competence model rather than reinventing scoring.
It adds a **capability-level** layer on top: domain suites, evidence-based scorers, baseline
persistence, and the ratchet.

**Honesty constraint (unchanged from M13):** the browser/desktop/research/coding/long-horizon
benchmarks require a real machine (live Chrome, desktop, network, model providers). This sandbox runs
under `FRIDAY_DRY_RUN=1` and cannot produce real scores. M14 therefore delivers (a) the runnable
benchmark framework + scorers + ratchet, validated by automated tests using stub evidence, and (b) a
`baseline.json` seeded as *empty/unmeasured* — real baselines are captured by the maintainer on a real
machine. M14 fabricates no competence numbers.

**Principle:** benchmarks are **capability-based** (a goal to accomplish), **evidence-scored** (via the
Evidence Law), and **domain-general** — no application-specific logic, no hardcoded workflow, no site
names (Axiom 15). A "browser operation" benchmark scores *whether real information was gathered from
real sources*, not whether a specific site was used.

---

## Architecture

```mermaid
graph TD
    subgraph M11["M11 primitives (reused)"]
        BR[BenchmarkRunner]
        REP[BenchmarkReport]
        RD[RegressionDetector]
    end

    subgraph M14["M14 capability layer (friday/benchmarks/capability/)"]
        DOM[Domain Suites\nbrowser/desktop/research/coding/long_horizon]
        SCORE[Evidence-based Scorers\nEvidence Law → [0,1]]
        RATCH[CompetenceRatchet\nbaseline.json + regression gate]
        CARD[CompetenceScorecard\nper-domain scores + verdict]
    end

    subgraph Evidence["Existing evidence + competence"]
        EV[ExecutionEvidence / EvidenceKind]
        CM[CompetenceModel (M8)]
    end

    DOM --> SCORE
    SCORE --> BR
    BR --> REP --> CARD
    SCORE -. reads .-> EV
    CARD --> RATCH
    RATCH -. records .-> CM
```

The domain suites are declarative (goals + expected evidence). A run executes each goal (on a real
machine, via the kernel or legacy path), scores it against the Evidence Law, aggregates into a
per-domain `[0,1]` score, and compares to the persisted baseline via the ratchet.

---

## How M14 Plugs Into Existing Code (real signatures)

**M11 benchmarks — `friday/benchmarks/suite.py`**
```python
class BenchmarkRunner:
    def run(self, capability_id, evaluate, suite) -> BenchmarkReport   # weighted [0,1] pass ratio
class RegressionDetector:
    def is_regression(self, incumbent, candidate, *, tolerance=0.0) -> bool
```

**Evidence Law — `friday/verification/evidence_law.py`**
```python
class ExecutionEvidence:
    def has(self, kind) -> bool
    def of_kind(self, kind) -> List[EvidenceArtifact]
class EvidenceKind(Enum): GATHERED_INFO, SOURCE_URL, GENERATED_CONTENT, FILE_ARTIFACT, DELIVERY_CONFIRMATION, ...
```

**Competence model — `friday/competence/model.py`** — the ratchet records domain outcomes here so
competence is evidence-only (never LLM self-reported).

---

## Components and Interfaces

### Component 1: Domain Benchmark Suites (`friday/benchmarks/capability/domains.py`)

**Purpose**: declarative, measurable acceptance goals for the five domains.

```python
@dataclass(frozen=True)
class CapabilityBenchmark:
    id: str
    domain: str                      # browser|desktop|research|coding|long_horizon
    goal_text: str
    required_evidence: Tuple[str, ...]  # EvidenceKind names that MUST be present to score a pass
    weight: float = 1.0
    requires_live: bool = True
    acceptance: str = ""             # human-readable measurable criterion
```

Five domain suites (`browser_suite()`, `desktop_suite()`, `research_suite()`, `coding_suite()`,
`long_horizon_suite()`), each returning `Tuple[CapabilityBenchmark, ...]`. Every benchmark states its
measurable acceptance criterion and the evidence that objectively proves it.

### Component 2: Evidence-Based Scorer (`friday/benchmarks/capability/scoring.py`)

**Purpose**: convert an execution's `ExecutionEvidence` into an objective pass/fail per benchmark, then
a weighted `[0,1]` domain score. **A benchmark passes ONLY if all its `required_evidence` kinds are
present** — the Evidence Law is the judge, not the LLM.

```python
def score_benchmark(benchmark: CapabilityBenchmark, evidence: "ExecutionEvidence") -> bool:
    """True iff every required EvidenceKind is present (real artifacts)."""

def score_domain(results: Tuple[Tuple[CapabilityBenchmark, bool], ...]) -> float:
    """Weighted pass ratio in [0,1]; 0.0 when empty; deterministic."""
```

### Component 3: CompetenceRatchet (`friday/benchmarks/capability/ratchet.py`)

**Purpose**: persist per-domain baselines and gate regressions — the "must-improve" mechanism.

```python
@dataclass(frozen=True)
class DomainScore:
    domain: str
    score: float          # [0,1]
    measured: bool        # False until a real run records it

class CompetenceRatchet:
    def __init__(self, baseline_path: str) -> None: ...
    def load(self) -> Dict[str, DomainScore]: ...
    def check(self, new_scores: Dict[str, float], *, tolerance: float = 0.05) -> "RatchetVerdict":
        """PASS iff no measured domain regressed below baseline - tolerance.
        Unmeasured baselines never block (first real run establishes them)."""
    def record(self, new_scores: Dict[str, float]) -> None:
        """Persist new baselines (only raises a baseline, or sets an unmeasured one)."""
```

```python
@dataclass(frozen=True)
class RatchetVerdict:
    passed: bool
    regressions: Tuple[str, ...]     # domains that regressed
    improvements: Tuple[str, ...]
    detail: str = ""
```

### Component 4: CompetenceScorecard + Review Protocol (`docs/reviews/`)

**Purpose**: the human-facing output. `CompetenceScorecard` aggregates the five domain scores + the
ratchet verdict into a Markdown scorecard. `docs/reviews/AFTER_MILESTONE_REVIEW_TEMPLATE.md` is the
repeatable protocol every future milestone completes.

---

## Data Models

```python
@dataclass(frozen=True)
class CapabilityBenchmark: ...   # (above)
@dataclass(frozen=True)
class DomainScore: ...           # (above)
@dataclass(frozen=True)
class RatchetVerdict: ...        # (above)

@dataclass(frozen=True)
class CompetenceScorecard:
    domain_scores: Tuple[DomainScore, ...]
    verdict: RatchetVerdict
    overall: float               # mean of measured domain scores
```

---

## Correctness Properties

Verified with tests under `FRIDAY_DRY_RUN=1` using stub evidence.

### Property 1: Evidence is the judge, never self-report

`score_benchmark` returns True iff every `required_evidence` kind is present in the bundle; a bundle
missing any required kind scores False regardless of any generated text.
**Validates: Requirements 1.2, 1.3**

### Property 2: Domain score is a bounded weighted ratio

`score_domain` returns `passed_weight / total_weight` in `[0,1]` (0.0 when empty), deterministic.
**Validates: Requirements 1.4**

### Property 3: Ratchet blocks regressions, allows improvements

`check` returns `passed=False` iff some measured domain's new score < baseline − tolerance; an equal or
higher score passes; an unmeasured baseline never blocks.
**Validates: Requirements 2.1, 2.2**

### Property 4: Ratchet never fabricates baselines

`record` marks a domain `measured=True` only when a real score is supplied; the seeded baseline is
`measured=False` for all domains and blocks nothing until a real run.
**Validates: Requirements 2.3, 3.3**

### Property 5: All five domains are covered

The suite catalog contains at least one benchmark for each of browser, desktop, research, coding, and
long_horizon, each with a measurable acceptance criterion and required evidence.
**Validates: Requirements 1.1**

### Property 6: No application/site names in benchmark definitions

Benchmark goal text and definitions contain no banned app/site name or URL scheme literal (Axiom 15) —
benchmarks measure capability, not a specific application.
**Validates: Requirements 1.5**

---

## Error Handling

- A benchmark whose execution raises is scored as a FAIL (no required evidence) — never crashes the run.
- An empty domain suite scores `0.0` (no evidence of competence), never divide-by-zero.
- A missing/corrupt `baseline.json` loads as all-unmeasured (fail-safe): the ratchet blocks nothing
  until a real baseline is recorded, and never fabricates numbers.
- `requires_live` benchmarks in `FRIDAY_DRY_RUN` are reported UNMEASURED/SKIPPED, never scored.

---

## Testing Strategy

- **Unit/property tests** (`tests/friday/test_m14_benchmarks.py`): the 6 properties using stub
  `ExecutionEvidence` — evidence-judged scoring, bounded domain score, ratchet gate behavior, no
  fabricated baselines, five-domain coverage, no app/site names.
- **No real competence numbers asserted** — real scores come only from the maintainer running the
  suite on a real machine (per the review protocol).
- **Regression**: full suite stays green (≥ 1234 + new tests).
