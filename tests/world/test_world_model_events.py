"""M15 — Event-emission integration tests for the WorldModel staleness sweep.

These are example/integration tests (not property tests) covering the acceptance
criteria that are NOT expressed as correctness properties:

- Req 4.4 — a stale high-impact belief emits a ``belief.stale_flagged`` kernel event
  whose payload carries the belief id and the recomputed freshness value.
- Req 4.5 — an all-fresh belief set yields an empty ``stale_beliefs(now)`` result.
- Req 5.9 — the WorldModel communicates outward exclusively via kernel events, routing
  through the kernel's public ``publish_event``; with no kernel attached the emission is
  a silent no-op and the sweep still returns its results (detection never depends on a
  live bus).

Populating the WorldModel
-------------------------
The public ``ingest`` path can only build beliefs with the M15 field DEFAULTS
(``ttl_seconds=None``, ``high_impact=False``, ``half_life_seconds=86400.0``), which
cannot exercise staleness/high-impact classification. Following the pattern used by the
M15 staleness property tests, fully-specified ``Belief`` instances are injected directly
into the authoritative belief collection ``WorldModel._fusion._beliefs_by_key`` — the
exact collection ``stale_beliefs`` iterates over. No production code is modified.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from friday.events.event import Event
from friday.world.belief import Belief
from friday.world.world_model import WorldModel

# The WorldModel default staleness threshold; freshness strictly below this is stale.
THRESHOLD = 0.1


class FakeKernel:
    """Minimal kernel stand-in matching the interface WorldModel.attach/_publish use.

    - ``subscribe(event_type, handler)`` records the subscription (WorldModel calls this
      inside ``attach`` for ``observation.received``).
    - ``query_world()`` returns a dict with a ``logical_time`` (read by the WorldModel to
      stamp the outbound event's best-effort logical time).
    - ``publish_event(event)`` captures the emitted Event into ``published`` so tests can
      assert on the ``belief.stale_flagged`` events routed through the kernel (Req 5.9).
    """

    def __init__(self, logical_time: int = 0) -> None:
        self.published: List[Event] = []
        self.subscriptions: List[Tuple[str, Callable[[Event], None]]] = []
        self._logical_time = logical_time

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        self.subscriptions.append((event_type, handler))

    def query_world(self) -> Dict[str, Any]:
        return {"logical_time": self._logical_time}

    def publish_event(self, event: Event) -> None:
        self.published.append(event)


def _stale_belief(*, high_impact: bool, description: str = "b") -> Belief:
    """A belief that is unambiguously stale at now=1000: observed long ago with a tiny
    half-life so freshness(1000) is effectively 0 (< THRESHOLD)."""
    return Belief(
        description=description,
        confidence=0.9,
        source="sensor",
        observed_at=0.0,
        half_life_seconds=1.0,  # elapsed = 1000 half-lives => freshness ~= 0
        high_impact=high_impact,
    )


def _fresh_belief(description: str = "fresh") -> Belief:
    """A belief that is fresh at now=1000: just observed, long half-life, no TTL."""
    return Belief(
        description=description,
        confidence=0.9,
        source="sensor",
        observed_at=1000.0,
        half_life_seconds=86400.0,
        high_impact=True,
    )


def _populate(wm: WorldModel, beliefs: List[Belief]) -> None:
    """Inject fully-specified beliefs into the authoritative belief store."""
    for index, belief in enumerate(beliefs):
        wm._fusion._beliefs_by_key[str(index)] = belief


def test_stale_high_impact_belief_emits_belief_stale_flagged():
    """Req 4.4 / 5.9: a stale high-impact belief emits exactly one belief.stale_flagged
    event, routed through kernel.publish_event, with payload {belief_id, freshness}."""
    kernel = FakeKernel()
    wm = WorldModel()  # default staleness_threshold = 0.1
    wm.attach(kernel)

    belief = _stale_belief(high_impact=True)
    _populate(wm, [belief])

    now = 1000.0
    result = wm.stale_beliefs(now)

    # The belief is returned as stale...
    assert belief.id in {b.id for b in result}

    # ...and exactly one belief.stale_flagged event was published (Req 4.4).
    flagged = [e for e in kernel.published if e.event_type == "belief.stale_flagged"]
    assert len(flagged) == 1

    event = flagged[0]
    assert event.source == "world_model"
    # Payload carries the belief id and the recomputed freshness (a float).
    assert event.payload["belief_id"] == belief.id
    freshness = event.payload["freshness"]
    assert isinstance(freshness, float)
    # Freshness is the value recomputed at `now` for this belief.
    assert freshness == belief.freshness(now)


def test_stale_non_high_impact_belief_does_not_emit_event():
    """Req 4.3/4.4: a stale belief that is NOT high_impact is still returned by the sweep
    but does NOT trigger a belief.stale_flagged event."""
    kernel = FakeKernel()
    wm = WorldModel()
    wm.attach(kernel)

    belief = _stale_belief(high_impact=False)
    _populate(wm, [belief])

    result = wm.stale_beliefs(1000.0)

    # Still detected as stale (inclusion does not depend on high_impact)...
    assert belief.id in {b.id for b in result}
    # ...but no event emitted because it does not gate an irreversible action.
    flagged = [e for e in kernel.published if e.event_type == "belief.stale_flagged"]
    assert flagged == []


def test_sweep_returns_results_with_no_kernel_attached():
    """Req 5.9: with NO kernel attached, stale_beliefs still returns the stale beliefs
    and emission is a silent no-op (detection never depends on a live bus)."""
    wm = WorldModel()  # no attach() => self._kernel is None
    belief = _stale_belief(high_impact=True)
    _populate(wm, [belief])

    # Does not raise even though a high-impact stale belief would normally emit.
    result = wm.stale_beliefs(1000.0)
    assert belief.id in {b.id for b in result}


def test_all_fresh_belief_set_yields_empty_result():
    """Req 4.5: when no belief is stale, stale_beliefs(now) returns an empty list."""
    kernel = FakeKernel()
    wm = WorldModel()
    wm.attach(kernel)

    _populate(wm, [_fresh_belief("a"), _fresh_belief("b"), _fresh_belief("c")])

    now = 1000.0
    # Sanity: every belief is fresh (freshness >= threshold) at now.
    for belief in wm._fusion.beliefs:
        assert belief.freshness(now) >= THRESHOLD

    assert wm.stale_beliefs(now) == []
    # No events emitted for an all-fresh set.
    flagged = [e for e in kernel.published if e.event_type == "belief.stale_flagged"]
    assert flagged == []
