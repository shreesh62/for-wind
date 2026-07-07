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
from typing import Any, Dict

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
        }
