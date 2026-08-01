"""M19 (A2.7) — deterministic retrieval-router benchmark tests.

Feature: m19-retrieval-router

Proves the retrieval benchmark deterministically measures routing quality:
coverage, correct-tier attribution, and de-duplication over a fixed, hermetic,
domain-general scenario set (no LLM / network / wall-clock / disk I/O).

Validates: Requirements 8.2
"""

from __future__ import annotations

import json

from friday.benchmarks.retrieval import (
    PlantedEntry,
    RetrievalBenchmark,
    RetrievalMetrics,
    RetrievalScenario,
    SyntheticSourceSpec,
    default_retrieval_scenarios,
)
from friday.memory.interfaces import MemoryTier


def test_default_scenarios_retrieve_and_attribute_relevant_items():
    # Feature: m19-retrieval-router:
    # every default scenario's planted relevant item is retrieved, attributed to
    # its planted tier, and the routed output is de-duplication clean.
    metrics = RetrievalBenchmark().run()

    assert metrics.total_scenarios == len(default_retrieval_scenarios())
    assert metrics.total_scenarios > 0
    assert metrics.coverage == 1.0
    assert metrics.correct_tier_rate == 1.0
    assert metrics.dedup_rate == 1.0
    # Every scenario contributes a finite rank (relevant item was actually found).
    assert len(metrics.ranks) == metrics.total_scenarios


def test_metrics_payload_is_json_safe():
    # Feature: m19-retrieval-router:
    # the metrics projection survives json.dumps and markdown is a non-empty str.
    metrics = RetrievalBenchmark().run()

    payload = metrics.to_dict()
    json.dumps(payload)  # must not raise
    assert "coverage" in payload
    assert "correct_tier_rate" in payload
    assert "dedup_rate" in payload

    md = metrics.to_markdown()
    assert isinstance(md, str)
    assert len(md) > 0


def test_run_is_deterministic():
    # Feature: m19-retrieval-router:
    # same scenarios -> identical metrics (no LLM/network/wall-clock dependence).
    m1 = RetrievalBenchmark().run()
    m2 = RetrievalBenchmark().run()
    assert m1.to_dict() == m2.to_dict()


def test_empty_scenarios_zero_metrics():
    # Feature: m19-retrieval-router:
    # no scenarios -> zero rates, no crash.
    metrics = RetrievalBenchmark(scenarios=()).run()
    assert isinstance(metrics, RetrievalMetrics)
    assert metrics.total_scenarios == 0
    assert metrics.coverage == 0.0
    assert metrics.correct_tier_rate == 0.0
    assert metrics.dedup_rate == 0.0
    assert metrics.mean_rank == 0.0


def test_duplicate_entry_id_is_deduplicated_and_attributed():
    # Feature: m19-retrieval-router:
    # a single scenario planting the same entry_id across two procedural sources is
    # de-duplicated cleanly, and the relevant item is retrieved with correct tier.
    scenario = RetrievalScenario(
        scenario_id="dup-check",
        query="steps to bake a simple loaf of bread",
        sources=(
            SyntheticSourceSpec(
                "procedural-a", MemoryTier.PROCEDURAL.value,
                (
                    PlantedEntry(
                        "proc-bread",
                        "steps to bake a simple loaf of bread: mix, knead, rise, bake",
                        "procedural",
                    ),
                ),
            ),
            SyntheticSourceSpec(
                "procedural-b", MemoryTier.PROCEDURAL.value,
                (
                    PlantedEntry(
                        "proc-bread",
                        "steps to bake a simple loaf of bread: mix, knead, rise, bake",
                        "procedural",
                    ),
                ),
            ),
        ),
        relevant_entry_id="proc-bread",
        relevant_tier="procedural",
    )
    metrics = RetrievalBenchmark(scenarios=(scenario,)).run()
    assert metrics.total_scenarios == 1
    assert metrics.coverage == 1.0
    assert metrics.correct_tier_rate == 1.0
    assert metrics.dedup_rate == 1.0


def test_failure_tier_filter_returns_only_failure_items():
    # Feature: m19-retrieval-router:
    # the default failure-filter scenario surfaces its planted FAILURE item under a
    # FAILURE-only tier filter (the competing semantic entry is excluded).
    scenarios = tuple(
        sc for sc in default_retrieval_scenarios() if sc.scenario_id == "failure-filter"
    )
    assert len(scenarios) == 1
    metrics = RetrievalBenchmark(scenarios=scenarios).run()
    assert metrics.total_scenarios == 1
    assert metrics.coverage == 1.0
    assert metrics.correct_tier_rate == 1.0
    assert metrics.by_tier.get("failure") == 1
