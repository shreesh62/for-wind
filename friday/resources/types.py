"""Ch 45 — finite resources with health, availability, and cost.

Models the kinds of finite resources the runtime schedules (compute, memory,
model budgets, browser sessions, input devices, human attention, ...) and a
concrete :class:`Resource` that honours the kernel's ``ResourceContract`` so
the rest of the runtime can ask about a resource's ``name`` and ``health()``
without assuming anything about availability.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from friday.kernel.contracts.resource import ResourceContract


class ResourceKind(str, Enum):
    """Ch 45 — the finite resource categories the runtime can schedule."""

    COMPUTE = "compute"      # cpu/gpu
    MEMORY = "memory"
    NETWORK = "network"
    MODEL = "model"          # an LLM budget
    BROWSER = "browser"      # a browser session (exclusive)
    INPUT = "input"          # mouse/keyboard (exclusive)
    STORAGE = "storage"
    HUMAN = "human"          # user attention (exclusive)


@dataclass
class Resource(ResourceContract):
    """Ch 45 — a finite resource with health, availability, cost."""

    id: str
    kind: ResourceKind
    exclusive: bool                 # only one holder at a time
    cost: float = 0.0               # relative cost per allocation
    healthy: bool = True
    capabilities: Tuple[str, ...] = ()
    permissions: Tuple[str, ...] = ()
    location: str = "local"
    latency_ms: float = 0.0
    reliability: float = 1.0
    availability: float = 1.0
    current_load: float = 0.0
    energy_cost: float = 0.0
    max_parallel_jobs: Optional[int] = None
    owner: Optional[str] = None
    version: str = ""
    confidence: float = 1.0

    def __post_init__(self) -> None:
        """Normalise bounded economics fields without rejecting discovery data."""
        self.cost = max(0.0, float(self.cost))
        self.latency_ms = max(0.0, float(self.latency_ms))
        self.energy_cost = max(0.0, float(self.energy_cost))
        self.reliability = max(0.0, min(1.0, float(self.reliability)))
        self.availability = max(0.0, min(1.0, float(self.availability)))
        self.current_load = max(0.0, min(1.0, float(self.current_load)))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        if self.max_parallel_jobs is not None:
            self.max_parallel_jobs = max(1, int(self.max_parallel_jobs))

    @property
    def name(self) -> str:
        """Contract identity — the resource's stable id."""
        return self.id

    def health(self) -> Dict[str, Any]:
        """Report the resource's current health/availability snapshot."""
        return {
            "id": self.id,
            "kind": self.kind,
            "exclusive": self.exclusive,
            "healthy": self.healthy,
            "cost": self.cost,
            "capabilities": self.capabilities,
            "permissions": self.permissions,
            "location": self.location,
            "latency_ms": self.latency_ms,
            "reliability": self.reliability,
            "availability": self.availability,
            "current_load": self.current_load,
            "energy_cost": self.energy_cost,
            "max_parallel_jobs": self.max_parallel_jobs,
            "owner": self.owner,
            "version": self.version,
            "confidence": self.confidence,
        }
