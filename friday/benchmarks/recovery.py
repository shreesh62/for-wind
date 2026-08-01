"""M24 (activation) — recovery-rate benchmark (audit objective 5).

Measures the now-active failure→recovery loop deterministically and hermetically:
feed a fixed set of synthetic failure verdicts through a real kernel wired with the
reactive loop, and count how many produced an ACTIONABLE recovery proposal (a
`recovery.proposed` event whose plan has a chosen alternative). This exposes
recovery rate, failure-cause (domain) distribution, and proposal counts — the
"success/recovery-rate/failure-cause" metrics the audit asks every capability to
expose.

Deterministic: no LLM, no network, no wall-clock dependence. NOT part of the
5-domain competence scorecard and never recorded to the committed baseline
(mirrors the M23 web-independence suite policy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from friday.verification.failure import classify_error_category


@dataclass(frozen=True)
class RecoveryScenario:
    """One synthetic failure to feed through the loop (always an unmet verdict)."""

    id: str
    requirement: str          # drives RepairDiagnoser (gather/produce/file/navigate/deliver)
    category: str             # free-form error_category → FailureDomain (distribution)
    capability: str = ""
    environment: str = ""
    reversible: bool = True
    blocked: bool = False


@dataclass
class RecoveryMetrics:
    """Aggregate outcome of a recovery benchmark run (JSON-projectable)."""

    total_failures: int = 0
    proposals: int = 0             # recovery.proposed events emitted
    actionable: int = 0            # proposals with a chosen alternative
    by_domain: Dict[str, int] = field(default_factory=dict)
    by_failure_class: Dict[str, int] = field(default_factory=dict)

    @property
    def recovery_rate(self) -> float:
        """Fraction of failures that yielded an actionable recovery, in [0,1]."""
        if self.total_failures <= 0:
            return 0.0
        return max(0.0, min(1.0, self.actionable / self.total_failures))

    @property
    def proposal_rate(self) -> float:
        """Fraction of failures that produced any recovery proposal, in [0,1]."""
        if self.total_failures <= 0:
            return 0.0
        return max(0.0, min(1.0, self.proposals / self.total_failures))

    def to_payload(self) -> Dict[str, Any]:
        return {
            "total_failures": self.total_failures,
            "proposals": self.proposals,
            "actionable": self.actionable,
            "recovery_rate": round(self.recovery_rate, 4),
            "proposal_rate": round(self.proposal_rate, 4),
            "by_domain": dict(self.by_domain),
            "by_failure_class": dict(self.by_failure_class),
        }

    def to_markdown(self) -> str:
        lines = [
            "# Recovery Benchmark",
            "",
            f"- Failures: {self.total_failures}",
            f"- Recovery proposals: {self.proposals} (proposal rate {self.proposal_rate:.4f})",
            f"- Actionable recoveries: {self.actionable} (recovery rate {self.recovery_rate:.4f})",
            "",
            "| Failure domain | count |",
            "|---|---|",
        ]
        for domain, count in sorted(self.by_domain.items()):
            lines.append(f"| {domain} | {count} |")
        return "\n".join(lines)


def default_recovery_scenarios() -> Tuple[RecoveryScenario, ...]:
    """A fixed, domain-general scenario set (no app/site identity — Axiom 15)."""
    return (
        RecoveryScenario("gather", "information about the topic must be gathered",
                         category="target_not_found", capability="research", environment="web"),
        RecoveryScenario("produce", "a written summary must be produced",
                         category="adapter_failed", capability="synthesize"),
        RecoveryScenario("file", "the document must be saved to a file",
                         category="desktop_error", capability="write_file"),
        RecoveryScenario("navigate", "the page must be navigated to and opened",
                         category="window_not_found", capability="navigate", environment="web"),
        RecoveryScenario("gather2", "sources must be collected and read",
                         category="perception_unavailable", capability="research", environment="web"),
        RecoveryScenario("produce2", "content must be synthesized from the sources",
                         category="verification_failed", capability="synthesize"),
    )


class RecoveryBenchmark:
    """Runs recovery scenarios through a kernel wired with the reactive loop."""

    def __init__(self, kernel: Any, *, reactive_loop: Any = None) -> None:
        from friday.kernel.reactive_loop import attach_reactive_loop
        from friday.verification.publisher import VerificationEventPublisher

        self._kernel = kernel
        # Reuse an already-attached loop if provided; otherwise wire one (logging off
        # to keep the benchmark quiet). Recovery is the component we measure.
        self._loop = reactive_loop or attach_reactive_loop(kernel, enable_logging=False)
        self._publisher = VerificationEventPublisher(kernel=kernel)
        self._proposals: List[dict] = []
        kernel.subscribe("recovery.proposed", self._capture)

    def _capture(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        self._proposals.append(dict(payload))

    def run(self, scenarios: Optional[Tuple[RecoveryScenario, ...]] = None) -> RecoveryMetrics:
        """Publish each scenario as a failed verdict and aggregate the outcome."""
        from friday.verification.evidence_law import ExecutionEvidence

        scenarios = scenarios if scenarios is not None else default_recovery_scenarios()
        metrics = RecoveryMetrics()

        for sc in scenarios:
            metrics.total_failures += 1
            domain = classify_error_category(sc.category).value
            metrics.by_domain[domain] = metrics.by_domain.get(domain, 0) + 1

            before = len(self._proposals)
            self._publisher.publish_verdict(
                goal_id=f"recovery-bench:{sc.id}",
                requirement=sc.requirement,
                satisfied=False,
                evidence=ExecutionEvidence(),
                capability=sc.capability,
                environment=sc.environment,
                reversible=sc.reversible,
                blocked=sc.blocked,
            )
            # Recovery reacts synchronously on the same thread (kernel bus.publish).
            new = self._proposals[before:]
            if new:
                metrics.proposals += len(new)
                for payload in new:
                    fclass = str(payload.get("failure_class", "unknown"))
                    metrics.by_failure_class[fclass] = (
                        metrics.by_failure_class.get(fclass, 0) + 1
                    )
                    if payload.get("chosen") is not None:
                        metrics.actionable += 1

        return metrics
