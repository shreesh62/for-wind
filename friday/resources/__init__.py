"""Ch 45-46 — finite resources: modeling, registration, and scheduling.

Re-exports the public resource surface: the `Resource`/`ResourceKind` value
model, the `ResourceRegistry` (discover/register), and the `ResourceManager`
(allocate/release; exclusive resources never double-allocated). Resources are
allocated, never assumed (the 7th law, Ch 45.x).
"""

from friday.resources.registry import ResourceRegistry
from friday.resources.scheduler import Allocation, ResourceManager
from friday.resources.types import Resource, ResourceKind

__all__ = [
    "Resource",
    "ResourceKind",
    "ResourceRegistry",
    "ResourceManager",
    "Allocation",
]
