"""M4-Gaps unit tests — concrete examples and edge cases.

Plain example-based tests for the four M4 subsystems (Safety & Permission,
Resource Model, Cognitive Identity, Cognitive State), complementing the
universal Hypothesis properties in ``test_m4_properties.py``.

All tests run under FRIDAY_DRY_RUN=1 — no real credential store or I/O.
"""

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from friday.safety.permission import (
    Decision,
    PermissionLevel,
    PermissionManager,
    PermissionRequest,
    TrustZone,
)
from friday.resources.registry import ResourceRegistry
from friday.resources.scheduler import ResourceManager
from friday.resources.types import Resource, ResourceKind
from friday.cognition.state import (
    CognitiveMode,
    CognitiveStateManager,
    ThinkingDepth,
)


# ======================================================================
# PermissionManager — permission matrix
# ======================================================================
def _request(level, trust_zone, *, reversible=True, confidence=1.0):
    return PermissionRequest(
        action="act",
        level=level,
        trust_zone=trust_zone,
        reversible=reversible,
        confidence=confidence,
    )


def test_observation_interaction_trusted_verified_allow():
    manager = PermissionManager()
    for level in (PermissionLevel.OBSERVATION, PermissionLevel.INTERACTION):
        for zone in (TrustZone.TRUSTED, TrustZone.VERIFIED):
            verdict = manager.evaluate(_request(level, zone))
            assert verdict.decision == Decision.ALLOW


def test_modification_notifies_in_trusted_zone():
    manager = PermissionManager()
    verdict = manager.evaluate(_request(PermissionLevel.MODIFICATION, TrustZone.TRUSTED))
    assert verdict.decision == Decision.NOTIFY


def test_hostile_zone_escalates_modification_to_deny():
    manager = PermissionManager()
    verdict = manager.evaluate(_request(PermissionLevel.MODIFICATION, TrustZone.HOSTILE))
    assert verdict.decision == Decision.DENY


def test_hostile_zone_escalates_interaction_to_confirm():
    manager = PermissionManager()
    verdict = manager.evaluate(_request(PermissionLevel.INTERACTION, TrustZone.HOSTILE))
    assert verdict.decision == Decision.CONFIRM


def test_untrusted_zone_escalates_interaction_to_confirm():
    manager = PermissionManager()
    verdict = manager.evaluate(_request(PermissionLevel.INTERACTION, TrustZone.UNTRUSTED))
    assert verdict.decision == Decision.CONFIRM


def test_kernel_level_is_denied():
    manager = PermissionManager()
    verdict = manager.evaluate(_request(PermissionLevel.KERNEL, TrustZone.TRUSTED))
    assert verdict.decision == Decision.DENY


def test_financial_level_requires_confirmation():
    manager = PermissionManager()
    verdict = manager.evaluate(_request(PermissionLevel.FINANCIAL, TrustZone.TRUSTED))
    assert verdict.decision == Decision.CONFIRM


# ======================================================================
# ResourceRegistry — register / get / by_kind / unregister
# ======================================================================
def test_registry_register_and_get():
    registry = ResourceRegistry()
    resource = Resource(id="r1", kind=ResourceKind.COMPUTE, exclusive=False)
    rid = registry.register(resource)
    assert rid == "r1"
    assert registry.get("r1") is resource


def test_registry_by_kind():
    registry = ResourceRegistry()
    registry.register(Resource(id="c1", kind=ResourceKind.COMPUTE, exclusive=False))
    registry.register(Resource(id="c2", kind=ResourceKind.COMPUTE, exclusive=False))
    registry.register(Resource(id="m1", kind=ResourceKind.MODEL, exclusive=False))
    compute = registry.by_kind(ResourceKind.COMPUTE)
    assert {r.id for r in compute} == {"c1", "c2"}
    assert [r.id for r in registry.by_kind(ResourceKind.MODEL)] == ["m1"]


def test_registry_unregister():
    registry = ResourceRegistry()
    registry.register(Resource(id="r1", kind=ResourceKind.STORAGE, exclusive=False))
    registry.unregister("r1")
    assert registry.get("r1") is None
    # Unregistering an unknown id is a no-op.
    registry.unregister("does-not-exist")


# ======================================================================
# ResourceManager — unknown / unhealthy / non-exclusive
# ======================================================================
def test_manager_unknown_resource_denied():
    manager = ResourceManager(ResourceRegistry())
    allocation = manager.allocate("nope", holder="h1")
    assert allocation.granted is False
    assert allocation.reason == "unknown"


def test_manager_unhealthy_resource_denied():
    registry = ResourceRegistry()
    registry.register(
        Resource(id="sick", kind=ResourceKind.NETWORK, exclusive=False, healthy=False)
    )
    manager = ResourceManager(registry)
    allocation = manager.allocate("sick", holder="h1")
    assert allocation.granted is False
    assert allocation.reason == "unhealthy"


def test_manager_non_exclusive_shared_by_many():
    registry = ResourceRegistry()
    registry.register(Resource(id="pool", kind=ResourceKind.COMPUTE, exclusive=False))
    manager = ResourceManager(registry)
    for holder in ("a", "b", "c"):
        allocation = manager.allocate("pool", holder=holder)
        assert allocation.granted is True
    # Non-exclusive resources track no single exclusive holder.
    assert manager.holder_of("pool") is None


def test_manager_exclusive_grant_and_idempotent():
    registry = ResourceRegistry()
    registry.register(Resource(id="excl", kind=ResourceKind.BROWSER, exclusive=True))
    manager = ResourceManager(registry)
    first = manager.allocate("excl", holder="a")
    assert first.granted is True
    # Same holder re-allocating is idempotent.
    again = manager.allocate("excl", holder="a")
    assert again.granted is True
    # A different holder is denied.
    other = manager.allocate("excl", holder="b")
    assert other.granted is False
    assert manager.holder_of("excl") == "a"


# ======================================================================
# CognitiveStateManager — transitions + snapshot copy
# ======================================================================
def test_enter_mode():
    manager = CognitiveStateManager()
    assert manager.snapshot().mode == CognitiveMode.IDLE
    manager.enter_mode(CognitiveMode.EXECUTION)
    assert manager.snapshot().mode == CognitiveMode.EXECUTION


def test_set_focus():
    manager = CognitiveStateManager()
    manager.set_focus("goal-1", attention=0.5)
    snap = manager.snapshot()
    assert snap.focus == "goal-1"
    assert snap.active_goal == "goal-1"
    assert snap.attention == 0.5


def test_set_focus_clamps_attention():
    manager = CognitiveStateManager()
    manager.set_focus("g", attention=5.0)
    assert manager.snapshot().attention == 1.0


def test_set_thinking_depth():
    manager = CognitiveStateManager()
    manager.set_thinking_depth(ThinkingDepth.DEEP)
    assert manager.snapshot().thinking_depth == ThinkingDepth.DEEP


def test_set_interruptible():
    manager = CognitiveStateManager()
    manager.set_interruptible(False)
    assert manager.snapshot().interruptible is False


def test_snapshot_returns_copy():
    manager = CognitiveStateManager()
    snap = manager.snapshot()
    snap.mode = CognitiveMode.CONVERSATION
    snap.focus = "mutated"
    # Mutating the snapshot does not affect internal state.
    fresh = manager.snapshot()
    assert fresh.mode == CognitiveMode.IDLE
    assert fresh.focus is None


def test_consume_and_reset_budget():
    manager = CognitiveStateManager()
    remaining = manager.consume_budget(0.3)
    assert abs(remaining - 0.7) < 1e-9
    manager.consume_budget(1.0)  # over-consume clamps to 0
    assert manager.snapshot().reasoning_budget == 0.0
    manager.reset_budget()
    assert manager.snapshot().reasoning_budget == 1.0
