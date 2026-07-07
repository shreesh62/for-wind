"""M4-Gaps Property-Based Tests (Hypothesis) — universal correctness properties.

Encodes the numbered correctness properties from the M4 design document
(Safety & Permission, Resource Model, Cognitive Identity, Cognitive State) using
the Hypothesis property-based testing library. Each test validates a
universally-quantified statement that must hold across ALL generated inputs.

Properties covered:
  - Property 1 (1.1, 1.4): Forbidden levels are never auto-allowed
  - Property 2 (1.2):      Confirmation levels always require confirmation
  - Property 3 (1.3):      Irreversible low-confidence never auto-allowed
  - Property 4 (2.2, 2.3): Vault never leaks values
  - Property 5 (2.1):      Vault round-trips
  - Property 6 (3.2, 3.3): Exclusive resources never double-allocated
  - Property 7 (3.4):      Release frees exactly the holder
  - Property 8 (4.5, 4.6): Identity survives restart
  - Property 9 (5.4):      Reasoning budget stays in [0, 1]

All tests run under FRIDAY_DRY_RUN=1 — no real credential store, filesystem, or I/O.
"""

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from hypothesis import given, settings, strategies as st

from friday.safety.permission import (
    Decision,
    PermissionLevel,
    PermissionManager,
    PermissionRequest,
    TrustZone,
)
from friday.safety.policy import SafetyPolicy
from friday.safety.vault import SecretVault
from friday.resources.registry import ResourceRegistry
from friday.resources.scheduler import ResourceManager
from friday.resources.types import Resource, ResourceKind
from friday.identity.identity import CognitiveIdentity
from friday.cognition.state import CognitiveStateManager


# ======================================================================
# Shared strategies
# ======================================================================

_trust_zones = st.sampled_from(list(TrustZone))
_all_levels = st.sampled_from(list(PermissionLevel))
_confidence = st.floats(min_value=0.0, max_value=1.0)
_holder = st.text(min_size=1, max_size=8)
_holders = st.lists(st.text(min_size=1, max_size=8), unique=True, min_size=1, max_size=6)

# The default policy's confirmation levels (always require confirmation).
_CONFIRM_LEVELS = [
    PermissionLevel.DELETION,
    PermissionLevel.FINANCIAL,
    PermissionLevel.IDENTITY,
    PermissionLevel.ADMINISTRATIVE,
    PermissionLevel.HARDWARE,
]

# Levels that are NOT forbidden under the default policy (KERNEL is forbidden).
_NON_FORBIDDEN_LEVELS = [lvl for lvl in PermissionLevel if lvl != PermissionLevel.KERNEL]


# ======================================================================
# Property 1: Forbidden levels are never auto-allowed
# ======================================================================
@settings(max_examples=200, deadline=None)
@given(trust_zone=_trust_zones, reversible=st.booleans(), confidence=_confidence)
def test_property_1_forbidden_never_auto_allowed(trust_zone, reversible, confidence):
    """**Property 1: Forbidden levels are never auto-allowed**

    For any PermissionRequest whose level == KERNEL (forbidden under the default
    policy), evaluate().decision is never ALLOW or NOTIFY.

    **Validates: Requirements 1.1, 1.4**
    """
    manager = PermissionManager()
    request = PermissionRequest(
        action="kernel-op",
        level=PermissionLevel.KERNEL,
        trust_zone=trust_zone,
        reversible=reversible,
        confidence=confidence,
    )
    verdict = manager.evaluate(request)
    assert verdict.decision not in (Decision.ALLOW, Decision.NOTIFY)


# ======================================================================
# Property 2: Confirmation levels always require confirmation
# ======================================================================
@settings(max_examples=200, deadline=None)
@given(
    level=st.sampled_from(_CONFIRM_LEVELS),
    trust_zone=_trust_zones,
    reversible=st.booleans(),
    confidence=_confidence,
)
def test_property_2_confirm_levels_require_confirmation(
    level, trust_zone, reversible, confidence
):
    """**Property 2: Confirmation levels always require confirmation**

    For any request whose level is in the policy's confirm set, evaluate().decision
    is CONFIRM or DENY, never ALLOW or NOTIFY.

    **Validates: Requirements 1.2**
    """
    manager = PermissionManager()
    request = PermissionRequest(
        action="risky",
        level=level,
        trust_zone=trust_zone,
        reversible=reversible,
        confidence=confidence,
    )
    verdict = manager.evaluate(request)
    assert verdict.decision in (Decision.CONFIRM, Decision.DENY)
    assert verdict.decision not in (Decision.ALLOW, Decision.NOTIFY)


# ======================================================================
# Property 3: Irreversible low-confidence never auto-allowed
# ======================================================================
@settings(max_examples=200, deadline=None)
@given(
    level=st.sampled_from(_NON_FORBIDDEN_LEVELS),
    trust_zone=_trust_zones,
    confidence=st.floats(min_value=0.0, max_value=0.85, exclude_max=True),
)
def test_property_3_irreversible_low_confidence_never_allowed(
    level, trust_zone, confidence
):
    """**Property 3: Irreversible low-confidence never auto-allowed**

    For any request with reversible=False and confidence below the confidence
    floor (0.85), and a non-forbidden level, evaluate().decision is never ALLOW.

    **Validates: Requirements 1.3**
    """
    manager = PermissionManager()
    request = PermissionRequest(
        action="irreversible",
        level=level,
        trust_zone=trust_zone,
        reversible=False,
        confidence=confidence,
    )
    verdict = manager.evaluate(request)
    assert verdict.decision != Decision.ALLOW


# ======================================================================
# Property 4: Vault never leaks values
# ======================================================================
@settings(max_examples=200, deadline=None)
@given(key=st.text(min_size=1, max_size=16), raw=st.text(min_size=1, max_size=32))
def test_property_4_vault_never_leaks_values(key, raw):
    """**Property 4: Vault never leaks values**

    For any key/value, after set(k, v) the value never appears in repr(vault),
    str(vault), or the vault's keys() output.

    **Validates: Requirements 2.2, 2.3**
    """
    # Wrap the arbitrary text in a distinctive sentinel so the secret value can
    # never coincide with the repr's structural template (backend name, key
    # count) or a key NAME — those overlaps are not value leaks. This still
    # exercises arbitrary secret content while asserting the real guarantee.
    value = "s3cr3t_marker::" + raw + "::end"
    vault = SecretVault(service="friday-test")
    vault.set(key, value)
    assert value not in repr(vault)
    assert value not in str(vault)
    assert value not in vault.keys()
    # The vault still round-trips the exact wrapped value.
    assert vault.get(key) == value


# ======================================================================
# Property 5: Vault round-trips
# ======================================================================
@settings(max_examples=200, deadline=None)
@given(key=st.text(min_size=1, max_size=16), value=st.text(min_size=1, max_size=32))
def test_property_5_vault_round_trips(key, value):
    """**Property 5: Vault round-trips**

    set(k, v) then get(k) == v; has(k) is True; after delete(k), get(k) is None
    and has(k) is False.

    **Validates: Requirements 2.1**
    """
    vault = SecretVault(service="friday-test")
    vault.set(key, value)
    assert vault.get(key) == value
    assert vault.has(key) is True

    vault.delete(key)
    assert vault.get(key) is None
    assert vault.has(key) is False


# ======================================================================
# Property 6: Exclusive resources never double-allocated
# ======================================================================
@settings(max_examples=200, deadline=None)
@given(holders=_holders)
def test_property_6_exclusive_never_double_allocated(holders):
    """**Property 6: Exclusive resources never double-allocated**

    Register an exclusive resource; for any list of distinct holders allocating
    it in order, at most one holds it at a time, and the first grantee stays the
    holder until it releases.

    **Validates: Requirements 3.2, 3.3**
    """
    registry = ResourceRegistry()
    registry.register(
        Resource(id="excl", kind=ResourceKind.BROWSER, exclusive=True)
    )
    manager = ResourceManager(registry)

    granted_holders = []
    for holder in holders:
        allocation = manager.allocate("excl", holder=holder)
        # At every step the resource has exactly one holder — the first grantee.
        assert manager.holder_of("excl") == holders[0]
        if allocation.granted:
            granted_holders.append(holder)

    # Only the first holder was ever granted (distinct holders, none released).
    assert granted_holders == [holders[0]]
    assert manager.holder_of("excl") == holders[0]


# ======================================================================
# Property 7: Release frees exactly the holder
# ======================================================================
@settings(max_examples=200, deadline=None)
@given(holder_a=_holder, holder_b=_holder)
def test_property_7_release_frees_exactly_the_holder(holder_a, holder_b):
    """**Property 7: Release frees exactly the holder**

    After holder A holds an exclusive resource, release by a non-holder B returns
    False and A still holds; release by A returns True and holder becomes None.

    **Validates: Requirements 3.4**
    """
    # Ensure B is genuinely a different holder from A.
    if holder_b == holder_a:
        holder_b = holder_a + "_other"

    registry = ResourceRegistry()
    registry.register(
        Resource(id="excl", kind=ResourceKind.INPUT, exclusive=True)
    )
    manager = ResourceManager(registry)

    granted = manager.allocate("excl", holder=holder_a)
    assert granted.granted is True
    assert manager.holder_of("excl") == holder_a

    # A non-holder cannot free it.
    assert manager.release("excl", holder=holder_b) is False
    assert manager.holder_of("excl") == holder_a

    # The current holder frees it.
    assert manager.release("excl", holder=holder_a) is True
    assert manager.holder_of("excl") is None


# ======================================================================
# Property 8: Identity survives restart
# ======================================================================
@settings(max_examples=200, deadline=None)
@given(
    identity_id=st.text(min_size=1, max_size=16),
    preferences=st.dictionaries(
        st.text(min_size=1, max_size=8),
        st.one_of(st.text(max_size=16), st.integers(), st.booleans()),
        max_size=6,
    ),
    goal_states=st.dictionaries(
        st.text(min_size=1, max_size=8),
        st.sampled_from(["pending", "active", "completed", "failed"]),
        max_size=6,
    ),
)
def test_property_8_identity_survives_restart(identity_id, preferences, goal_states):
    """**Property 8: Identity survives restart**

    A fresh CognitiveIdentity.restore(original.checkpoint()) reproduces
    identity_id, preferences, and goal_states identically; a partial state (e.g.
    {}) invents no goal ids.

    **Validates: Requirements 4.5, 4.6**
    """
    original = CognitiveIdentity(identity_id=identity_id)
    for key, value in preferences.items():
        original.set_preference(key, value)
    for goal_id, state in goal_states.items():
        original.record_goal_state(goal_id, state)

    snapshot = original.checkpoint()

    restored = CognitiveIdentity(identity_id="placeholder")
    restored.restore(snapshot)

    assert restored.identity_id == identity_id
    assert restored.preferences == preferences
    assert restored.goal_states == goal_states

    # Partial state (empty dict) defaults fields and invents no goal ids.
    partial = CognitiveIdentity(identity_id="keep-me")
    partial.restore({})
    assert partial.identity_id == "keep-me"
    assert partial.goal_states == {}
    assert partial.preferences == {}


# ======================================================================
# Property 9: Reasoning budget stays in [0, 1]
# ======================================================================
@settings(max_examples=200, deadline=None)
@given(amounts=st.lists(st.floats(min_value=0.0, max_value=2.0), max_size=20))
def test_property_9_reasoning_budget_in_unit_interval(amounts):
    """**Property 9: Reasoning budget stays in [0, 1]**

    For any sequence of consume_budget(amount >= 0) calls, snapshot().reasoning_budget
    stays within [0, 1] and is monotonically non-increasing until reset_budget().

    **Validates: Requirements 5.4**
    """
    manager = CognitiveStateManager()
    previous = manager.snapshot().reasoning_budget
    assert 0.0 <= previous <= 1.0

    for amount in amounts:
        manager.consume_budget(amount)
        current = manager.snapshot().reasoning_budget
        assert 0.0 <= current <= 1.0
        assert current <= previous  # monotonically non-increasing
        previous = current

    # Reset restores full budget within the unit interval.
    manager.reset_budget()
    reset_budget = manager.snapshot().reasoning_budget
    assert reset_budget == 1.0
    assert 0.0 <= reset_budget <= 1.0


# ======================================================================
# Property 10: Determinism
# ======================================================================
import fnmatch
from typing import Any, List, Tuple

from friday.events.event import Event, make_event


class FakeKernel:
    """Minimal kernel double: captures published events + fnmatch-routes them.

    Mirrors the real ``CognitiveKernel`` wiring the M4 subsystems depend on
    (``subscribe(pattern, handler)`` / ``publish_event(event)`` / ``health()``)
    without any clock, store, scheduler, or checkpoint machinery — so replaying
    an identical ordered event log through two independent kernels is perfectly
    deterministic.
    """

    def __init__(self) -> None:
        self.published: List[Event] = []
        self._subscribers: List[Tuple[str, Any]] = []
        self._logical = 0

    def subscribe(self, pattern: str, handler: Any) -> str:
        self._subscribers.append((pattern, handler))
        return f"sub-{len(self._subscribers)}"

    def publish_event(self, event: Event) -> None:
        self.published.append(event)
        for pattern, handler in list(self._subscribers):
            if fnmatch.fnmatch(event.event_type, pattern):
                handler(event)

    def health(self) -> dict:
        return {"tick": self._logical}

    def next_logical(self) -> int:
        self._logical += 1
        return self._logical


def _build_m4_subsystems():
    """Freshly construct and attach the kernel-driven M4 subsystems.

    Builds a brand-new :class:`FakeKernel` plus a fresh
    ``PermissionManager`` / ``ResourceManager`` (over a pre-populated
    ``ResourceRegistry``) / ``CognitiveIdentity`` / ``CognitiveStateManager``,
    each attached via ``subscribe`` — exactly the wiring a real kernel uses.
    """
    kernel = FakeKernel()

    permissions = PermissionManager()
    permissions.attach(kernel)

    registry = ResourceRegistry()
    registry.register(Resource(id="excl-1", kind=ResourceKind.BROWSER, exclusive=True))
    registry.register(Resource(id="shared-1", kind=ResourceKind.COMPUTE, exclusive=False))
    resources = ResourceManager(registry)
    resources.attach(kernel)

    identity = CognitiveIdentity(identity_id="friday-identity")
    identity.attach(kernel)

    cognitive = CognitiveStateManager()
    cognitive.attach(kernel)

    return kernel, permissions, resources, identity, cognitive


def _emission_fingerprint(kernel: FakeKernel) -> List[Tuple[str, tuple]]:
    """Ordered (event_type, sorted-payload-items) for every published event.

    Event id and wall_time live on the :class:`Event` envelope and are excluded
    by construction (we never read them); the payload is compared verbatim.
    """
    fingerprint: List[Tuple[str, tuple]] = []
    for event in kernel.published:
        items = tuple(sorted(dict(event.payload).items()))
        fingerprint.append((event.event_type, items))
    return fingerprint


def _internal_state(resources, identity, cognitive) -> dict:
    """A comparable snapshot of the M4 subsystems' internal state after replay."""
    snap = cognitive.snapshot()
    return {
        "identity": identity.checkpoint(),
        "resource_holders": dict(resources._holders),
        "resource_shared": {k: sorted(v) for k, v in resources._shared.items()},
        "resource_wait": {k: list(v) for k, v in resources._wait.items()},
        "cognitive": {
            "mode": snap.mode.value,
            "focus": snap.focus,
            "active_goal": snap.active_goal,
            "attention": snap.attention,
            "interruptible": snap.interruptible,
            "thinking_depth": snap.thinking_depth.value,
            "reasoning_budget": snap.reasoning_budget,
            "urgency": snap.urgency,
        },
    }


# A single generated event descriptor: (event_type, payload). Hypothesis builds
# an ordered list of these; both runs replay the SAME list, event-for-event.
@st.composite
def _m4_event_log(draw) -> List[Tuple[str, dict]]:
    """Generate an ordered log of M4-relevant kernel events.

    Draws a bounded sequence of action.requested / resource.requested /
    resource.released / goal.state_changed / action.executed descriptors over a
    small shared vocabulary (fixed resource ids + a handful of holders/goals) so
    exclusive-resource contention and goal focus actually recur. Only the ORDER
    and CONTENT matter — both determinism runs replay this exact list.
    """
    holders = st.sampled_from(["holder-A", "holder-B", "holder-C"])
    goal_ids = st.sampled_from(["g1", "g2", "g3"])
    resource_ids = st.sampled_from(["excl-1", "shared-1", "unknown-1"])
    levels = st.sampled_from([int(lvl) for lvl in PermissionLevel])
    trust_zones = st.sampled_from([tz.value for tz in TrustZone])
    states = st.sampled_from(["active", "suspended", "completed", "pending"])

    action_requested = st.builds(
        lambda lvl, tz, rev, conf: (
            "action.requested",
            {
                "action": "act",
                "level": lvl,
                "trust_zone": tz,
                "reversible": rev,
                "confidence": conf,
            },
        ),
        levels,
        trust_zones,
        st.booleans(),
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    resource_requested = st.builds(
        lambda rid, h: ("resource.requested", {"resource_id": rid, "holder": h}),
        resource_ids,
        holders,
    )
    resource_released = st.builds(
        lambda rid, h: ("resource.released", {"resource_id": rid, "holder": h}),
        resource_ids,
        holders,
    )
    goal_changed = st.builds(
        lambda gid, s: ("goal.state_changed", {"goal_id": gid, "state": s}),
        goal_ids,
        states,
    )
    action_executed = st.builds(
        lambda gid: ("action.executed", {"goal_id": gid, "capability": "search"}),
        goal_ids,
    )

    return draw(
        st.lists(
            st.one_of(
                action_requested,
                resource_requested,
                resource_released,
                goal_changed,
                action_executed,
            ),
            min_size=1,
            max_size=30,
        )
    )


def _replay(log: List[Tuple[str, dict]]):
    """Replay an event log through a fresh set of M4 subsystems; return them."""
    kernel, permissions, resources, identity, cognitive = _build_m4_subsystems()
    for event_type, payload in log:
        kernel.publish_event(
            make_event(
                event_type=event_type,
                source="test",
                logical_time=kernel.next_logical(),
                payload=payload,
            )
        )
    return kernel, resources, identity, cognitive


@settings(max_examples=150, deadline=None)
@given(log=_m4_event_log())
def test_property_10_determinism(log):
    """**Property 10: Determinism**

    Replaying the same ordered event log through two freshly-constructed sets of
    M4 subsystems (Safety + Resources + Identity + CognitiveState) produces
    identical emitted kernel-event types and payloads (modulo event id and
    wall_time, which live on the Event envelope) and identical internal state.
    No M4 decision depends on anything but the ordered events it consumes.

    **Validates: Requirements 6.4, 6.5**
    """
    kernel_a, resources_a, identity_a, cognitive_a = _replay(log)
    kernel_b, resources_b, identity_b, cognitive_b = _replay(log)

    # Identical emitted event types + payloads, in identical order.
    assert _emission_fingerprint(kernel_a) == _emission_fingerprint(kernel_b)

    # Identical internal state across all four kernel-driven subsystems.
    assert _internal_state(resources_a, identity_a, cognitive_a) == _internal_state(
        resources_b, identity_b, cognitive_b
    )
