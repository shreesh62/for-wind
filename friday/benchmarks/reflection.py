"""M20 (A2.10) — deterministic layered-reflection quality benchmark.

Measures the three higher reflection layers (Long-Term / Skill / Architectural,
``friday/cognition/reflection_layers.py``) hermetically: a fixed set of synthetic
``reflection.completed`` streams is fed through the layers attached to a *real*
``CognitiveKernel``, and the proposal event types the layers emit
(``reflection.longterm`` / ``reflection.skill`` / ``reflection.architectural``) are
compared against the proposals each stream is EXPECTED to produce. This exposes the
expected-proposal precision / recall the audit asks every capability to surface,
plus per-type emission counts.

Deterministic + hermetic: NO LLM, NO network, NO wall-clock dependence. The kernel
is wired with an in-memory event store (no ``session.jsonl`` is written), synthetic
events carry fixed timestamps, and metrics depend only on emitted event *types* —
never on ``time.time()`` or run order. Identical runs yield identical metrics.

POLICY: This benchmark is domain-general (Axiom 15 — no application/browser/site
identity, only generic capabilities like "research"/"coding"/"navigation" and
environment classes like "web"/"desktop"). It is NOT part of the 5-domain
competence scorecard and is NEVER written into the committed competence baseline
(mirrors the M19 retrieval-router and M24 recovery-rate suite policy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from friday.cognition.reflection_layers import (
    ArchitecturalReflector,
    LongTermReflector,
    SkillReflector,
    attach_reflection_layers,
)
from friday.events.event import Event, make_event
from friday.kernel.kernel import CognitiveKernel

# Proposal event types the higher reflection layers emit (the labels we score).
PROPOSAL_LONGTERM = "reflection.longterm"
PROPOSAL_SKILL = "reflection.skill"
PROPOSAL_ARCHITECTURAL = "reflection.architectural"
PROPOSAL_TYPES: Tuple[str, ...] = (
    PROPOSAL_LONGTERM,
    PROPOSAL_SKILL,
    PROPOSAL_ARCHITECTURAL,
)

# Explicit, small benchmark thresholds so every intended proposal is reachable with
# short synthetic streams while the layers stay mutually distinguishable. The
# long-term (adverse-trend) error band sits ABOVE the architectural (hot-capability)
# band, so a moderate multi-capability stream can trip the cross-capability meta
# signal without also tripping a per-capability long-term trend.
_BENCH_WINDOW = 50
_BENCH_MIN_SAMPLES = 3
_BENCH_LONGTERM_ERROR_THRESHOLD = 0.7    # long-term: mean error at/above → adverse
_BENCH_SKILL_VERIFIED_THRESHOLD = 0.7    # skill: verified_rate at/above → mature
_BENCH_SKILL_ERROR_THRESHOLD = 0.3       # skill: mean error at/below → low-error
_BENCH_ARCH_ERROR_THRESHOLD = 0.4        # architectural: per-cap mean error → hot
_BENCH_ARCH_MIN_CAPABILITIES = 2         # architectural: distinct hot capabilities


# --------------------------------------------------------------------------- specs


@dataclass(frozen=True)
class ReflectionSample:
    """One synthetic ``reflection.completed`` sample in a scenario stream.

    ``prediction_error`` and ``calibration`` are clamped to [0, 1] by the layers;
    ``verified`` mirrors the (optional) verification flag the layers read.
    """

    capability: str
    environment: str
    prediction_error: float
    calibration: float
    verified: bool


@dataclass(frozen=True)
class ReflectionScenario:
    """A synthetic stream plus the proposal types it is EXPECTED to emit.

    ``expected_proposals`` is the exact set of ``reflection.*`` event types the
    layers should emit for ``samples`` (empty for a below-threshold stream). A
    scenario "matches" when the set of emitted types equals this set exactly.
    """

    scenario_id: str
    samples: Tuple[ReflectionSample, ...]
    expected_proposals: FrozenSet[str]


# ----------------------------------------------------------------------- metrics


@dataclass
class ReflectionMetrics:
    """Aggregate expected-proposal outcome of a benchmark run (JSON-projectable).

    Precision / recall are computed over ``(scenario, proposal-type)`` labels: a
    true positive is an expected type that was emitted, a false positive a type
    emitted but not expected, and a false negative an expected type never emitted.
    ``exact_match`` counts scenarios whose emitted type set equals the expected set
    exactly (so a below-threshold stream that stays silent counts as a match).
    """

    total_scenarios: int = 0
    true_positives: int = 0        # expected type emitted
    false_positives: int = 0       # emitted type that was not expected
    false_negatives: int = 0       # expected type never emitted
    exact_match: int = 0           # scenarios whose emitted set == expected set
    by_type_emitted: Dict[str, int] = field(default_factory=dict)  # emission counts

    @property
    def precision(self) -> float:
        """Expected-proposal precision in [0, 1].

        With no scenarios there is nothing to score (0.0). With scenarios but no
        emitted proposals there are no false positives, so precision is perfect.
        """
        if self.total_scenarios <= 0:
            return 0.0
        denom = self.true_positives + self.false_positives
        if denom <= 0:
            return 1.0
        return max(0.0, min(1.0, self.true_positives / denom))

    @property
    def recall(self) -> float:
        """Expected-proposal recall in [0, 1].

        With no scenarios there is nothing to score (0.0). With scenarios but no
        expected proposals there are no false negatives, so recall is perfect.
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
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "exact_match_rate": round(self.exact_match_rate, 4),
            "by_type_emitted": dict(self.by_type_emitted),
        }

    def to_markdown(self) -> str:
        lines = [
            "# Reflection Layers Benchmark",
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
            "",
            "| Proposal type | emissions |",
            "|---|---|",
        ]
        for proposal_type, count in sorted(self.by_type_emitted.items()):
            lines.append(f"| {proposal_type} | {count} |")
        return "\n".join(lines)


# --------------------------------------------------------------------- scenarios


def default_reflection_scenarios() -> Tuple[ReflectionScenario, ...]:
    """A fixed, domain-general scenario set (generic capabilities only — Axiom 15).

    Covers the four canonical outcomes of the higher layers under the benchmark
    thresholds: a below-threshold stream (no proposal), a high-error stream (a
    long-term adverse-trend proposal), a verified low-error stream (a skill-pipeline
    candidate proposal), and a multi-capability moderate-error stream (a single
    cross-capability architectural advisory).
    """
    n = _BENCH_MIN_SAMPLES

    def stream(
        capability: str,
        environment: str,
        error: float,
        calibration: float,
        verified: bool,
        count: int,
    ) -> Tuple[ReflectionSample, ...]:
        return tuple(
            ReflectionSample(capability, environment, error, calibration, verified)
            for _ in range(count)
        )

    return (
        # 1) Below every threshold: enough samples to aggregate, but a mid-band error
        #    that is neither an adverse trend, low-error/verified, nor "hot". None.
        ReflectionScenario(
            scenario_id="below-threshold",
            samples=stream("research", "web", 0.35, 0.5, False, n + 1),
            expected_proposals=frozenset(),
        ),
        # 2) Single capability, high sustained error → long-term adverse trend only.
        ReflectionScenario(
            scenario_id="high-error-longterm",
            samples=stream("coding", "desktop", 0.85, 0.3, False, n),
            expected_proposals=frozenset({PROPOSAL_LONGTERM}),
        ),
        # 3) Single capability, verified low error → skill-pipeline candidate only.
        ReflectionScenario(
            scenario_id="verified-low-error-skill",
            samples=stream("navigation", "web", 0.1, 0.9, True, n),
            expected_proposals=frozenset({PROPOSAL_SKILL}),
        ),
        # 4) Several capabilities each moderately "hot" (above the architectural band
        #    but below the long-term band) → one cross-capability architectural
        #    advisory, and no per-capability long-term or skill proposals.
        ReflectionScenario(
            scenario_id="multi-capability-architectural",
            samples=(
                stream("research", "web", 0.5, 0.4, False, n)
                + stream("coding", "web", 0.5, 0.4, False, n)
                + stream("navigation", "web", 0.5, 0.4, False, n)
            ),
            expected_proposals=frozenset({PROPOSAL_ARCHITECTURAL}),
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
        self._events: List[Event] = []

    def append(self, event: Event) -> None:
        self._events.append(event)

    @property
    def append_count(self) -> int:
        return len(self._events)


# ---------------------------------------------------------------------- benchmark


class ReflectionBenchmark:
    """Feeds synthetic reflection streams through the layers on a real kernel."""

    def __init__(
        self,
        scenarios: Optional[Tuple[ReflectionScenario, ...]] = None,
        *,
        window: int = _BENCH_WINDOW,
        min_samples: int = _BENCH_MIN_SAMPLES,
        longterm_error_threshold: float = _BENCH_LONGTERM_ERROR_THRESHOLD,
        skill_verified_threshold: float = _BENCH_SKILL_VERIFIED_THRESHOLD,
        skill_error_threshold: float = _BENCH_SKILL_ERROR_THRESHOLD,
        arch_error_threshold: float = _BENCH_ARCH_ERROR_THRESHOLD,
        arch_min_capabilities: int = _BENCH_ARCH_MIN_CAPABILITIES,
    ) -> None:
        self._scenarios = (
            scenarios if scenarios is not None else default_reflection_scenarios()
        )
        self._window = window
        self._min_samples = min_samples
        self._longterm_error_threshold = longterm_error_threshold
        self._skill_verified_threshold = skill_verified_threshold
        self._skill_error_threshold = skill_error_threshold
        self._arch_error_threshold = arch_error_threshold
        self._arch_min_capabilities = arch_min_capabilities

    def run(self) -> ReflectionMetrics:
        """Feed every scenario through fresh layers and aggregate the metrics."""
        metrics = ReflectionMetrics()

        for sc in self._scenarios:
            metrics.total_scenarios += 1
            emitted = self._run_scenario(sc)

            emitted_types = set(emitted)
            expected = set(sc.expected_proposals)
            metrics.true_positives += len(expected & emitted_types)
            metrics.false_positives += len(emitted_types - expected)
            metrics.false_negatives += len(expected - emitted_types)
            if emitted_types == expected:
                metrics.exact_match += 1

            for proposal_type in emitted:
                metrics.by_type_emitted[proposal_type] = (
                    metrics.by_type_emitted.get(proposal_type, 0) + 1
                )

        return metrics

    def _run_scenario(self, sc: ReflectionScenario) -> List[str]:
        """Attach fresh layers to a real kernel, publish the stream, collect types."""
        kernel = CognitiveKernel(event_store=_InMemoryEventStore())

        # Explicit small thresholds keep the three layers reachable AND mutually
        # distinguishable on short streams (see module thresholds).
        longterm = LongTermReflector(
            window=self._window,
            min_samples=self._min_samples,
            error_threshold=self._longterm_error_threshold,
        )
        skill = SkillReflector(
            window=self._window,
            min_samples=self._min_samples,
            verified_threshold=self._skill_verified_threshold,
            error_threshold=self._skill_error_threshold,
        )
        architectural = ArchitecturalReflector(
            window=self._window,
            min_samples=self._min_samples,
            error_threshold=self._arch_error_threshold,
            min_capabilities=self._arch_min_capabilities,
        )
        attach_reflection_layers(
            kernel,
            longterm=longterm,
            skill=skill,
            architectural=architectural,
        )

        emitted: List[str] = []

        def collector(event: Any) -> None:
            emitted.append(getattr(event, "event_type", ""))

        for proposal_type in PROPOSAL_TYPES:
            kernel.subscribe(proposal_type, collector)

        for index, sample in enumerate(sc.samples):
            # Fixed logical + wall time: emissions stay ordered and hermetic (no
            # dependence on time.time()); metrics read only the emitted event type.
            event = make_event(
                event_type="reflection.completed",
                source="reflection-benchmark",
                logical_time=index + 1,
                payload={
                    "goal_id": f"{sc.scenario_id}:{index}",
                    "scale": "session",
                    "capability": sample.capability,
                    "environment": sample.environment,
                    "prediction_error": sample.prediction_error,
                    "calibration": sample.calibration,
                    "verified": sample.verified,
                },
                wall_time=0.0,
            )
            kernel.publish_event(event)

        return emitted
