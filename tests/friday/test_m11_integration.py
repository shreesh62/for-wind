"""M11 — Kernel-event integration test (promotion, plugin, federation).

Wires a real ``CognitiveKernel`` and drives the three M11 flows through it,
asserting the expected events land on the bus and the registries change:

- a CapabilityCandidate flows through the PromotionPipeline (passing benchmark)
  and emits ``capability.promoted``;
- a plugin manifest flows loader → sandbox → pipeline and is promoted;
- a FederatedNode joins and its namespaced resources appear in the
  ResourceRegistry, emitting ``federation.node_joined``.

Runs under ``FRIDAY_DRY_RUN=1``.

Requirements: 2.5, 3.1, 4.1
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from dataclasses import dataclass
from typing import Any, List, Optional

from friday.benchmarks.suite import BenchmarkRunner, BenchmarkScenario, BenchmarkSuite
from friday.capabilities.registry import CapabilityRegistry
from friday.evolution.lifecycle import CapabilityLifecycle
from friday.evolution.pipeline import PromotionOutcome, PromotionPipeline
from friday.events.store import EventStore
from friday.federation.directory import FederatedNode, NodeDirectory
from friday.federation.federation import ResourceFederation
from friday.kernel.kernel import CognitiveKernel
from friday.plugins.loader import PluginLoader
from friday.plugins.manifest import LoadedPlugin, PluginManifest
from friday.plugins.sandbox import PluginSandbox
from friday.resources.registry import ResourceRegistry
from friday.resources.types import Resource, ResourceKind


@dataclass
class _Candidate:
    proposed_id: str = "explored.click.n1"
    affordance: Optional[Any] = None
    procedure: Optional[Any] = None
    evidence_count: int = 0
    confidence: float = 0.9


def _kernel(tmp_path) -> CognitiveKernel:
    store = EventStore(str(tmp_path / "events.jsonl"))
    return CognitiveKernel(event_store=store)


def _one_scenario_suite() -> BenchmarkSuite:
    suite = BenchmarkSuite()
    suite.add(BenchmarkScenario(id="0", description="smoke", weight=1.0))
    return suite


def test_promotion_flow_emits_capability_promoted(tmp_path):
    kernel = _kernel(tmp_path)
    seen: List[str] = []
    kernel.subscribe("capability.*", lambda e: seen.append(e.event_type))

    registry = CapabilityRegistry()
    pipeline = PromotionPipeline(registry, CapabilityLifecycle(), BenchmarkRunner())
    pipeline.attach(kernel)

    result = pipeline.submit(
        _Candidate(), suite=_one_scenario_suite(), evaluate=lambda s: True
    )

    assert result.outcome is PromotionOutcome.PROMOTED
    assert registry.get("explored.click.n1") is not None
    assert "capability.promoted" in seen


def test_plugin_flow_promotes_a_declared_capability(tmp_path):
    kernel = _kernel(tmp_path)
    seen: List[str] = []
    kernel.subscribe("capability.*", lambda e: seen.append(e.event_type))

    registry = CapabilityRegistry()
    pipeline = PromotionPipeline(registry, CapabilityLifecycle(), BenchmarkRunner())
    pipeline.attach(kernel)

    manifest = PluginManifest(
        name="p", version="1", author="a",
        capabilities=("click",), permissions=("read",), signature="sig",
    )
    loaded = PluginLoader(PluginSandbox()).load(manifest)
    assert isinstance(loaded, LoadedPlugin)

    candidate = loaded.candidates[0]
    result = pipeline.submit(
        candidate, suite=_one_scenario_suite(), evaluate=lambda s: True
    )

    assert result.outcome is PromotionOutcome.PROMOTED
    assert registry.get(candidate.proposed_id) is not None
    assert "capability.promoted" in seen


def test_federation_flow_registers_namespaced_resource(tmp_path):
    kernel = _kernel(tmp_path)
    seen: List[str] = []
    kernel.subscribe("federation.*", lambda e: seen.append(e.event_type))

    registry = ResourceRegistry()
    federation = ResourceFederation(registry, NodeDirectory())
    federation.attach(kernel)

    federation.join(
        FederatedNode(
            "nodeA",
            (Resource(id="gpu0", kind=ResourceKind.COMPUTE, exclusive=False),),
        )
    )

    compute = registry.by_kind(ResourceKind.COMPUTE)
    assert any(r.id == "nodeA::gpu0" for r in compute)
    assert "federation.node_joined" in seen
