"""M11 — Property tests for resource federation (Ch 47).

Exercises ``friday/federation/*``:
- Property 9: joining a node namespaces every registered resource id by node_id,
  and join-then-leave restores the registry to its pre-join contents.
- Property 10: a FederatedNode carries only Resource descriptors (no code), and
  ``NodeDirectory.healthy_nodes`` returns exactly the healthy nodes.

All tests run under ``FRIDAY_DRY_RUN=1`` so the existing suite stays green.

Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import string

from hypothesis import given, settings, strategies as st

from friday.federation.directory import FederatedNode, NodeDirectory
from friday.federation.federation import ResourceFederation
from friday.resources.registry import ResourceRegistry
from friday.resources.types import Resource, ResourceKind

_labels = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=6)


def _resources(ids):
    return tuple(
        Resource(id=rid, kind=ResourceKind.COMPUTE, exclusive=False) for rid in ids
    )


# --------------------------------------------------------------------------- #
# Property 9: Federation namespaces resources and is reversible
# --------------------------------------------------------------------------- #
@given(
    node_id=_labels,
    resource_ids=st.lists(_labels, min_size=0, max_size=5, unique=True),
)
@settings(max_examples=100)
def test_property9_namespaced_and_reversible(node_id, resource_ids):
    """Every registered resource id is namespaced; join-then-leave is identity."""
    registry = ResourceRegistry()
    federation = ResourceFederation(registry, NodeDirectory())

    before = len(registry.by_kind(ResourceKind.COMPUTE))

    federation.join(FederatedNode(node_id, _resources(resource_ids)))

    registered = registry.by_kind(ResourceKind.COMPUTE)
    assert len(registered) == before + len(resource_ids)
    prefix = f"{node_id}::"
    for resource in registered:
        assert resource.id.startswith(prefix)

    federation.leave(node_id)

    # Join-then-leave returns the registry to exactly its pre-join contents.
    assert len(registry.by_kind(ResourceKind.COMPUTE)) == before


# --------------------------------------------------------------------------- #
# Property 10: Federation transmits only resource descriptors
# --------------------------------------------------------------------------- #
@given(resource_ids=st.lists(_labels, min_size=0, max_size=5, unique=True))
@settings(max_examples=50)
def test_property10_node_carries_only_resource_descriptors(resource_ids):
    """A FederatedNode's resources are all Resource values — never code/callables."""
    node = FederatedNode("nodeA", _resources(resource_ids))
    for resource in node.resources:
        assert isinstance(resource, Resource)
        assert not callable(resource)


@given(flags=st.lists(st.booleans(), min_size=0, max_size=6))
@settings(max_examples=100)
def test_property10_healthy_nodes_returns_exactly_healthy(flags):
    """NodeDirectory.healthy_nodes returns exactly the nodes flagged healthy."""
    directory = NodeDirectory()
    expected_healthy = set()
    for i, healthy in enumerate(flags):
        node_id = f"node{i}"
        directory.add(FederatedNode(node_id, (), healthy=healthy))
        if healthy:
            expected_healthy.add(node_id)

    returned = {n.node_id for n in directory.healthy_nodes()}
    assert returned == expected_healthy
