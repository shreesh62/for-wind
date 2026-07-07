"""M4-Gaps Task 6.4 — The M4 Gate (safety/resources/identity end-to-end).

The binding gate: a REAL ``CognitiveKernel`` with all four M4-gap subsystems
attached proves the constitutional story end-to-end through kernel events:

1. A risky action (``action.requested`` at FINANCIAL or KERNEL level) is gated:
   ``permission.denied`` lands on the log and ``permission.granted`` never does
   for that action (Req 6.5 / Property 1, 2).
2. An exclusive resource contended by two holders is granted to EXACTLY one:
   one ``resource.allocated`` and one ``resource.denied`` (Req 6.5 / Property 6).
3. A ``CognitiveIdentity`` survives a checkpoint→restore across a FRESH kernel:
   the identical identity id + goal states are reconstructed (Req 6.5 /
   Property 8).
4. Determinism: a ``_run_gate(tmp_path, tag)`` helper run twice yields identical
   ordered M4 event-type sequences (Req 6.5 / Property 10).

All interaction is via ``kernel.subscribe`` / ``kernel.publish_event`` — the
scheduler thread is never started, so the whole gate is deterministic. Runs
under ``FRIDAY_DRY_RUN=1``.

Validates: Requirements 6.5, 7.2
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from typing import List

from friday.cognition.state import CognitiveStateManager
from friday.events.event import make_event
from friday.identity.identity import CognitiveIdentity
from friday.kernel.kernel import CognitiveKernel
from friday.resources.registry import ResourceRegistry
from friday.resources.scheduler import ResourceManager
from friday.resources.types import Resource, ResourceKind
from friday.safety.permission import PermissionLevel, PermissionManager, TrustZone


# M4-relevant event types used for the determinism comparison (Req 6.5).
_M4_EVENT_TYPES = {
    "permission.granted",
    "permission.denied",
    "resource.allocated",
    "resource.denied",
    "resource.released",
}


def _publish(kernel: CognitiveKernel, event_type: str, payload: dict) -> None:
    """Publish an event through the kernel with a monotonically advancing tick."""
    tick = int(kernel.health().get("tick", 0)) + 1
    kernel.publish_event(
        make_event(
            event_type=event_type,
            source="test",
            logical_time=tick,
            payload=payload,
        )
    )


def _wire(kernel: CognitiveKernel):
    """Attach all four M4 subsystems to ``kernel``; return them + a collector."""
    collected: List[str] = []
    kernel.subscribe("*", lambda event: collected.append(event.event_type))

    permissions = PermissionManager()
    permissions.attach(kernel)

    registry = ResourceRegistry()
    registry.register(Resource(id="excl-slot", kind=ResourceKind.BROWSER, exclusive=True))
    resources = ResourceManager(registry)
    resources.attach(kernel)

    identity = CognitiveIdentity(identity_id="friday-gate-identity")
    identity.attach(kernel)

    cognitive = CognitiveStateManager()
    cognitive.attach(kernel)

    return collected, permissions, resources, identity, cognitive


def test_m4_gate(tmp_path) -> None:
    store_path = str(tmp_path / "m4_gate.jsonl")
    kernel = CognitiveKernel(store_path=store_path, auto_checkpoint_every=0)
    collected, _perm, resources, identity, _cog = _wire(kernel)

    # --- 1. A risky action is gated (never auto-granted) ----------------------
    _publish(
        kernel,
        "action.requested",
        {
            "action": "wire-money",
            "level": int(PermissionLevel.FINANCIAL),
            "trust_zone": TrustZone.TRUSTED.value,
            "reversible": True,
            "confidence": 1.0,
        },
    )
    _publish(
        kernel,
        "action.requested",
        {
            "action": "self-modify",
            "level": int(PermissionLevel.KERNEL),
            "trust_zone": TrustZone.TRUSTED.value,
            "reversible": True,
            "confidence": 1.0,
        },
    )
    granted = [e for e in collected if e == "permission.granted"]
    denied = [e for e in collected if e == "permission.denied"]
    assert denied, "a risky action must be gated to permission.denied"
    assert not granted, "no risky action may be auto-granted in the gate"

    # --- 2. Exclusive resource contended by two holders → exactly one grant ---
    _publish(
        kernel,
        "resource.requested",
        {"resource_id": "excl-slot", "holder": "holder-A"},
    )
    _publish(
        kernel,
        "resource.requested",
        {"resource_id": "excl-slot", "holder": "holder-B"},
    )
    allocated = [e for e in collected if e == "resource.allocated"]
    denied_res = [e for e in collected if e == "resource.denied"]
    assert len(allocated) == 1, "exactly one holder is granted the exclusive resource"
    assert len(denied_res) == 1, "the contending holder is denied"
    assert resources.holder_of("excl-slot") == "holder-A"

    # --- 3. Identity survives checkpoint→restore across a FRESH kernel --------
    _publish(kernel, "goal.state_changed", {"goal_id": "g-continuity", "state": "active"})
    _publish(kernel, "goal.state_changed", {"goal_id": "g-secondary", "state": "suspended"})
    assert identity.goal_states == {"g-continuity": "active", "g-secondary": "suspended"}

    identity_snapshot = identity.checkpoint()
    identity_id_before = identity.identity_id
    goal_states_before = dict(identity.goal_states)

    kernel.shutdown()

    # A brand-new kernel + a brand-new identity restore the continuity record.
    store_path2 = str(tmp_path / "m4_gate_session2.jsonl")
    kernel2 = CognitiveKernel(store_path=store_path2, auto_checkpoint_every=0)
    _collected2, _perm2, _res2, identity2, _cog2 = _wire(kernel2)

    identity2.restore(identity_snapshot)
    assert identity2.identity_id == identity_id_before
    assert identity2.goal_states == goal_states_before

    kernel2.shutdown()

    # --- 4. Determinism: the gate replays to an identical M4 event sequence ---
    seq_a = _run_gate(tmp_path, "det_a")
    seq_b = _run_gate(tmp_path, "det_b")
    assert seq_a == seq_b, "the M4 gate must be deterministic under DRY_RUN"
    # The gate actually exercised the M4 event families (not a trivial match).
    assert "permission.denied" in seq_a
    assert "resource.allocated" in seq_a
    assert "resource.denied" in seq_a


def _run_gate(tmp_path, tag: str) -> List[str]:
    """Build a fresh kernel + M4 subsystems, run the identical publish sequence,
    and return the ordered list of M4-relevant event types (Req 6.5 determinism).
    """
    store_path = str(tmp_path / f"{tag}.jsonl")
    kernel = CognitiveKernel(store_path=store_path, auto_checkpoint_every=0)
    collected, _perm, _res, _identity, _cog = _wire(kernel)

    # Risky action → denied.
    _publish(
        kernel,
        "action.requested",
        {
            "action": "wire-money",
            "level": int(PermissionLevel.FINANCIAL),
            "trust_zone": TrustZone.TRUSTED.value,
            "reversible": True,
            "confidence": 1.0,
        },
    )
    # Safe action → granted.
    _publish(
        kernel,
        "action.requested",
        {
            "action": "inspect",
            "level": int(PermissionLevel.OBSERVATION),
            "trust_zone": TrustZone.TRUSTED.value,
            "reversible": True,
            "confidence": 1.0,
        },
    )
    # Exclusive contention → one allocated, one denied.
    _publish(kernel, "resource.requested", {"resource_id": "excl-slot", "holder": "holder-A"})
    _publish(kernel, "resource.requested", {"resource_id": "excl-slot", "holder": "holder-B"})
    # Release by the holder → freed.
    _publish(kernel, "resource.released", {"resource_id": "excl-slot", "holder": "holder-A"})
    # Goal + execution activity.
    _publish(kernel, "goal.state_changed", {"goal_id": "g-continuity", "state": "active"})
    _publish(kernel, "action.executed", {"goal_id": "g-continuity", "capability": "search"})

    kernel.shutdown()

    return [et for et in collected if et in _M4_EVENT_TYPES]
