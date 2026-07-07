"""Ch 47 — federate remote node resources into the local ResourceRegistry."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List

from friday.events.event import make_event
from friday.federation.directory import FederatedNode, NodeDirectory


class ResourceFederation:
    """Ch 47 — federate remote node resources into the local ResourceRegistry."""

    def __init__(self, registry: Any, directory: NodeDirectory) -> None:
        self._registry = registry
        self._directory = directory
        self._kernel: Any = None
        # node_id -> the namespaced resource ids registered for that node.
        self._registered: Dict[str, List[str]] = {}

    def attach(self, kernel: Any) -> None:
        """Wire the kernel so join/leave can emit federation events."""
        self._kernel = kernel

    def join(self, node: FederatedNode) -> None:
        """Register the node's resources (namespaced by node_id) and emit federation.node_joined."""
        # Leave-then-join so ids are never double-registered for the same node.
        if node.node_id in self._registered:
            self.leave(node.node_id)

        self._directory.add(node)

        registered_ids: List[str] = []
        for resource in node.resources:
            namespaced_id = f"{node.node_id}::{resource.id}"
            self._registry.register(replace(resource, id=namespaced_id))
            registered_ids.append(namespaced_id)
        self._registered[node.node_id] = registered_ids

        self._emit(
            "federation.node_joined",
            {"node_id": node.node_id, "resource_count": len(node.resources)},
        )

    def leave(self, node_id: str) -> None:
        """Unregister the node's resources and emit federation.node_left."""
        for namespaced_id in self._registered.pop(node_id, []):
            self._registry.unregister(namespaced_id)
        self._directory.remove(node_id)

        self._emit("federation.node_left", {"node_id": node_id})

    # --- kernel wiring -----------------------------------------------------

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish a federation event via the kernel; never raises into a tick loop."""
        if self._kernel is None:
            return
        try:
            self._kernel.publish_event(
                make_event(
                    event_type=event_type,
                    source="federation",
                    logical_time=self._next_logical_time(),
                    payload=payload,
                )
            )
        except Exception:  # noqa: BLE001 — emission must never break federation
            return

    def _next_logical_time(self) -> int:
        """Best-effort next logical time from kernel health; defaults to 1."""
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:  # noqa: BLE001 — health must never break emission
            return 1
