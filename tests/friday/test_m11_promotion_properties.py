"""M11 — Property test for benchmark-gated promotion (Ch 27).

Exercises ``friday/evolution/pipeline.py``: a candidate is promoted through the
``PromotionPipeline`` ONLY when its benchmark score meets the floor, and the
registry capability count changes only on a real promotion.

- Property 3: promotion requires a passing benchmark — PROMOTED iff
  ``score >= min_benchmark_score``; otherwise REJECTED with the registry
  untouched.

All tests run under ``FRIDAY_DRY_RUN=1`` so the existing suite stays green.

Validates: Requirements 2.1, 2.2
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from dataclasses import dataclass
from typing import Any, Optional

from hypothesis import given, settings, strategies as st

from friday.benchmarks.suite import BenchmarkRunner, BenchmarkScenario, BenchmarkSuite
from friday.capabilities.registry import CapabilityRegistry
from friday.evolution.lifecycle import CapabilityLifecycle
from friday.evolution.pipeline import PromotionOutcome, PromotionPipeline


@dataclass
class _Candidate:
    """A minimal CapabilityCandidate-shaped value (duck-typed to the M7 shape)."""

    proposed_id: str = "explored.click.n1"
    affordance: Optional[Any] = None
    procedure: Optional[Any] = None
    evidence_count: int = 0
    confidence: float = 0.9


def _pipeline(min_score: float = 0.6) -> PromotionPipeline:
    return PromotionPipeline(
        CapabilityRegistry(),
        CapabilityLifecycle(),
        BenchmarkRunner(),
        min_benchmark_score=min_score,
    )


def _suite(n: int) -> BenchmarkSuite:
    suite = BenchmarkSuite()
    for i in range(n):
        suite.add(BenchmarkScenario(id=str(i), description=f"s{i}", weight=1.0))
    return suite


# --------------------------------------------------------------------------- #
# Property 3: Promotion requires a passing benchmark
# --------------------------------------------------------------------------- #
def test_property3_passing_benchmark_promotes_and_registers():
    pipeline = _pipeline()
    reg = pipeline._registry  # the registry this pipeline promotes into
    before = reg.capability_count

    result = pipeline.submit(_Candidate(), suite=_suite(1), evaluate=lambda s: True)

    assert result.outcome is PromotionOutcome.PROMOTED
    assert reg.capability_count == before + 1
    assert reg.get("explored.click.n1") is not None


def test_property3_failing_benchmark_rejects_and_leaves_registry_unchanged():
    pipeline = _pipeline()
    reg = pipeline._registry
    before = reg.capability_count

    result = pipeline.submit(_Candidate(), suite=_suite(1), evaluate=lambda s: False)

    assert result.outcome is PromotionOutcome.REJECTED
    assert reg.capability_count == before


@given(
    total=st.integers(min_value=1, max_value=6),
    passing=st.integers(min_value=0, max_value=6),
)
@settings(max_examples=100)
def test_property3_promoted_iff_score_meets_floor(total, passing):
    """PROMOTED iff the weighted pass ratio >= min_benchmark_score (0.6)."""
    passing = min(passing, total)
    pipeline = _pipeline(0.6)
    suite = _suite(total)

    # First `passing` scenario ids pass; the rest fail.
    passing_ids = {str(i) for i in range(passing)}

    result = pipeline.submit(
        _Candidate(),
        suite=suite,
        evaluate=lambda s: s.id in passing_ids,
    )

    score = passing / total
    if score >= 0.6:
        assert result.outcome is PromotionOutcome.PROMOTED
    else:
        assert result.outcome is PromotionOutcome.REJECTED


def test_property3_no_benchmark_evidence_rejects():
    """No suite / evaluate ⇒ no evidence of competence ⇒ REJECTED (never promoted)."""
    pipeline = _pipeline()
    result = pipeline.submit(_Candidate())
    assert result.outcome is PromotionOutcome.REJECTED
