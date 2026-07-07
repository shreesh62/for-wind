"""Ch 27 — candidate → sandbox → benchmark → promote (evidence-gated)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

from friday.benchmarks.suite import BenchmarkSuite, RegressionDetector
from friday.events.event import make_event
from friday.evolution.lifecycle import CapabilityLifecycle, LifecycleState


class PromotionOutcome(str, Enum):
    """Ch 27 — terminal outcome of a promotion attempt."""

    PROMOTED = "promoted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class PromotionResult:
    """Ch 27 — the immutable result of running a candidate through the pipeline."""

    outcome: PromotionOutcome
    capability_id: str
    benchmark_score: float
    reason: str = ""


class PromotionPipeline:
    """Ch 27 — candidate → sandbox → benchmark → promote (evidence-gated)."""

    def __init__(
        self,
        registry: Any,
        lifecycle: CapabilityLifecycle,
        runner: Any,
        *,
        min_benchmark_score: float = 0.6,
    ) -> None:
        self._registry = registry
        self._lifecycle = lifecycle
        self._runner = runner
        self._min_benchmark_score = min_benchmark_score
        self._detector = RegressionDetector()
        self._kernel: Any = None

    # --- pure core ---------------------------------------------------------

    def submit(
        self,
        candidate: Any,
        *,
        suite: Optional[BenchmarkSuite] = None,
        evaluate: Optional[Callable[[Any], bool]] = None,
        incumbent_score: Optional[float] = None,
    ) -> PromotionResult:
        """Pure core: sandbox → run benchmark → gate → (promote via registry | reject).

        Deterministic wrt inputs: promotes only when the benchmark score is at or
        above ``min_benchmark_score`` and the candidate does not regress the
        incumbent. Emits ``capability.promoted`` / ``capability.rejected`` when a
        kernel is attached.
        """
        cap_id = getattr(candidate, "proposed_id", None)
        if not cap_id:
            return self._finish(
                PromotionResult(
                    PromotionOutcome.REJECTED, "", 0.0, "candidate has no proposed_id"
                )
            )

        # No benchmark evidence -> deterministically un-promotable.
        if suite is None or not suite.scenarios() or evaluate is None:
            return self._finish(
                PromotionResult(
                    PromotionOutcome.REJECTED, cap_id, 0.0, "no benchmark evidence"
                )
            )

        report = self._runner.run(cap_id, evaluate, suite)
        score = report.score

        # Regression check against an existing incumbent (score supplied by caller).
        incumbent = self._registry.get(cap_id)
        if (
            incumbent is not None
            and incumbent_score is not None
            and self._detector.is_regression(incumbent_score, score)
        ):
            return self._finish(
                PromotionResult(PromotionOutcome.REJECTED, cap_id, score, "regression")
            )

        if score < self._min_benchmark_score:
            return self._finish(
                PromotionResult(
                    PromotionOutcome.REJECTED, cap_id, score, "below benchmark floor"
                )
            )

        # Passing candidate: promote via the sanctioned registry seam, then advance
        # lifecycle DRAFT -> EXPERIMENTAL. A lifecycle already past DRAFT must not
        # crash the promotion, so guard the transition.
        self._registry.promote_candidate(candidate)
        try:
            self._lifecycle.transition(cap_id, LifecycleState.EXPERIMENTAL)
        except Exception:  # noqa: BLE001 — an already-advanced lifecycle still counts as promoted
            pass

        return self._finish(
            PromotionResult(PromotionOutcome.PROMOTED, cap_id, score)
        )

    # --- kernel wiring (Ch 52 — kernel-driven; never raises into the tick loop) ---

    def attach(self, kernel: Any) -> None:
        """Subscribe to ``capability.candidate`` (Ch 52)."""
        self._kernel = kernel
        kernel.subscribe("capability.candidate", self._on_candidate)

    def _on_candidate(self, event: Any) -> None:
        """Defensive stub: candidates cannot be benchmarked without a suite here.

        The real benchmarked promotion is driven by ``submit(...)`` in tests and
        integration. This handler reads its payload defensively and never raises
        into the kernel tick loop.
        """
        try:
            payload = getattr(event, "payload", None) or {}
            # No suite/evaluate available on the bus — nothing to promote safely.
            _ = payload.get("proposed_id")
        except Exception:  # noqa: BLE001 — a handler must never break the tick loop
            return

    def _finish(self, result: PromotionResult) -> PromotionResult:
        """Emit the outcome event (when attached) and return the result."""
        if result.outcome is PromotionOutcome.PROMOTED:
            self._emit(
                "capability.promoted",
                {
                    "capability_id": result.capability_id,
                    "benchmark_score": result.benchmark_score,
                },
            )
        else:
            self._emit(
                "capability.rejected",
                {"capability_id": result.capability_id, "reason": result.reason},
            )
        return result

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish a pipeline event via the kernel; never raises into a tick loop."""
        if self._kernel is None:
            return
        try:
            self._kernel.publish_event(
                make_event(
                    event_type=event_type,
                    source="evolution.pipeline",
                    logical_time=self._next_logical_time(),
                    payload=payload,
                )
            )
        except Exception:  # noqa: BLE001 — emission must never break promotion
            return

    def _next_logical_time(self) -> int:
        """Best-effort next logical time from kernel health; defaults to 1."""
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:  # noqa: BLE001 — health must never break emission
            return 1
