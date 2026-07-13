"""M18 - Resource Manager v2 economics, scheduling, and reallocation tests."""

from __future__ import annotations

from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

from friday.resources.economics import ResourceBudget, ResourcePolicy, ResourceRequest
from friday.resources.registry import ResourceRegistry
from friday.resources.scheduler import ResourceManager
from friday.resources.types import Resource, ResourceKind


def _manager(*resources: Resource) -> ResourceManager:
    registry = ResourceRegistry()
    for resource in resources:
        registry.register(resource)
    return ResourceManager(registry)


def test_selection_uses_capability_policy_and_economics():
    manager = _manager(
        Resource(
            id="local-fast",
            kind=ResourceKind.MODEL,
            exclusive=False,
            capabilities=("summarize",),
            location="local",
            reliability=0.9,
            latency_ms=50,
            cost=0.0,
        ),
        Resource(
            id="remote-costly",
            kind=ResourceKind.MODEL,
            exclusive=False,
            capabilities=("summarize",),
            location="remote",
            reliability=1.0,
            latency_ms=5,
            cost=3.0,
        ),
        Resource(
            id="incompatible",
            kind=ResourceKind.MODEL,
            exclusive=False,
            capabilities=("vision",),
            reliability=1.0,
        ),
    )

    allocation = manager.allocate_best(
        ResourceRequest(holder="goal-a", kind=ResourceKind.MODEL, capability="summarize"),
        policy=ResourcePolicy(prefer_local=True, allow_paid=False),
    )

    assert allocation.granted is True
    assert allocation.resource_id == "local-fast"
    assert allocation.reservation_id
    assert manager.reservations[0].resource_id == "local-fast"


def test_budget_denial_is_queued_without_overcommitting():
    manager = _manager(
        Resource(id="expensive", kind=ResourceKind.COMPUTE, exclusive=False, cost=2.0)
    )
    manager.set_budget("goal-a", ResourceBudget(max_cost=1.0))

    allocation = manager.allocate_best(
        ResourceRequest(holder="goal-a", kind=ResourceKind.COMPUTE)
    )

    assert allocation.granted is False
    assert allocation.queued is True
    assert manager.budget_status("goal-a").reserved_cost == 0.0
    assert manager.pending_requests == (
        ResourceRequest(holder="goal-a", kind=ResourceKind.COMPUTE),
    )


def test_explicit_fallback_is_marked_degraded():
    manager = _manager(
        Resource(id="fallback", kind=ResourceKind.COMPUTE, exclusive=False)
    )

    allocation = manager.allocate_best(
        ResourceRequest(
            holder="goal-a",
            kind=ResourceKind.MODEL,
            allow_degrade=True,
            fallback_kinds=(ResourceKind.COMPUTE,),
        )
    )

    assert allocation.granted is True
    assert allocation.resource_id == "fallback"
    assert allocation.degraded is True
    assert allocation.reason == "degraded"


def test_bounded_nonexclusive_resource_never_exceeds_parallel_limit():
    manager = _manager(
        Resource(
            id="pool",
            kind=ResourceKind.COMPUTE,
            exclusive=False,
            max_parallel_jobs=2,
        )
    )
    request = lambda holder: ResourceRequest(holder=holder, kind=ResourceKind.COMPUTE)

    assert manager.allocate_best(request("one")).granted is True
    assert manager.allocate_best(request("two")).granted is True
    third = manager.allocate_best(request("three"), queue_on_failure=False)

    assert third.granted is False
    assert third.reason == "unavailable"


def test_queue_is_priority_ordered_and_retries_without_auto_granting():
    manager = _manager(
        Resource(id="slot", kind=ResourceKind.BROWSER, exclusive=True)
    )
    assert manager.allocate("slot", holder="running").granted
    low = ResourceRequest(holder="low", kind=ResourceKind.BROWSER, priority=1)
    high = ResourceRequest(holder="high", kind=ResourceKind.BROWSER, priority=9)
    assert manager.allocate_best(low).queued
    assert manager.allocate_best(high).queued

    assert manager.release("slot", holder="running") is True
    granted = manager.process_queue()

    assert [item.holder for item in granted] == ["high"]
    assert manager.holder_of("slot") == "high"
    assert manager.pending_requests == (low,)


def test_failure_reallocates_an_affected_reservation_to_a_substitute():
    manager = _manager(
        Resource(
            id="preferred",
            kind=ResourceKind.MODEL,
            exclusive=False,
            location="local",
            reliability=0.9,
        ),
        Resource(
            id="substitute",
            kind=ResourceKind.MODEL,
            exclusive=False,
            location="remote",
            reliability=0.8,
        ),
    )
    request = ResourceRequest(holder="goal-a", kind=ResourceKind.MODEL)
    initial = manager.allocate_best(request, policy=ResourcePolicy(prefer_local=True))
    assert initial.resource_id == "preferred"

    outcomes = manager.mark_unavailable("preferred", reason="health_check_failed")

    assert len(outcomes) == 1
    assert outcomes[0].outcome == "reallocated"
    assert outcomes[0].replacement_resource_id == "substitute"
    assert manager.reservations[0].resource_id == "substitute"
    assert manager.budget_status("goal-a").reserved_cost == 0.0


def test_failure_queues_only_affected_work_when_no_substitute_exists():
    manager = _manager(
        Resource(id="sole", kind=ResourceKind.NETWORK, exclusive=False)
    )
    allocation = manager.allocate_best(
        ResourceRequest(holder="goal-a", kind=ResourceKind.NETWORK)
    )

    outcomes = manager.mark_unavailable("sole")

    assert outcomes[0].previous_reservation_id == allocation.reservation_id
    assert outcomes[0].outcome == "queued"
    assert manager.pending_requests[0].holder == "goal-a"
    assert manager.reservations == ()


def test_failover_preserves_the_original_policy():
    manager = _manager(
        Resource(id="free", kind=ResourceKind.MODEL, exclusive=False, cost=0.0),
        Resource(id="paid", kind=ResourceKind.MODEL, exclusive=False, cost=1.0),
    )
    request = ResourceRequest(holder="goal-a", kind=ResourceKind.MODEL)
    initial = manager.allocate_best(request, policy=ResourcePolicy(allow_paid=False))
    assert initial.resource_id == "free"

    outcomes = manager.mark_unavailable("free")

    assert outcomes[0].outcome == "queued"
    assert manager.reservations == ()
    assert manager.pending_requests == (request,)


def test_resource_unavailable_event_uses_the_same_failover_path():
    class FakeKernel:
        def __init__(self):
            self.handlers = {}
            self.events = []

        def subscribe(self, event_type, handler):
            self.handlers[event_type] = handler

        def publish_event(self, event):
            self.events.append(event)

        def health(self):
            return {"tick": 7}

    manager = _manager(
        Resource(id="affected", kind=ResourceKind.NETWORK, exclusive=False, reliability=0.9),
        Resource(id="replacement", kind=ResourceKind.NETWORK, exclusive=False, reliability=0.8),
    )
    kernel = FakeKernel()
    manager.attach(kernel)
    assert manager.allocate_best(
        ResourceRequest(holder="goal-a", kind=ResourceKind.NETWORK)
    ).resource_id == "affected"

    kernel.handlers["resource.unavailable"](
        SimpleNamespace(payload={"resource_id": "affected", "reason": "event"})
    )

    assert manager.reservations[0].resource_id == "replacement"
    assert any(event.event_type == "resource.reallocated" for event in kernel.events)


# Feature: m18-resource-manager-v2, Property 1: resource selection is deterministic.
@settings(max_examples=100, deadline=None)
@given(
    local_reliability=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    remote_reliability=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    local_cost=st.floats(min_value=0.0, max_value=5.0, allow_nan=False),
    remote_cost=st.floats(min_value=0.0, max_value=5.0, allow_nan=False),
)
def test_property_selection_is_deterministic(
    local_reliability, remote_reliability, local_cost, remote_cost
):
    """The same registry, request, and policy always choose the same resource."""
    resources = (
        Resource(
            id="local",
            kind=ResourceKind.MODEL,
            exclusive=False,
            location="local",
            reliability=local_reliability,
            cost=local_cost,
        ),
        Resource(
            id="remote",
            kind=ResourceKind.MODEL,
            exclusive=False,
            location="remote",
            reliability=remote_reliability,
            cost=remote_cost,
        ),
    )
    request = ResourceRequest(holder="goal", kind=ResourceKind.MODEL)
    policy = ResourcePolicy(prefer_local=True)

    first = _manager(*resources).allocate_best(request, policy=policy)
    second = _manager(*resources).allocate_best(request, policy=policy)

    assert first.resource_id == second.resource_id
    assert first.score == second.score


# Feature: m18-resource-manager-v2, Property 2: reservation accounting is conserved.
@settings(max_examples=100, deadline=None)
@given(
    cost=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    energy=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
)
def test_property_release_restores_reservation_budget(cost, energy):
    """Granting then releasing restores the exact pre-allocation budget state."""
    manager = _manager(
        Resource(
            id="resource",
            kind=ResourceKind.COMPUTE,
            exclusive=True,
            cost=cost,
            energy_cost=energy,
        )
    )
    request = ResourceRequest(holder="goal", kind=ResourceKind.COMPUTE)
    allocation = manager.allocate_best(request)
    assert allocation.granted

    before_release = manager.budget_status("goal")
    assert before_release.reserved_cost == cost
    assert before_release.reserved_energy_cost == energy
    assert manager.release_reservation(allocation.reservation_id) is True

    after_release = manager.budget_status("goal")
    assert after_release.reserved_cost == 0.0
    assert after_release.reserved_energy_cost == 0.0
    assert manager.reservations == ()
