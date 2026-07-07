"""Ch 55 — goal-completion benchmark suite, runner, report, and regression detection.

Measures whether a capability actually *completes goals* (not token counts): a
`BenchmarkSuite` holds weighted `BenchmarkScenario`s, a `BenchmarkRunner` scores a
candidate against the suite into a bounded `BenchmarkReport`, and a
`RegressionDetector` decides whether a candidate underperforms an incumbent.

The scoring core is pure and deterministic: for a deterministic ``evaluate`` the
same suite yields the same report every run. No hardcoded application/site names
or URL schemes (Axiom 15); stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple


@dataclass(frozen=True)
class BenchmarkScenario:
    """Ch 55 — one goal-completion scenario with a relative importance weight."""

    id: str
    description: str
    weight: float = 1.0


@dataclass(frozen=True)
class BenchmarkReport:
    """Ch 55 — the aggregate result of running a suite against a candidate."""

    capability_id: str
    score: float
    scenarios_run: int
    scenarios_passed: int
    latency_ms: float = 0.0


class BenchmarkSuite:
    """Ch 55 — a set of goal-completion scenarios (not token metrics)."""

    def __init__(self) -> None:
        self._scenarios: List[BenchmarkScenario] = []

    def add(self, scenario: BenchmarkScenario) -> None:
        """Append a scenario to the suite."""
        self._scenarios.append(scenario)

    def scenarios(self) -> Tuple[BenchmarkScenario, ...]:
        """Return the suite's scenarios as an immutable tuple."""
        return tuple(self._scenarios)


class BenchmarkRunner:
    """Ch 55 — run a candidate against a suite; produce a bounded BenchmarkReport."""

    def run(
        self,
        capability_id: str,
        evaluate: Callable[[BenchmarkScenario], bool],
        suite: BenchmarkSuite,
    ) -> BenchmarkReport:
        """Score ``capability_id`` against ``suite`` using ``evaluate``.

        ``evaluate(scenario) -> bool`` is called once per scenario inside a
        try/except: a raising ``evaluate`` counts as a FAILED scenario rather than
        aborting the run. The score is the weighted pass ratio
        ``passed_weight / total_weight`` clamped to ``[0, 1]``, or ``0.0`` when the
        suite is empty (no evidence of competence). Deterministic for a
        deterministic ``evaluate``.
        """
        scenarios = suite.scenarios()
        total_weight = sum(s.weight for s in scenarios)
        passed_weight = 0.0
        scenarios_passed = 0

        for scenario in scenarios:
            try:
                passed = bool(evaluate(scenario))
            except Exception:
                passed = False
            if passed:
                passed_weight += scenario.weight
                scenarios_passed += 1

        score = passed_weight / total_weight if total_weight > 0 else 0.0
        score = max(0.0, min(1.0, score))

        return BenchmarkReport(
            capability_id=capability_id,
            score=score,
            scenarios_run=len(scenarios),
            scenarios_passed=scenarios_passed,
        )


class RegressionDetector:
    """Ch 55 — a candidate must not score below the incumbent."""

    def is_regression(
        self,
        incumbent: float,
        candidate: float,
        *,
        tolerance: float = 0.0,
    ) -> bool:
        """Return True iff ``candidate < incumbent - tolerance``.

        Monotonic in ``candidate``: a lower candidate score is never less likely to
        be flagged as a regression.
        """
        return candidate < incumbent - tolerance
