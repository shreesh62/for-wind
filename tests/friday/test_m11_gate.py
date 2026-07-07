"""M11 gate test — the defining constraint of capability evolution.

A capability enters the registry ONLY through sandbox → benchmark → promote; a
regressing candidate is rejected and (given a recorded snapshot) rolled back; and
one goal graph's resource requirement is satisfiable by a federated node. The M11
event sequence is deterministic under identical inputs.

Validates: Requirements 1.4, 2.2, 2.3, 4.1
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from dataclasses import dataclass
from typing import Any, List, Optional

from friday.benchmarks.suite import BenchmarkRunner, BenchmarkScenario, BenchmarkSuite
from friday.capabilities.registry import CapabilityRegistry
from friday.evolution.lifecycle import CapabilityLifecycle
from friday.evolution.pipeline import PromotionOutcome, PromotionPipeline
from friday.evolution.rollback import RollbackManager
from friday.federation.directory import FederatedNode, NodeDirectory
from friday.federation.federation import ResourceFederation
from friday.resources.registry import ResourceRegistry
from friday.resources.types import Resource, ResourceKind


@dataclass
class _Candidate:
    proposed_id: str = "explored.click.n1"
    affordance: Optional[Any] = None
    procedure: Optional[Any] = None
    evidence_count: int = 0
    confidence: float = 0.9


def _suite() -> BenchmarkSuite:
    suite = BenchmarkSuite()
    suite.add(BenchmarkScenario(id="0", description="smoke", weight=1.0))
    return suite


def _pipeline():
    registry = CapabilityRegistry()
    return registry, PromotionPipeline(
        registry, CapabilityLifecycle(), BenchmarkRunner(), min_benchmark_score=0.6
    )


# --------------------------------------------------------------------------- #
# Gate 1: promotion only via the benchmark pipeline
# --------------------------------------------------------------------------- #
def test_promotion_only_via_benchmark():
    registry, pipeline = _pipeline()

    # A failing candidate is rejected and never registered.
    rejected = pipeline.submit(_Candidate(), suite=_suite(), evaluate=lambda s: False)
    assert rejected.outcome is PromotionOutcome.REJECTED
    assert registry.get("explored.click.n1") is None

    # A passing candidate is promoted and registered.
    promoted = pipeline.submit(_Candidate(), suite=_suite(), evaluate=lambda s: True)
    assert promoted.outcome is PromotionOutcome.PROMOTED
    assert registry.get("explored.click.n1") is not None


# --------------------------------------------------------------------------- #
# Gate 2: regressing candidate rejected; rollback restores last-known-good
# --------------------------------------------------------------------------- #
def test_regressing_candidate_rejected_and_rollback():
    registry, pipeline = _pipeline()
    rollback = RollbackManager()

    # Record a known-good snapshot, then promote an incumbent.
    rollback.record_stable("explored.click.n1", "v1")
    first = pipeline.submit(_Candidate(), suite=_suite(), evaluate=lambda s: True)
    assert first.outcome is PromotionOutcome.PROMOTED

    # A regressing candidate (score below the incumbent's 0.9) is rejected.
    regressing = pipeline.submit(
        _Candidate(),
        suite=_suite(),
        evaluate=lambda s: False,
        incumbent_score=0.9,
    )
    assert regressing.outcome is PromotionOutcome.REJECTED

    # The last-known-good snapshot is still restorable.
    assert rollback.can_rollback("explored.click.n1") is True
    assert rollback.rollback("explored.click.n1") == "v1"


# --------------------------------------------------------------------------- #
# Gate 3: a federated node satisfies a resource requirement
# --------------------------------------------------------------------------- #
def test_federated_resource_satisfies_requirement():
    registry = ResourceRegistry()
    federation = ResourceFederation(registry, NodeDirectory())

    assert registry.by_kind(ResourceKind.COMPUTE) == []

    federation.join(
        FederatedNode(
            "nodeA",
            (Resource(id="gpu0", kind=ResourceKind.COMPUTE, exclusive=False),),
        )
    )

    compute = registry.by_kind(ResourceKind.COMPUTE)
    assert len(compute) == 1
    assert compute[0].id == "nodeA::gpu0"


# --------------------------------------------------------------------------- #
# Gate 4: determinism — identical inputs produce identical ordered outcomes
# --------------------------------------------------------------------------- #
def _run_sequence() -> List[PromotionOutcome]:
    _registry, pipeline = _pipeline()
    outcomes: List[PromotionOutcome] = []
    outcomes.append(
        pipeline.submit(_Candidate(), suite=_suite(), evaluate=lambda s: False).outcome
    )
    outcomes.append(
        pipeline.submit(_Candidate(), suite=_suite(), evaluate=lambda s: True).outcome
    )
    return outcomes


def test_determinism():
    assert _run_sequence() == _run_sequence()
    assert _run_sequence() == [
        PromotionOutcome.REJECTED,
        PromotionOutcome.PROMOTED,
    ]
