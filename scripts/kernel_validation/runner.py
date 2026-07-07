"""M13 — the dual-path validation runner (non-production; changes no defaults).

Runs each :class:`ValidationScenario` on BOTH the legacy path and the kernel
path with identical goal text, capturing a :class:`ValidationEvidence` per path.
It restores ``FRIDAY_USE_KERNEL_EXECUTION`` after each run and SKIPS
``requires_live`` scenarios under ``FRIDAY_DRY_RUN`` (never fabricating results).

This module NEVER changes a production default: the bridge/kernel are constructed
locally per run, and no global default is mutated. It is intended to be executed
manually on a real machine:

    python -m scripts.kernel_validation.runner
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, List, Optional, Tuple

from scripts.kernel_validation.evidence import ValidationEvidence
from scripts.kernel_validation.scenarios import ValidationScenario, all_scenarios


def _is_dry_run() -> bool:
    return os.environ.get("FRIDAY_DRY_RUN") == "1"


class ValidationRunner:
    """Runs scenarios on legacy and kernel paths and collects evidence.

    ``operator_factory`` is an injected callable ``(goal_text) -> operator`` used
    by the kernel path (and, in a real run, by the legacy path too). Injecting it
    keeps this tool decoupled and testable with stub operators — exactly like the
    M12 GoalExecutionRuntime.
    """

    def __init__(self, operator_factory: Callable[[str], Any]) -> None:
        self._operator_factory = operator_factory

    # -- kernel path --------------------------------------------------------

    def _run_kernel(self, scenario: ValidationScenario) -> ValidationEvidence:
        from friday.events.store import EventStore
        from friday.kernel.execution import GoalExecutionRuntime
        from friday.kernel.kernel import CognitiveKernel

        seen: List[str] = []
        start = time.perf_counter()
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as d:
                kernel = CognitiveKernel(event_store=EventStore(os.path.join(d, "ev.jsonl")))
                kernel.subscribe("goal.completed", lambda e: seen.append(e.event_type))
                kernel.subscribe("goal.failed", lambda e: seen.append(e.event_type))
                runtime = GoalExecutionRuntime(self._operator_factory)
                kernel.register_runtime(runtime)
                kernel.submit_goal(scenario.goal_text)
            latency = (time.perf_counter() - start) * 1000
            result = "pass" if "goal.completed" in seen else "fail"
            return ValidationEvidence(
                scenario_id=scenario.id, path="kernel", result=result,
                event_types=tuple(seen), latency_ms=latency,
            )
        except Exception as exc:  # noqa: BLE001 — a failure is recorded, not raised
            latency = (time.perf_counter() - start) * 1000
            return ValidationEvidence(
                scenario_id=scenario.id, path="kernel", result="fail",
                latency_ms=latency, error=str(exc),
            )

    # -- legacy path --------------------------------------------------------

    def _run_legacy(self, scenario: ValidationScenario) -> ValidationEvidence:
        start = time.perf_counter()
        try:
            operator = self._operator_factory(scenario.goal_text)
            outcome = operator.run(scenario.goal_text)
            latency = (time.perf_counter() - start) * 1000
            completed = bool(getattr(outcome, "completed", False))
            summary = str(getattr(outcome, "summary", "") or "")
            return ValidationEvidence(
                scenario_id=scenario.id, path="legacy",
                result="pass" if completed else "fail",
                output=summary, latency_ms=latency,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000
            return ValidationEvidence(
                scenario_id=scenario.id, path="legacy", result="fail",
                latency_ms=latency, error=str(exc),
            )

    # -- orchestration ------------------------------------------------------

    def run_scenario(
        self, scenario: ValidationScenario
    ) -> Tuple[ValidationEvidence, ValidationEvidence]:
        """Run one scenario on both paths. Live-only scenarios are SKIPPED in
        DRY_RUN (never fabricated). Restores env defaults afterward."""
        prev_flag = os.environ.get("FRIDAY_USE_KERNEL_EXECUTION")
        try:
            if scenario.requires_live and _is_dry_run():
                skipped_k = ValidationEvidence(scenario.id, "kernel", "skipped",
                                               error="requires_live in FRIDAY_DRY_RUN")
                skipped_l = ValidationEvidence(scenario.id, "legacy", "skipped",
                                               error="requires_live in FRIDAY_DRY_RUN")
                return skipped_l, skipped_k

            legacy_ev = self._run_legacy(scenario)
            kernel_ev = self._run_kernel(scenario)
            return legacy_ev, kernel_ev
        finally:
            # Restore the flag exactly as it was — never leak a default change.
            if prev_flag is None:
                os.environ.pop("FRIDAY_USE_KERNEL_EXECUTION", None)
            else:
                os.environ["FRIDAY_USE_KERNEL_EXECUTION"] = prev_flag

    def run_all(self) -> List[Tuple[ValidationEvidence, ValidationEvidence]]:
        return [self.run_scenario(s) for s in all_scenarios()]


if __name__ == "__main__":  # pragma: no cover - manual real-machine entry point
    # On a real machine, replace the stub factory with a real Operator factory:
    #   from friday.operator import Operator
    #   factory = lambda g: Operator(model_router=..., browser_controller=...)
    print("This harness is intended to be driven with a real Operator factory on")
    print("a live machine. See docs/validation/KERNEL_PRODUCTION_VALIDATION_PLAN.md.")
