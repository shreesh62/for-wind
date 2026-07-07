"""M4-Gaps Task 6.2 — kernel-event integration test (safety/resources/identity/state).

Builds a REAL ``CognitiveKernel`` and attaches all four M4-gap subsystems — the
``PermissionManager``, the ``ResourceManager`` (over a pre-populated
``ResourceRegistry``), the ``CognitiveIdentity``, and the
``CognitiveStateManager`` — then drives ``action.requested`` /
``resource.requested`` / ``resource.released`` / ``goal.state_changed`` /
``action.executed`` events through ``kernel.publish_event`` and asserts the
expected ``permission.*`` / ``resource.*`` events land on the event log and the
identity / cognitive-state are updated.

Everything flows through ``kernel.subscribe`` / ``kernel.publish_event`` — no M4
subsystem is called directly to route an event (Req 6.1). The kernel routes
synchronously in ``_persist_and_route``, so by the time a ``publish_event``
returns the whole nested causal chain is already on the log. To stay
deterministic the scheduler thread is never started; every event is published
synchronously.

Runs under ``FRIDAY_DRY_RUN=1`` so no real filesystem/LLM/OS/credential surface
is touched.

Validates: Requirements 6.1, 7.2
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from typing import List

from friday.cognition.state import CognitiveMode, CognitiveStateManager
from friday.events.event import make_event
from friday.identity.identity import CognitiveIdentity
from friday.kernel.kernel import CognitiveKernel
from friday.resources.registry import ResourceRegistry
from friday.resources.scheduler import ResourceManager
from friday.resources.types import Resource, ResourceKind
from friday.safety.permission import PermissionLevel, PermissionManager, TrustZone


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


def test_m4_kernel_event_integration(tmp_path) -> None:
    kernel = CognitiveKernel(
        store_path=str(tmp_path / "m4.jsonl"), auto_checkpoint_every=0
    )

    # Collector subscribed FIRST so it records every event in causal order,
    # including the nested events subsystems publish from their handlers.
    collected: List[str] = []
    kernel.subscribe("*", lambda event: collected.append(event.event_type))

    # A registry pre-populated with a couple of resources, then the manager.
    registry = ResourceRegistry()
    registry.register(
        Resource(id="browser-slot", kind=ResourceKind.BROWSER, exclusive=True)
    )
    registry.register(
        Resource(id="compute-pool", kind=ResourceKind.COMPUTE, exclusive=False)
    )

    # Wire all four subsystems — ALL routing is via kernel events (Req 6.1).
    permissions = PermissionManager()
    permissions.attach(kernel)

    resources = ResourceManager(registry)
    resources.attach(kernel)

    identity = CognitiveIdentity(identity_id="friday-identity")
    identity.attach(kernel)

    cognitive = CognitiveStateManager()
    cognitive.attach(kernel)

    # --- Safety: a KERNEL-level action is forbidden autonomously → denied -----
    _publish(
        kernel,
        "action.requested",
        {
            "action": "self-modify-kernel",
            "level": int(PermissionLevel.KERNEL),
            "trust_zone": TrustZone.TRUSTED.value,
            "reversible": True,
            "confidence": 1.0,
        },
    )
    assert "permission.denied" in collected

    # --- Safety: an OBSERVATION action in a TRUSTED zone → granted ------------
    _publish(
        kernel,
        "action.requested",
        {
            "action": "inspect-screen",
            "level": int(PermissionLevel.OBSERVATION),
            "trust_zone": TrustZone.TRUSTED.value,
            "reversible": True,
            "confidence": 1.0,
        },
    )
    assert "permission.granted" in collected

    # --- Resources: exclusive resource granted to A, then denied to B ---------
    _publish(
        kernel,
        "resource.requested",
        {"resource_id": "browser-slot", "holder": "holder-A"},
    )
    assert "resource.allocated" in collected
    assert resources.holder_of("browser-slot") == "holder-A"

    _publish(
        kernel,
        "resource.requested",
        {"resource_id": "browser-slot", "holder": "holder-B"},
    )
    assert "resource.denied" in collected
    # The original holder is unchanged after the contended request (Req 3.3).
    assert resources.holder_of("browser-slot") == "holder-A"

    # --- Identity + CognitiveState: a goal goes active ------------------------
    _publish(
        kernel,
        "goal.state_changed",
        {"goal_id": "goal-42", "state": "active"},
    )
    # Identity recorded the goal transition (Req 4.3).
    assert identity.goal_states.get("goal-42") == "active"
    # CognitiveState focused the active goal (Req 5.3).
    snap = cognitive.snapshot()
    assert snap.focus == "goal-42"
    assert snap.active_goal == "goal-42"

    # --- CognitiveState: an executed action enters EXECUTION mode (Req 5.2) ---
    _publish(
        kernel,
        "action.executed",
        {"goal_id": "goal-42", "capability": "search"},
    )
    assert cognitive.snapshot().mode == CognitiveMode.EXECUTION

    # --- Identity records the checkpoint path from kernel.checkpoint (Req 4.4)-
    checkpoint_path = kernel.checkpoint()
    assert identity.last_checkpoint == checkpoint_path

    kernel.shutdown()

    # ------------------------------------------------------------------ #
    # Ordering sanity: the allocation precedes the contended denial.
    # ------------------------------------------------------------------ #
    i_alloc = collected.index("resource.allocated")
    i_denied = collected.index("resource.denied")
    assert i_alloc < i_denied, "allocation precedes the contended denial"
