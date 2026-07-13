"""Ch 45 — discover and register resources; never assume availability.

The :class:`ResourceRegistry` is the single place the runtime learns which
finite resources exist. It only tracks what has been explicitly registered —
it never invents resources or assumes one is available.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional

from friday.resources.types import Resource, ResourceKind


class ResourceRegistry:
    """Ch 45 — discover and register resources; never assume availability."""

    def __init__(self) -> None:
        self._resources: Dict[str, Resource] = {}

    def register(self, resource: Resource) -> str:
        """Register a resource (overwriting any prior entry with the same id)."""
        self._resources[resource.id] = resource
        return resource.id

    def unregister(self, resource_id: str) -> None:
        """Forget a resource; a no-op if it was never registered."""
        self._resources.pop(resource_id, None)

    def get(self, resource_id: str) -> Optional[Resource]:
        """Return the registered resource, or ``None`` if unknown."""
        return self._resources.get(resource_id)

    def by_kind(self, kind: ResourceKind) -> List[Resource]:
        """Return all registered resources of the given kind."""
        return [r for r in self._resources.values() if r.kind == kind]

    def all(self) -> List[Resource]:
        """Return a stable snapshot of every known resource."""
        return list(self._resources.values())

    def update(self, resource_id: str, **changes: object) -> Optional[Resource]:
        """Replace descriptor fields through the registry mutation boundary."""
        resource = self._resources.get(resource_id)
        if resource is None:
            return None
        updated = replace(resource, **changes)
        self._resources[resource_id] = updated
        return updated
