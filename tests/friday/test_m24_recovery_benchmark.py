"""M24 (activation) — recovery-rate benchmark tests.

Feature: m24-structured-failure-recovery-activation

Proves the recovery benchmark deterministically measures the active loop:
recovery rate, proposal rate, and failure-domain distribution.
"""

from __future__ import annotations

from friday.benchmarks.recovery import (
    RecoveryBenchmark,
    RecoveryMetrics,
    RecoveryScenario,
    default_recovery_scenarios,
)
from friday.kernel.kernel import CognitiveKernel


def _kernel(tmp_path, name="rb"):
    return CognitiveKernel(store_path=str(tmp_path / f"{name}.jsonl"))


def test_default_scenarios_yield_recovery_proposals(tmp_path):
    # Feature: m24-structured-failure-recovery-activation:
    # the default recoverable scenarios all produce actionable recoveries.
    bench = RecoveryBenchmark(_kernel(tmp_path))
    metrics = bench.run()
    assert metrics.total_failures == len(default_recovery_scenarios())
    assert metrics.proposals == metrics.total_failures  # every failure got a proposal
    assert metrics.actionable >= 1
    assert 0.0 <= metrics.recovery_rate <= 1.0
    # Domain distribution is populated and spans multiple domains.
    assert sum(metrics.by_domain.values()) == metrics.total_failures
    assert len(metrics.by_domain) >= 3


def test_metrics_payload_is_json_safe(tmp_path):
    # Feature: m24-structured-failure-recovery-activation.
    import json
    bench = RecoveryBenchmark(_kernel(tmp_path, "rb2"))
    metrics = bench.run()
    json.dumps(metrics.to_payload())
    assert "recovery_rate" in metrics.to_payload()
    assert isinstance(metrics.to_markdown(), str)


def test_run_is_deterministic(tmp_path):
    # Feature: m24-structured-failure-recovery-activation:
    # same scenarios -> identical metrics (no LLM/network/wall-clock dependence).
    m1 = RecoveryBenchmark(_kernel(tmp_path, "det1")).run()
    m2 = RecoveryBenchmark(_kernel(tmp_path, "det2")).run()
    assert m1.to_payload() == m2.to_payload()


def test_empty_scenarios_zero_rate(tmp_path):
    # Feature: m24-structured-failure-recovery-activation:
    # no scenarios -> zero rates, no crash.
    metrics = RecoveryBenchmark(_kernel(tmp_path, "empty")).run(scenarios=())
    assert metrics.total_failures == 0
    assert metrics.recovery_rate == 0.0
    assert metrics.proposal_rate == 0.0


def test_domain_classification_matches_scenarios(tmp_path):
    # Feature: m24-structured-failure-recovery-activation:
    # a single perception-category scenario is counted under 'perception'.
    scenario = RecoveryScenario(
        id="s", requirement="information must be gathered",
        category="target_not_found", capability="research",
    )
    metrics = RecoveryBenchmark(_kernel(tmp_path, "dom")).run(scenarios=(scenario,))
    assert metrics.by_domain.get("perception") == 1
