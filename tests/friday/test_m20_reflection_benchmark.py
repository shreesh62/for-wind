"""M20 (A2.10) — deterministic layered-reflection benchmark tests.

Feature: m20-reflection-v2

Proves the reflection benchmark deterministically measures higher-layer proposal
quality: expected-proposal precision / recall, exact-match rate, and per-type
emission counts over a fixed, hermetic, domain-general scenario set (no LLM /
network / wall-clock / disk I/O).

Validates: Requirements 8.2
"""

from __future__ import annotations

import json

from friday.benchmarks.reflection import (
    PROPOSAL_ARCHITECTURAL,
    PROPOSAL_LONGTERM,
    PROPOSAL_SKILL,
    ReflectionBenchmark,
    ReflectionMetrics,
    ReflectionSample,
    ReflectionScenario,
    default_reflection_scenarios,
)


def test_default_scenarios_emit_expected_proposals():
    # Feature: m20-reflection-v2:
    # every default scenario's expected proposal set is emitted exactly, so
    # precision / recall / exact-match are perfect and each higher layer fires once.
    metrics = ReflectionBenchmark().run()

    assert metrics.total_scenarios == len(default_reflection_scenarios())
    assert metrics.total_scenarios > 0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.exact_match_rate == 1.0
    assert metrics.by_type_emitted.get(PROPOSAL_LONGTERM) == 1
    assert metrics.by_type_emitted.get(PROPOSAL_SKILL) == 1
    assert metrics.by_type_emitted.get(PROPOSAL_ARCHITECTURAL) == 1


def test_metrics_payload_is_json_safe():
    # Feature: m20-reflection-v2:
    # the metrics projection survives json.dumps and markdown is a non-empty str.
    metrics = ReflectionBenchmark().run()

    payload = metrics.to_dict()
    json.dumps(payload)  # must not raise
    assert "precision" in payload
    assert "recall" in payload
    assert "exact_match_rate" in payload
    assert "by_type_emitted" in payload

    md = metrics.to_markdown()
    assert isinstance(md, str)
    assert len(md) > 0


def test_run_is_deterministic():
    # Feature: m20-reflection-v2:
    # same scenarios -> identical metrics (no LLM/network/wall-clock dependence).
    m1 = ReflectionBenchmark().run()
    m2 = ReflectionBenchmark().run()
    assert m1.to_dict() == m2.to_dict()


def test_empty_scenarios_zero_metrics():
    # Feature: m20-reflection-v2:
    # no scenarios -> zero rates, no crash.
    metrics = ReflectionBenchmark(scenarios=()).run()
    assert isinstance(metrics, ReflectionMetrics)
    assert metrics.total_scenarios == 0
    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    assert metrics.exact_match_rate == 0.0


def test_below_threshold_scenario_emits_no_proposals():
    # Feature: m20-reflection-v2:
    # a single below-threshold stream stays silent (no false positives) and counts
    # as an exact match against its empty expected set.
    scenario = ReflectionScenario(
        scenario_id="below-threshold-only",
        samples=tuple(
            ReflectionSample("research", "web", 0.35, 0.5, False) for _ in range(4)
        ),
        expected_proposals=frozenset(),
    )
    metrics = ReflectionBenchmark(scenarios=(scenario,)).run()
    assert metrics.total_scenarios == 1
    assert metrics.true_positives == 0
    assert metrics.false_positives == 0
    assert metrics.false_negatives == 0
    assert metrics.exact_match == 1
    assert metrics.exact_match_rate == 1.0
    assert metrics.by_type_emitted == {}
