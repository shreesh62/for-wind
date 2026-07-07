"""Ch 46 — allocate/release resources; exclusive resources never double-allocated.

The :class:`ResourceManager` is the single authority the rest of the runtime
asks for resources rather than acquiring them directly. It prevents
double-allocation of exclusive resources, lets non-exclusive resources be
shared, and tracks a FIFO wait order per exclusive resource so a released slot
can be handed to the next queued holder (dynamic reallocation, Ch 46.6).

Fails safe: unknown or unhealthy resources are denied rather than granted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from friday.events.event import make_event
from friday.resources.registry import ResourceRegistry


@dataclass(frozen=True)
class Allocation:
    """Ch 46 — the outcome of an allocation request."""

    resource_id: str
    holder: str                     # goal_id or subsystem name
    granted: bool
    reason: str


class ResourceManager:
    """Ch 46 — allocate/release; exclusive resources never double-allocated."""

    def __init__(self, registry: ResourceRegistry) -> None:
        self._registry = registry
        # exclusive resources: resource_id -> current holder
        self._holders: Dict[str, str] = {}
        # non-exclusive resources: resource_id -> set of holders
        self._shared: Dict[str, Set[str]] = {}
        # FIFO wait order per exclusive resource
        self._wait: Dict[str, List[str]] = {}
        # kernel handle for event-driven wiring (task 2.3); None until attached
        self._kernel: Any = None

    def allocate(self, resource_id: str, *, holder: str) -> Allocation:
        """Allocate ``resource_id`` to ``holder``; fail safe on unknown/unhealthy."""
        resource = self._registry.get(resource_id)
        if resource is None:
            return Allocation(resource_id, holder, granted=False, reason="unknown")
        if not resource.healthy:
            return Allocation(resource_id, holder, granted=False, reason="unhealthy")

        if not resource.exclusive:
            # Non-exclusive: always grant, add holder to the shared set.
            self._shared.setdefault(resource_id, set()).add(holder)
            return Allocation(resource_id, holder, granted=True, reason="shared")

        # Exclusive resource.
        current = self._holders.get(resource_id)
        if current is None:
            # Free slot — grant and record holder.
            self._holders[resource_id] = holder
            return Allocation(resource_id, holder, granted=True, reason="granted")
        if current == holder:
            # Idempotent re-allocation by the same holder.
            return Allocation(resource_id, holder, granted=True, reason="held")

        # Held by a different holder — deny and queue in FIFO wait order.
        waiters = self._wait.setdefault(resource_id, [])
        if holder not in waiters:
            waiters.append(holder)
        return Allocation(resource_id, holder, granted=False, reason="busy")

    def release(self, resource_id: str, *, holder: str) -> bool:
        """Release ``resource_id`` held by ``holder``; return True if freed."""
        resource = self._registry.get(resource_id)

        # Exclusive path — only the current holder can free it.
        if resource is not None and resource.exclusive:
            if self._holders.get(resource_id) == holder:
                del self._holders[resource_id]
                # Do NOT auto-grant here; next waiter is surfaced via
                # next_waiter()/the resource.released event (task 2.3).
                return True
            return False

        # Non-exclusive path — remove holder from the shared set if present.
        holders = self._shared.get(resource_id)
        if holders is not None and holder in holders:
            holders.discard(holder)
            if not holders:
                del self._shared[resource_id]
            return True
        return False

    def holder_of(self, resource_id: str) -> Optional[str]:
        """Return the current exclusive holder of ``resource_id`` (or None)."""
        return self._holders.get(resource_id)

    def next_waiter(self, resource_id: str) -> Optional[str]:
        """Peek the FIFO head of the wait list for ``resource_id`` (or None)."""
        waiters = self._wait.get(resource_id)
        if waiters:
            return waiters[0]
        return None

    # --- kernel wiring (Ch 52 — kernel-driven) -----------------------------
    def attach(self, kernel: Any) -> None:
        """Subscribe to resource request/release events (kernel-driven)."""
        self._kernel = kernel
        kernel.subscribe("resource.requested", self._on_resource_requested)
        kernel.subscribe("resource.released", self._on_resource_released)

    def _on_resource_requested(self, event: Any) -> None:
        """React to ``resource.requested``; allocate and emit the outcome.

        Reads the payload defensively. On a granted allocation publishes
        ``resource.allocated``; otherwise publishes ``resource.denied`` with the
        allocation reason. Never raises into the tick loop.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            resource_id = payload.get("resource_id")
            holder = payload.get("holder")
            if not resource_id or not holder:
                return

            allocation = self.allocate(resource_id, holder=holder)
            if allocation.granted:
                self._emit(
                    "resource.allocated",
                    {"resource_id": resource_id, "holder": holder},
                )
            else:
                self._emit(
                    "resource.denied",
                    {
                        "resource_id": resource_id,
                        "holder": holder,
                        "reason": allocation.reason,
                    },
                )
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _on_resource_released(self, event: Any) -> None:
        """React to ``resource.released``; release and surface the next waiter.

        Reads the payload defensively. On a successful release publishes
        ``resource.released`` carrying the next FIFO waiter (may be None). Never
        raises into the tick loop.
        """
        try:
            payload = getattr(event, "payload", {}) or {}
            resource_id = payload.get("resource_id")
            holder = payload.get("holder")
            if not resource_id or not holder:
                return

            freed = self.release(resource_id, holder=holder)
            if freed:
                self._emit(
                    "resource.released",
                    {
                        "resource_id": resource_id,
                        "holder": holder,
                        "next_holder": self.next_waiter(resource_id),
                    },
                )
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    # --- helpers -----------------------------------------------------------
    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish a kernel event; no-op when no kernel is attached."""
        if self._kernel is None:
            return
        event = make_event(
            event_type=event_type,
            source="resources",
            logical_time=self._next_tick(),
            payload=payload,
        )
        self._kernel.publish_event(event)

    def _next_tick(self) -> int:
        """Best-effort next logical time from kernel health; defaults to 1."""
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:  # noqa: BLE001 — health must never break emission
            return 1
