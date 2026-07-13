"""Ch 45-48 - deterministic resource economics contracts.

These value objects keep policy, demand, budget, reservations, and failover
outcomes independent from any concrete browser, model, device, or provider.
They are intentionally clock-free so allocation decisions are replayable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from friday.resources.types import ResourceKind


@dataclass(frozen=True)
class ResourceBudget:
    """Concurrent resource commitments a holder may reserve."""

    max_cost: Optional[float] = None
    max_energy_cost: Optional[float] = None

    def __post_init__(self) -> None:
        for value in (self.max_cost, self.max_energy_cost):
            if value is not None and value < 0:
                raise ValueError("resource budget values must be non-negative")


@dataclass(frozen=True)
class BudgetStatus:
    """Current reserved amounts relative to one holder's budget."""

    holder: str
    reserved_cost: float
    reserved_energy_cost: float
    budget: ResourceBudget

    @property
    def within_budget(self) -> bool:
        return (
            (self.budget.max_cost is None or self.reserved_cost <= self.budget.max_cost)
            and (
                self.budget.max_energy_cost is None
                or self.reserved_energy_cost <= self.budget.max_energy_cost
            )
        )


@dataclass(frozen=True)
class ResourceRequest:
    """A domain-agnostic request for a single allocation."""

    holder: str
    kind: Optional[ResourceKind] = None
    capability: str = ""
    required_permissions: Tuple[str, ...] = ()
    priority: int = 0
    max_latency_ms: Optional[float] = None
    local_only: bool = False
    allow_degrade: bool = True
    fallback_kinds: Tuple[ResourceKind, ...] = ()

    def __post_init__(self) -> None:
        if not self.holder:
            raise ValueError("resource request holder is required")
        object.__setattr__(self, "priority", max(0, min(10, int(self.priority))))
        if self.max_latency_ms is not None and self.max_latency_ms < 0:
            raise ValueError("max_latency_ms must be non-negative")


@dataclass(frozen=True)
class ResourcePolicy:
    """User-directed trade-offs for ranking usable resources."""

    prefer_local: bool = False
    allow_paid: bool = True
    reliability_weight: float = 1.0
    availability_weight: float = 1.0
    cost_weight: float = 1.0
    energy_weight: float = 0.25
    latency_weight: float = 0.001
    load_weight: float = 1.0

    def __post_init__(self) -> None:
        for value in (
            self.reliability_weight,
            self.availability_weight,
            self.cost_weight,
            self.energy_weight,
            self.latency_weight,
            self.load_weight,
        ):
            if value < 0:
                raise ValueError("resource policy weights must be non-negative")


@dataclass(frozen=True)
class ResourceReservation:
    """An auditable accounting record for a granted allocation."""

    id: str
    resource_id: str
    holder: str
    request: ResourceRequest
    policy: ResourcePolicy
    cost: float
    energy_cost: float
    sequence: int


@dataclass(frozen=True)
class ReallocationResult:
    """Result of replacing, degrading, or queuing an interrupted allocation."""

    previous_reservation_id: str
    previous_resource_id: str
    holder: str
    outcome: str
    replacement_reservation_id: str = ""
    replacement_resource_id: str = ""
    reason: str = ""
