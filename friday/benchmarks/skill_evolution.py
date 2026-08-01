"""M17 (A2.5) — deterministic skill-evolution candidate-emission benchmark.

Measures the M17 :class:`friday.learning.skill_pipeline.SkillEvolutionPipeline`
hermetically: a fixed set of synthetic maturation streams (``learning.validated`` /
``reflection.skill`` / ``learning.rejected`` events, each carrying a generic
``(capability, environment)`` identity) is fed through the pipeline attached to a
*real* ``CognitiveKernel``, and the ``skill.candidate`` proposals the pipeline emits
are compared against the candidates each stream is EXPECTED to produce. This exposes
the candidate-emission precision / recall the audit asks every capability to
surface, plus the total number of candidate emissions.

Deterministic + hermetic: NO LLM, NO network, NO wall-clock dependence. The kernel
is wired with an in-memory event store (no ``session.jsonl`` is written), synthetic
events carry fixed ``logical_time`` and ``wall_time=0.0``, and metrics depend only on
the emitted candidate *identities* — never on ``time.time()`` or run order. Identical
runs yield identical metrics.

POLICY: This benchmark is domain-general (Axiom 15 — no application/browser/site
identity, only generic capabilities like "research"/"coding"/"navigation" and
environment classes like "web"/"desktop"). It is NOT part of the 5-domain competence
scorecard and is NEVER written into the committed competence baseline (mirrors the
M19 retrieval-router and M20 reflection-layers benchmark policy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from friday.events.event import make_event
from friday.kernel.kernel import CognitiveKernel
from friday.learning.skill_pipeline import attach_skill_pipeline

# Signal event types consumed by the pipeline, and the proposal type it emits.
SIGNAL_VALIDATED = "learning.validated"
SIGNAL_SKILL = "reflection.skill"
SIGNAL_REJECTED = "learning.rejected"
PROPOSAL_CANDIDATE = "skill.candidate"

# Fixed, deterministic evidence attached to synthetic ``reflection.skill`` events so
# the emitted candidate payload carries a realistic (but clock-free) summary. Values
# never affect scoring — metrics read only the emitted candidate identity.
_BENCH_MEAN_ERROR = 0.1
_BENCH_VERIFIED_RATE = 0.9
_BENCH_SAMPLE_COUNT = 5


# --------------------------------------------------------------------------- specs


@dataclass(frozen=True)
class SkillEvent:
    """One synthetic maturation event in a scenario stream.

    ``event_type`` is one of the consumed signal types
    (``learning.validated`` / ``reflection.skill`` / ``learning.rejected``); the
    generic ``(capability, environment)`` identity is the only routing key (no
    application/site/window identity ever appears — Axiom 15).
    """

    event_type: str
    capability: str
    environment: str


@dataclass(frozen=True)
class SkillScenario:
    """A synthetic maturation stream plus the candidates it is EXPECTED to emit.

    ``events`` are published in order through the pipeline on a real kernel;
    ``expected_candidates`` is the exact set of ``(capability, environment)`` skills
    that should each emit exactly one ``skill.candidate`` (empty when no skill in the
    stream carries both required signals). A scenario "matches" when the set of
    skills that emitted exactly one candidate equals this set exactly.
    """

    scenario_id: str
    events: Tuple[SkillEvent, ...]
    expected_candidates: FrozenSet[Tuple[str, str]]


# ----------------------------------------------------------------------- metrics


@dataclass
class SkillMetrics:
    """Aggregate candidate-emission outcome of a benchmark run (JSON-projectable).

    Precision / recall are computed over ``(scenario, skill)`` labels: a true
    positive is an expected skill that emitted exactly one candidate, a false
    positive a candidate emitted for a skill that was not expected, and a false
    negative an expected skill that never emitted. ``exact_match`` counts scenarios
    whose emitted-candidate skill set equals the expected set exactly (so a
    single-signal stream that stays silent counts as a match).
    """

    total_scenarios: int = 0
    true_positives: int = 0        # expected skill emitted exactly one candidate
    false_positives: int = 0       # candidate emitted for a skill not expected
    false_negatives: int = 0       # expected skill that never emitted
    exact_match: int = 0           # scenarios whose emitted set == expected set
    total_emissions: int = 0       # total ``skill.candidate`` events emitted

    @property
    def precision(self) -> float:
        """Candidate-emission precision in [0, 1].

        With no scenarios there is nothing to score (0.0). With scenarios but no
        emitted candidates there are no false positives, so precision is perfect.
        """
        if self.total_scenarios <= 0:
            return 0.0
        denom = self.true_positives + self.false_positives
        if denom <= 0:
            return 1.0
        return max(0.0, min(1.0, self.true_positives / denom))

    @property
    def recall(self) -> float:
        """Candidate-emission recall in [0, 1].

        With no scenarios there is nothing to score (0.0). With scenarios but no
        expected candidates there are no false negatives, so recall is perfect.
        """
        if self.total_scenarios <= 0:
            return 0.0
        denom = self.true_positives + self.false_negatives
        if denom <= 0:
            return 1.0
        return max(0.0, min(1.0, self.true_positives / denom))

    @property
    def exact_match_rate(self) -> float:
        """Fraction of scenarios whose emitted set matched expectations, in [0,1]."""
        if self.total_scenarios <= 0:
            return 0.0
        return max(0.0, min(1.0, self.exact_match / self.total_scenarios))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_scenarios": self.total_scenarios,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "exact_match": self.exact_match,
            "total_emissions": self.total_emissions,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "exact_match_rate": round(self.exact_match_rate, 4),
        }

    def to_markdown(self) -> str:
        lines = [
            "# Skill Evolution Benchmark",
            "",
            f"- Scenarios: {self.total_scenarios}",
            f"- Precision: {self.precision:.4f} "
            f"(TP {self.true_positives} / FP {self.false_positives})",
            f"- Recall: {self.recall:.4f} "
            f"(TP {self.true_positives} / FN {self.false_negatives})",
            (
                f"- Exact-match scenarios: {self.exact_match}/{self.total_scenarios} "
                f"({self.exact_match_rate:.4f})"
            ),
            f"- Total candidate emissions: {self.total_emissions}",
        ]
        return "\n".join(lines)


# --------------------------------------------------------------------- scenarios


def default_skill_scenarios() -> Tuple[SkillScenario, ...]:
    """A fixed, domain-general scenario set (generic capabilities only — Axiom 15).

    Covers the canonical outcomes of the dual-signal candidate rule: a dual-signal
    skill (one candidate), each single-signal skill (none), a validated-then-
    rejected-then-skill skill (none — the rejection disqualifies it), and two
    independent dual-signal skills (two candidates).
    """
    return (
        # (a) Dual signal (validated + skill) → exactly one candidate.
        SkillScenario(
            scenario_id="dual-signal",
            events=(
                SkillEvent(SIGNAL_VALIDATED, "research", "web"),
                SkillEvent(SIGNAL_SKILL, "research", "web"),
            ),
            expected_candidates=frozenset({("research", "web")}),
        ),
        # (b1) Single signal — only ``learning.validated`` → no candidate.
        SkillScenario(
            scenario_id="single-signal-validated",
            events=(SkillEvent(SIGNAL_VALIDATED, "coding", "desktop"),),
            expected_candidates=frozenset(),
        ),
        # (b2) Single signal — only ``reflection.skill`` → no candidate.
        SkillScenario(
            scenario_id="single-signal-skill",
            events=(SkillEvent(SIGNAL_SKILL, "navigation", "web"),),
            expected_candidates=frozenset(),
        ),
        # (c) Validated → rejected → skill: the rejection clears the generalization,
        #     so the later skill signal must NOT complete a candidate.
        SkillScenario(
            scenario_id="validated-rejected-skill",
            events=(
                SkillEvent(SIGNAL_VALIDATED, "research", "desktop"),
                SkillEvent(SIGNAL_REJECTED, "research", "desktop"),
                SkillEvent(SIGNAL_SKILL, "research", "desktop"),
            ),
            expected_candidates=frozenset(),
        ),
        # (d) Two independent dual-signal skills → exactly two candidates.
        SkillScenario(
            scenario_id="two-dual-signals",
            events=(
                SkillEvent(SIGNAL_VALIDATED, "coding", "web"),
                SkillEvent(SIGNAL_SKILL, "coding", "web"),
                SkillEvent(SIGNAL_VALIDATED, "navigation", "desktop"),
                SkillEvent(SIGNAL_SKILL, "navigation", "desktop"),
            ),
            expected_candidates=frozenset(
                {("coding", "web"), ("navigation", "desktop")}
            ),
        ),
    )


# ------------------------------------------------------------- hermetic event store


class _InMemoryEventStore:
    """Hermetic in-memory stand-in for ``EventStore`` (no disk I/O).

    During a benchmark run the kernel only ``append``s events and reads
    ``append_count`` (no replay / checkpoint), so this duck-types exactly those.
    Keeping the store in memory is what makes the benchmark hermetic: no
    ``session.jsonl`` is written, so runs cannot contaminate one another and results
    never depend on prior disk state. A fresh instance is used per scenario.
    """

    def __init__(self) -> None:
        self._events: List[Any] = []

    def append(self, event: Any) -> None:
        self._events.append(event)

    @property
    def append_count(self) -> int:
        return len(self._events)


# ---------------------------------------------------------------------- benchmark


class SkillEvolutionBenchmark:
    """Feeds synthetic maturation streams through the pipeline on a real kernel."""

    def __init__(
        self, scenarios: Optional[Tuple[SkillScenario, ...]] = None
    ) -> None:
        self._scenarios = (
            scenarios if scenarios is not None else default_skill_scenarios()
        )

    def run(self) -> SkillMetrics:
        """Feed every scenario through a fresh pipeline and aggregate the metrics."""
        metrics = SkillMetrics()

        for sc in self._scenarios:
            metrics.total_scenarios += 1
            emitted = self._run_scenario(sc)

            # Count candidate emissions per skill identity.
            counts: Dict[Tuple[str, str], int] = {}
            for skill in emitted:
                counts[skill] = counts.get(skill, 0) + 1
            metrics.total_emissions += len(emitted)

            expected = set(sc.expected_candidates)
            emitted_skills = set(counts)

            # True positive: an expected skill that emitted exactly one candidate.
            for skill in expected:
                if counts.get(skill, 0) == 1:
                    metrics.true_positives += 1
                elif counts.get(skill, 0) == 0:
                    metrics.false_negatives += 1
                else:
                    # More than one emission for an expected skill: count the first
                    # as the match and the surplus as false positives (the pipeline
                    # dedups, so this branch is defensive, never hit in practice).
                    metrics.true_positives += 1
                    metrics.false_positives += counts[skill] - 1

            # False positive: every candidate emitted for a skill not expected.
            for skill in emitted_skills - expected:
                metrics.false_positives += counts[skill]

            # Exact match: emitted skill set equals expectations and each expected
            # skill emitted exactly once (no surplus, no unexpected emissions).
            if emitted_skills == expected and all(
                counts[skill] == 1 for skill in counts
            ):
                metrics.exact_match += 1

        return metrics

    def _run_scenario(self, sc: SkillScenario) -> List[Tuple[str, str]]:
        """Attach a fresh pipeline to a real kernel, publish the stream, collect."""
        kernel = CognitiveKernel(event_store=_InMemoryEventStore())
        attach_skill_pipeline(kernel)

        emitted: List[Tuple[str, str]] = []

        def collector(event: Any) -> None:
            payload = getattr(event, "payload", None) or {}
            capability = str(payload.get("capability", ""))
            environment = str(payload.get("environment", ""))
            emitted.append((capability, environment))

        kernel.subscribe(PROPOSAL_CANDIDATE, collector)

        for index, signal in enumerate(sc.events):
            payload: Dict[str, Any] = {
                "capability": signal.capability,
                "environment": signal.environment,
            }
            if signal.event_type == SIGNAL_SKILL:
                # Fixed, clock-free evidence summary (never affects scoring).
                payload["mean_error"] = _BENCH_MEAN_ERROR
                payload["verified_rate"] = _BENCH_VERIFIED_RATE
                payload["sample_count"] = _BENCH_SAMPLE_COUNT
            elif signal.event_type == SIGNAL_REJECTED:
                payload["reason"] = "benchmark-disqualification"

            # Fixed logical + wall time: emissions stay ordered and hermetic (no
            # dependence on time.time()); metrics read only the emitted identity.
            event = make_event(
                event_type=signal.event_type,
                source="skill-evolution-benchmark",
                logical_time=index + 1,
                payload=payload,
                wall_time=0.0,
            )
            kernel.publish_event(event)

        return emitted
