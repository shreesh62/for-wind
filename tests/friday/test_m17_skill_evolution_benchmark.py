"""M17 (A2.5) — deterministic skill-evolution candidate-emission benchmark tests.

Feature: m17-skill-evolution

Proves the skill-evolution benchmark deterministically measures candidate-emission
quality: precision / recall, exact-match rate, and total candidate emissions over a
fixed, hermetic, domain-general scenario set (no LLM / network / wall-clock / disk
I/O). The dual-signal rule is exercised end to end: dual-signal skills emit exactly
one candidate, single-signal and rejected-then-skill streams stay silent.

Validates: Requirements 6.2
"""

from __future__ import annotations

import json

from friday.benchmarks.skill_evolution import (
    SIGNAL_REJECTED,
    SIGNAL_SKILL,
    SIGNAL_VALIDATED,
    SkillEvent,
    SkillEvolutionBenchmark,
    SkillMetrics,
    SkillScenario,
    default_skill_scenarios,
)


def test_default_scenarios_emit_expected_candidates():
    # Feature: m17-skill-evolution:
    # every default scenario's expected candidate set is emitted exactly, so
    # precision / recall / exact-match are perfect, and the total candidate
    # emissions equal the number of expected dual-signal skills (1 + 2 = 3).
    metrics = SkillEvolutionBenchmark().run()

    assert metrics.total_scenarios == len(default_skill_scenarios())
    assert metrics.total_scenarios > 0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.exact_match_rate == 1.0

    expected_emissions = sum(
        len(sc.expected_candidates) for sc in default_skill_scenarios()
    )
    assert expected_emissions == 3
    assert metrics.total_emissions == expected_emissions


def test_metrics_payload_is_json_safe():
    # Feature: m17-skill-evolution:
    # the metrics projection survives json.dumps and markdown is a non-empty str.
    metrics = SkillEvolutionBenchmark().run()

    payload = metrics.to_dict()
    json.dumps(payload)  # must not raise
    assert "precision" in payload
    assert "recall" in payload
    assert "exact_match_rate" in payload
    assert "total_emissions" in payload

    md = metrics.to_markdown()
    assert isinstance(md, str)
    assert len(md) > 0


def test_run_is_deterministic():
    # Feature: m17-skill-evolution:
    # same scenarios -> identical metrics (no LLM/network/wall-clock dependence).
    m1 = SkillEvolutionBenchmark().run()
    m2 = SkillEvolutionBenchmark().run()
    assert m1.to_dict() == m2.to_dict()


def test_empty_scenarios_zero_metrics():
    # Feature: m17-skill-evolution:
    # no scenarios -> zero rates, no crash.
    metrics = SkillEvolutionBenchmark(scenarios=()).run()
    assert isinstance(metrics, SkillMetrics)
    assert metrics.total_scenarios == 0
    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    assert metrics.exact_match_rate == 0.0


def test_single_signal_and_rejected_streams_emit_no_candidate():
    # Feature: m17-skill-evolution:
    # a single-signal stream (only learning.validated) emits no candidate (no false
    # positives), and a validated-then-rejected-then-skill stream stays silent
    # because the rejection disqualifies the later skill signal.
    single_signal = SkillScenario(
        scenario_id="single-signal-only",
        events=(SkillEvent(SIGNAL_VALIDATED, "research", "web"),),
        expected_candidates=frozenset(),
    )
    rejected_then_skill = SkillScenario(
        scenario_id="rejected-then-skill",
        events=(
            SkillEvent(SIGNAL_VALIDATED, "coding", "desktop"),
            SkillEvent(SIGNAL_REJECTED, "coding", "desktop"),
            SkillEvent(SIGNAL_SKILL, "coding", "desktop"),
        ),
        expected_candidates=frozenset(),
    )

    metrics = SkillEvolutionBenchmark(
        scenarios=(single_signal, rejected_then_skill)
    ).run()

    assert metrics.total_scenarios == 2
    assert metrics.total_emissions == 0
    assert metrics.true_positives == 0
    assert metrics.false_positives == 0
    assert metrics.false_negatives == 0
    assert metrics.exact_match == 2
    assert metrics.exact_match_rate == 1.0
