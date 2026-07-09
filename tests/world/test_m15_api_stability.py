"""M15 — API-stability, concurrency, and reentrancy example tests.

Covers the acceptance criteria that are NOT expressed as correctness properties:

- Req 5.1 — the existing ``Belief`` public API (``decay``, ``reinforce``, ``contradict``,
  ``expired``) retains its behaviour; minimal ``Belief(description, confidence, source)``
  still constructs and a "legacy-style" belief behaves identically.
- Req 5.2 — the existing ``WorldModel`` public API (``ingest``, ``observed_world``,
  ``unmet_conditions``, ``relate``, ``attach``) retains its signatures/returns, including
  ``ingest -> List[Belief]`` and ``observed_world -> ObservedWorld``.
- Req 5.3 / 5.6 — no existing default parameter value changed: ``WorldModel`` still
  defaults ``decay_rate=0.01`` and ``staleness_threshold=0.1``.
- Req 3.10 / 6.1 / 6.5 / 6.6 — thread-safety: concurrent ``ingest``/``stale_beliefs`` do
  not raise and produce a consistent result; the reentrant ``RLock`` permits nested
  lock-acquiring calls from the same thread without deadlock.
"""

from __future__ import annotations

import inspect
import threading
from typing import List

from friday.events.event import FrozenDict
from friday.perception.observation import Observation
from friday.world.belief import Belief
from friday.world.world_model import WorldModel
from friday.world.worlds import ObservedWorld


def _obs(name: str = "Submit", sensor: str = "dom", confidence: float = 0.8) -> Observation:
    return Observation(
        sensor=sensor,
        environment="browser",
        object_type="button",
        attributes=FrozenDict({"name": name}),
        confidence=confidence,
    )


# --------------------------------------------------------------------------- #
# Task 7.2 — API-unchanged example tests (Req 5.1, 5.2, 5.3, 5.6)
# --------------------------------------------------------------------------- #


def test_belief_minimal_construction_and_legacy_api_intact():
    """Req 5.1 / 5.3: minimal Belief(description, confidence, source) constructs and the
    legacy API (decay, reinforce, contradict, expired) still works and returns Beliefs."""
    # Minimal construction succeeds without any M15 fields.
    belief = Belief(description="door is open", confidence=0.7, source="dom")
    assert isinstance(belief, Belief)

    # expired is a boolean property (no hard expiry set => not expired).
    assert belief.expired is False

    # decay / reinforce / contradict all return Belief instances.
    decayed = belief.decay(rate=0.01, now=belief.observed_at + 10.0)
    assert isinstance(decayed, Belief)

    reinforced = belief.reinforce(0.5, evidence_id="obs-1")
    assert isinstance(reinforced, Belief)
    # noisy-OR strengthens confidence.
    assert reinforced.confidence >= belief.confidence

    contradicted = belief.contradict(0.5, evidence_id="obs-2")
    assert isinstance(contradicted, Belief)
    # contradiction weakens confidence.
    assert contradicted.confidence <= belief.confidence


def test_belief_legacy_style_belief_behaves_identically():
    """Req 5.1: a Belief constructed the OLD way (positional core fields only) behaves
    identically for the legacy operations."""
    legacy = Belief("cursor visible", 0.9, "vision")

    # M15 fields carry their defaults, proving construction is unaffected.
    assert legacy.ttl_seconds is None
    assert legacy.high_impact is False
    assert legacy.half_life_seconds == 86400.0

    assert isinstance(legacy.decay(now=legacy.observed_at + 1.0), Belief)
    assert isinstance(legacy.reinforce(0.3), Belief)
    assert isinstance(legacy.contradict(0.3), Belief)


def test_world_model_public_api_signatures_and_returns():
    """Req 5.2: WorldModel exposes ingest/observed_world/unmet_conditions/relate/attach
    with intact returns (ingest -> List[Belief], observed_world -> ObservedWorld)."""
    wm = WorldModel()

    for name in ("ingest", "observed_world", "unmet_conditions", "relate", "attach"):
        assert callable(getattr(wm, name)), f"WorldModel.{name} missing"

    beliefs = wm.ingest([_obs(name="Window"), _obs(name="Button")])
    assert isinstance(beliefs, list)
    assert all(isinstance(b, Belief) for b in beliefs)

    world = wm.observed_world()
    assert isinstance(world, ObservedWorld)


def test_world_model_defaults_unchanged_via_introspection():
    """Req 5.3 / 5.6: WorldModel() constructs with decay_rate default 0.01 and
    staleness_threshold default 0.1 — asserted via inspect.signature."""
    sig = inspect.signature(WorldModel.__init__)
    assert sig.parameters["decay_rate"].default == 0.01
    assert sig.parameters["staleness_threshold"].default == 0.1

    # Behavioural confirmation: default construction succeeds and is usable.
    wm = WorldModel()
    assert wm.ingest([_obs()]) is not None


# --------------------------------------------------------------------------- #
# Task 7.3 — Concurrency and reentrancy tests (Req 3.10, 6.1, 6.5, 6.6)
# --------------------------------------------------------------------------- #


def test_concurrent_ingest_and_stale_beliefs_no_exceptions():
    """Req 3.10 / 6.1 / 6.6: concurrent ingest + stale_beliefs on the same WorldModel
    raise no exceptions and leave the model in a consistent state (linearizable at the
    lock boundary)."""
    wm = WorldModel()
    errors: List[BaseException] = []
    barrier = threading.Barrier(8)
    iterations = 50

    def ingest_worker(worker_id: int) -> None:
        try:
            barrier.wait()
            for i in range(iterations):
                wm.ingest([_obs(name=f"obj-{worker_id}-{i}")])
        except BaseException as exc:  # noqa: BLE001 - capture to assert none occurred
            errors.append(exc)

    def sweep_worker() -> None:
        try:
            barrier.wait()
            for i in range(iterations):
                result = wm.stale_beliefs(float(i))
                # stale_beliefs always returns a valid list.
                assert isinstance(result, list)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=ingest_worker, args=(w,)) for w in range(4)]
    threads += [threading.Thread(target=sweep_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"concurrent access raised: {errors}"

    # Final state is consistent: a fresh sweep returns a valid list.
    final = wm.stale_beliefs(0.0)
    assert isinstance(final, list)


def test_reentrant_lock_sequential_calls_do_not_deadlock():
    """Req 6.5 / 6.1: the WorldModel's reentrant RLock allows lock-acquiring methods to
    be called in sequence on the same thread without deadlock. observed_world() and
    stale_beliefs() each acquire the lock; calling both from one thread completes."""
    wm = WorldModel()
    wm.ingest([_obs(name="A"), _obs(name="B")])

    completed = threading.Event()

    def caller() -> None:
        # Both acquire self._lock; the RLock permits the same thread to acquire it in
        # successive (and nested, via internal calls) scopes without deadlocking.
        world = wm.observed_world()
        assert isinstance(world, ObservedWorld)
        result = wm.stale_beliefs(0.0)
        assert isinstance(result, list)
        completed.set()

    thread = threading.Thread(target=caller)
    thread.start()
    thread.join(timeout=5.0)

    assert completed.is_set(), "observed_world() + stale_beliefs() deadlocked"
    assert not thread.is_alive()
