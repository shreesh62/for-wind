"""Ch 46/48 - allocate, budget, queue, and reallocate finite resources.

``ResourceManager`` remains the sole authority for resource acquisition.  Its
legacy ``allocate``/``release`` API preserves M4 semantics; Resource Manager
v2 adds deterministic policy-aware selection, reservation accounting, bounded
parallelism, and failover without teaching callers about particular providers.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from friday.events.event import make_event
from friday.resources.economics import (
    BudgetStatus,
    ReallocationResult,
    ResourceBudget,
    ResourcePolicy,
    ResourceRequest,
    ResourceReservation,
)
from friday.resources.registry import ResourceRegistry
from friday.resources.types import Resource


@dataclass(frozen=True)
class Allocation:
    """The outcome of an allocation request.

    The first four fields are the stable M4 contract.  The defaulted v2 fields
    add traceability for economic reservations without changing old callers.
    """

    resource_id: str
    holder: str
    granted: bool
    reason: str
    reservation_id: str = ""
    score: float = 0.0
    degraded: bool = False
    queued: bool = False


class ResourceManager:
    """Single authority for allocation, economics, queues, and failover."""

    def __init__(self, registry: ResourceRegistry) -> None:
        self._registry = registry
        # M4 allocation state.
        self._holders: Dict[str, str] = {}
        self._shared: Dict[str, Set[str]] = {}
        self._wait: Dict[str, List[str]] = {}
        self._kernel: Any = None

        # M18 accounting and scheduler state.  Sequence values, rather than a
        # wall clock or UUID, make decisions and reservation IDs replay-safe.
        self._budgets: Dict[str, ResourceBudget] = {}
        self._reservations: Dict[str, ResourceReservation] = {}
        self._reserved_cost: Dict[str, float] = {}
        self._reserved_energy: Dict[str, float] = {}
        self._pending: Dict[str, Tuple[ResourceRequest, ResourcePolicy]] = {}
        self._sequence = 0

    # ------------------------------------------------------------------
    # M4-compatible allocation surface
    # ------------------------------------------------------------------
    def allocate(self, resource_id: str, *, holder: str) -> Allocation:
        """Allocate ``resource_id`` to ``holder``; fail safe if unavailable."""
        resource = self._registry.get(resource_id)
        if resource is None:
            return Allocation(resource_id, holder, granted=False, reason="unknown")
        if not resource.healthy:
            return Allocation(resource_id, holder, granted=False, reason="unhealthy")
        if resource.availability <= 0.0:
            return Allocation(resource_id, holder, granted=False, reason="unavailable")

        if not resource.exclusive:
            holders = self._shared.setdefault(resource_id, set())
            if (
                resource.max_parallel_jobs is not None
                and holder not in holders
                and len(holders) >= resource.max_parallel_jobs
            ):
                return Allocation(resource_id, holder, granted=False, reason="busy")
            holders.add(holder)
            return Allocation(resource_id, holder, granted=True, reason="shared")

        current = self._holders.get(resource_id)
        if current is None:
            self._holders[resource_id] = holder
            return Allocation(resource_id, holder, granted=True, reason="granted")
        if current == holder:
            return Allocation(resource_id, holder, granted=True, reason="held")

        waiters = self._wait.setdefault(resource_id, [])
        if holder not in waiters:
            waiters.append(holder)
        return Allocation(resource_id, holder, granted=False, reason="busy")

    def release(self, resource_id: str, *, holder: str) -> bool:
        """Release a resource held by ``holder`` and remove its reservations."""
        resource = self._registry.get(resource_id)

        if resource is not None and resource.exclusive:
            if self._holders.get(resource_id) == holder:
                del self._holders[resource_id]
                self._forget_reservations(resource_id, holder)
                return True
            return False

        holders = self._shared.get(resource_id)
        if holders is not None and holder in holders:
            holders.discard(holder)
            if not holders:
                del self._shared[resource_id]
            self._forget_reservations(resource_id, holder)
            return True
        return False

    def holder_of(self, resource_id: str) -> Optional[str]:
        """Return the current exclusive holder of ``resource_id`` (or None)."""
        return self._holders.get(resource_id)

    def next_waiter(self, resource_id: str) -> Optional[str]:
        """Peek the FIFO head of the legacy exclusive-resource wait list."""
        waiters = self._wait.get(resource_id)
        return waiters[0] if waiters else None

    # ------------------------------------------------------------------
    # Resource Manager v2: economics and scheduling
    # ------------------------------------------------------------------
    def set_budget(self, holder: str, budget: ResourceBudget) -> None:
        """Set the concurrent commitment budget for ``holder``."""
        if not holder:
            raise ValueError("budget holder is required")
        self._budgets[holder] = budget

    def budget_status(self, holder: str) -> BudgetStatus:
        """Return an immutable accounting snapshot for one holder."""
        return BudgetStatus(
            holder=holder,
            reserved_cost=self._reserved_cost.get(holder, 0.0),
            reserved_energy_cost=self._reserved_energy.get(holder, 0.0),
            budget=self._budgets.get(holder, ResourceBudget()),
        )

    @property
    def reservations(self) -> Tuple[ResourceReservation, ...]:
        """Reservations in stable creation order for auditing and replay."""
        return tuple(sorted(self._reservations.values(), key=lambda item: item.sequence))

    @property
    def pending_requests(self) -> Tuple[ResourceRequest, ...]:
        """Queued requests, ordered by priority and then arrival sequence."""
        queued = []
        for request_id, (request, _policy) in self._pending.items():
            sequence = self._sequence_from_id(request_id)
            queued.append((request, sequence))
        queued.sort(key=lambda item: (-item[0].priority, item[1]))
        return tuple(request for request, _sequence in queued)

    def allocate_best(
        self,
        request: ResourceRequest,
        *,
        policy: Optional[ResourcePolicy] = None,
        queue_on_failure: bool = True,
        exclude_resource_ids: Iterable[str] = (),
    ) -> Allocation:
        """Rank compatible resources and reserve the best budget-safe choice.

        A normal request tries its requested kind first.  If it permits
        degradation, explicitly listed fallback kinds are considered only after
        every primary candidate is unavailable.  This makes a degraded outcome
        visible to the caller rather than silently changing semantics.
        """
        policy = policy or ResourcePolicy()
        excluded = set(exclude_resource_ids)
        primary = self._rank_candidates(request, policy, excluded)
        allocation, reason = self._attempt(primary, request, policy, degraded=False)
        if allocation is not None:
            return allocation

        if request.allow_degrade and request.fallback_kinds:
            fallback_candidates: List[Tuple[Resource, float]] = []
            for kind in request.fallback_kinds:
                fallback_request = replace(request, kind=kind)
                fallback_candidates.extend(
                    self._rank_candidates(fallback_request, policy, excluded)
                )
            fallback_candidates.sort(key=lambda pair: (-pair[1], pair[0].id))
            allocation, fallback_reason = self._attempt(
                fallback_candidates, request, policy, degraded=True
            )
            if allocation is not None:
                return allocation
            if fallback_reason == "budget_exceeded":
                reason = fallback_reason

        if queue_on_failure:
            return self._queue(request, policy, reason)
        return Allocation("", request.holder, granted=False, reason=reason)

    def process_queue(self) -> List[Allocation]:
        """Attempt queued work by priority, retaining requests still blocked."""
        ordered = list(self._pending.items())
        ordered.sort(
            key=lambda item: (-item[1][0].priority, self._sequence_from_id(item[0]))
        )
        self._pending.clear()
        granted: List[Allocation] = []
        for request_id, (request, policy) in ordered:
            allocation = self.allocate_best(
                request, policy=policy, queue_on_failure=False
            )
            if allocation.granted:
                granted.append(allocation)
            else:
                self._pending[request_id] = (request, policy)
        return granted

    def release_reservation(self, reservation_id: str) -> bool:
        """Release exactly one economic reservation, if it is still active."""
        reservation = self._reservations.get(reservation_id)
        if reservation is None:
            return False
        released = self.release(reservation.resource_id, holder=reservation.holder)
        if released:
            return True
        # A resource can disappear from a federated registry before its holder
        # receives a release callback.  Accounting must still converge.
        self._forget_reservation(reservation.resource_id, reservation.holder)
        return True

    def mark_unavailable(
        self, resource_id: str, *, reason: str = "unavailable"
    ) -> List[ReallocationResult]:
        """Fail a resource and deterministically substitute, degrade, or queue.

        Only reservations that actually depended on the failed resource are
        touched.  Unrelated resources and legacy non-economic allocations keep
        their state.  The original resource is excluded from each retry so a
        stale descriptor can never be selected again during the failover pass.
        """
        if self._registry.update(resource_id, healthy=False, availability=0.0) is None:
            return []

        interrupted = [
            reservation
            for reservation in self.reservations
            if reservation.resource_id == resource_id
        ]
        outcomes: List[ReallocationResult] = []
        for reservation in interrupted:
            self.release_reservation(reservation.id)
            allocation = self.allocate_best(
                reservation.request,
                policy=reservation.policy,
                exclude_resource_ids=(resource_id,),
                queue_on_failure=True,
            )
            if allocation.granted:
                outcome = "degraded" if allocation.degraded else "reallocated"
                result = ReallocationResult(
                    previous_reservation_id=reservation.id,
                    previous_resource_id=resource_id,
                    holder=reservation.holder,
                    outcome=outcome,
                    replacement_reservation_id=allocation.reservation_id,
                    replacement_resource_id=allocation.resource_id,
                    reason=reason,
                )
            else:
                result = ReallocationResult(
                    previous_reservation_id=reservation.id,
                    previous_resource_id=resource_id,
                    holder=reservation.holder,
                    outcome="queued" if allocation.queued else "unavailable",
                    reason=allocation.reason,
                )
            outcomes.append(result)
            self._emit(
                "resource.reallocated",
                {
                    "previous_resource_id": resource_id,
                    "holder": reservation.holder,
                    "outcome": result.outcome,
                    "replacement_resource_id": result.replacement_resource_id,
                    "reason": result.reason,
                },
            )
        return outcomes

    # ------------------------------------------------------------------
    # Kernel wiring
    # ------------------------------------------------------------------
    def attach(self, kernel: Any) -> None:
        """Subscribe to resource requests, releases, and availability changes."""
        self._kernel = kernel
        kernel.subscribe("resource.requested", self._on_resource_requested)
        kernel.subscribe("resource.released", self._on_resource_released)
        kernel.subscribe("resource.unavailable", self._on_resource_unavailable)

    def _on_resource_requested(self, event: Any) -> None:
        """Service the stable direct-resource event contract defensively."""
        try:
            payload = getattr(event, "payload", {}) or {}
            resource_id = payload.get("resource_id")
            holder = payload.get("holder")
            if not resource_id or not holder:
                return
            allocation = self.allocate(resource_id, holder=holder)
            if allocation.granted:
                self._emit("resource.allocated", {"resource_id": resource_id, "holder": holder})
            else:
                self._emit(
                    "resource.denied",
                    {"resource_id": resource_id, "holder": holder, "reason": allocation.reason},
                )
        except Exception:
            return

    def _on_resource_released(self, event: Any) -> None:
        """Service release events without auto-granting legacy FIFO waiters."""
        try:
            payload = getattr(event, "payload", {}) or {}
            resource_id = payload.get("resource_id")
            holder = payload.get("holder")
            if not resource_id or not holder:
                return
            if self.release(resource_id, holder=holder):
                self._emit(
                    "resource.released",
                    {
                        "resource_id": resource_id,
                        "holder": holder,
                        "next_holder": self.next_waiter(resource_id),
                    },
                )
        except Exception:
            return

    def _on_resource_unavailable(self, event: Any) -> None:
        """Translate an availability event into bounded deterministic failover."""
        try:
            payload = getattr(event, "payload", {}) or {}
            resource_id = payload.get("resource_id")
            if resource_id:
                self.mark_unavailable(resource_id, reason=str(payload.get("reason", "unavailable")))
        except Exception:
            return

    # ------------------------------------------------------------------
    # Selection and accounting helpers
    # ------------------------------------------------------------------
    def _rank_candidates(
        self,
        request: ResourceRequest,
        policy: ResourcePolicy,
        excluded: Set[str],
    ) -> List[Tuple[Resource, float]]:
        candidates: List[Tuple[Resource, float]] = []
        for resource in self._registry.all():
            if resource.id in excluded or not self._matches(resource, request, policy):
                continue
            candidates.append((resource, self._score(resource, policy)))
        candidates.sort(key=lambda pair: (-pair[1], pair[0].id))
        return candidates

    def _matches(
        self, resource: Resource, request: ResourceRequest, policy: ResourcePolicy
    ) -> bool:
        if not resource.healthy or resource.availability <= 0.0:
            return False
        if request.kind is not None and resource.kind != request.kind:
            return False
        if request.capability and request.capability not in resource.capabilities:
            return False
        if not set(request.required_permissions).issubset(set(resource.permissions)):
            return False
        if request.local_only and resource.location.lower() != "local":
            return False
        if request.max_latency_ms is not None and resource.latency_ms > request.max_latency_ms:
            return False
        if not policy.allow_paid and resource.cost > 0.0:
            return False
        if resource.exclusive and self._holders.get(resource.id) not in (None, request.holder):
            return False
        shared = self._shared.get(resource.id, set())
        return not (
            not resource.exclusive
            and resource.max_parallel_jobs is not None
            and request.holder not in shared
            and len(shared) >= resource.max_parallel_jobs
        )

    @staticmethod
    def _score(resource: Resource, policy: ResourcePolicy) -> float:
        """Score an already-compatible resource using only its descriptor."""
        local_bonus = 0.25 if policy.prefer_local and resource.location.lower() == "local" else 0.0
        return (
            resource.reliability * policy.reliability_weight
            + resource.availability * policy.availability_weight
            + local_bonus
            - resource.cost * policy.cost_weight
            - resource.energy_cost * policy.energy_weight
            - resource.latency_ms * policy.latency_weight
            - resource.current_load * policy.load_weight
        )

    def _attempt(
        self,
        candidates: Iterable[Tuple[Resource, float]],
        request: ResourceRequest,
        policy: ResourcePolicy,
        *,
        degraded: bool,
    ) -> Tuple[Optional[Allocation], str]:
        saw_budget_rejection = False
        for resource, score in candidates:
            if not self._fits_budget(request.holder, resource):
                saw_budget_rejection = True
                continue
            basic = self.allocate(resource.id, holder=request.holder)
            if not basic.granted:
                continue
            existing = self._reservation_for(resource.id, request.holder)
            if existing is None:
                existing = self._create_reservation(resource, request, policy)
            allocation = Allocation(
                resource.id,
                request.holder,
                granted=True,
                reason="degraded" if degraded else "allocated",
                reservation_id=existing.id,
                score=score,
                degraded=degraded,
            )
            self._emit(
                "resource.economically_allocated",
                {
                    "resource_id": resource.id,
                    "holder": request.holder,
                    "reservation_id": existing.id,
                    "score": score,
                    "degraded": degraded,
                },
            )
            return allocation, "allocated"
        return None, "budget_exceeded" if saw_budget_rejection else "unavailable"

    def _fits_budget(self, holder: str, resource: Resource) -> bool:
        status = self.budget_status(holder)
        budget = status.budget
        existing = self._reservation_for(resource.id, holder)
        added_cost = 0.0 if existing is not None else resource.cost
        added_energy = 0.0 if existing is not None else resource.energy_cost
        if budget.max_cost is not None and status.reserved_cost + added_cost > budget.max_cost:
            return False
        return not (
            budget.max_energy_cost is not None
            and status.reserved_energy_cost + added_energy > budget.max_energy_cost
        )

    def _create_reservation(
        self, resource: Resource, request: ResourceRequest, policy: ResourcePolicy
    ) -> ResourceReservation:
        self._sequence += 1
        reservation = ResourceReservation(
            id=f"reservation-{self._sequence}",
            resource_id=resource.id,
            holder=request.holder,
            request=request,
            policy=policy,
            cost=resource.cost,
            energy_cost=resource.energy_cost,
            sequence=self._sequence,
        )
        self._reservations[reservation.id] = reservation
        self._reserved_cost[request.holder] = self._reserved_cost.get(request.holder, 0.0) + resource.cost
        self._reserved_energy[request.holder] = (
            self._reserved_energy.get(request.holder, 0.0) + resource.energy_cost
        )
        return reservation

    def _reservation_for(self, resource_id: str, holder: str) -> Optional[ResourceReservation]:
        for reservation in self._reservations.values():
            if reservation.resource_id == resource_id and reservation.holder == holder:
                return reservation
        return None

    def _forget_reservations(self, resource_id: str, holder: str) -> None:
        for reservation in list(self._reservations.values()):
            if reservation.resource_id != resource_id or reservation.holder != holder:
                continue
            self._reservations.pop(reservation.id, None)
            self._reserved_cost[holder] = max(
                0.0, self._reserved_cost.get(holder, 0.0) - reservation.cost
            )
            self._reserved_energy[holder] = max(
                0.0, self._reserved_energy.get(holder, 0.0) - reservation.energy_cost
            )

    def _queue(
        self, request: ResourceRequest, policy: ResourcePolicy, reason: str
    ) -> Allocation:
        for request_id, (queued_request, _queued_policy) in self._pending.items():
            if queued_request == request:
                return Allocation(
                    "", request.holder, granted=False, reason="queued", queued=True,
                    reservation_id=request_id,
                )
        self._sequence += 1
        request_id = f"request-{self._sequence}"
        self._pending[request_id] = (request, policy)
        self._emit(
            "resource.queued",
            {"holder": request.holder, "request_id": request_id, "reason": reason},
        )
        return Allocation(
            "", request.holder, granted=False, reason="queued", queued=True,
            reservation_id=request_id,
        )

    @staticmethod
    def _sequence_from_id(identifier: str) -> int:
        try:
            return int(identifier.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            return 0

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish a kernel event; no-op when no kernel is attached."""
        if self._kernel is None:
            return
        try:
            event = make_event(
                event_type=event_type,
                source="resources",
                logical_time=self._next_tick(),
                payload=payload,
            )
            self._kernel.publish_event(event)
        except Exception:
            return

    def _next_tick(self) -> int:
        """Best-effort next logical time from kernel health; defaults to one."""
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:
            return 1
