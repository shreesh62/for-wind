"""Ch 47 — track federated nodes and their health."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from friday.resources.types import Resource


@dataclass(frozen=True)
class FederatedNode:
    """Ch 47 — a remote node exposing M4 Resource descriptors (never code)."""

    node_id: str
    resources: Tuple[Resource, ...] = ()
    healthy: bool = True


class NodeDirectory:
    """Ch 47 — track federated nodes and their health."""

    def __init__(self) -> None:
        self._nodes: Dict[str, FederatedNode] = {}

    def add(self, node: FederatedNode) -> None:
        """Record (or replace) a node by its ``node_id``."""
        self._nodes[node.node_id] = node

    def remove(self, node_id: str) -> None:
        """Forget a node; a no-op if it was never added."""
        self._nodes.pop(node_id, None)

    def healthy_nodes(self) -> Tuple[FederatedNode, ...]:
        """Return exactly the nodes currently flagged healthy."""
        return tuple(n for n in self._nodes.values() if n.healthy is True)
