"""Environment fingerprint change monitor (M15 — Environment Intelligence).

This module adds the kernel-attached *change-detection* half of Environment
Intelligence (FAS §A2.2). The pure :mod:`friday.perception.fingerprint` library
computes a deterministic ``EnvironmentFingerprint`` per observation; this monitor
tracks the last-seen fingerprint **per environment key** and, on a detected change,
emits invalidation proposal events so the Exploration Engine (A2.8) and competence
consumers re-explore / re-validate rather than silently reusing stale affordances.

Design tenets (see design.md, components C5–C6):

* **Event-driven / replay-safe.** On a detected change the monitor emits, via
  ``kernel.publish_event(make_event(...))``, an ``environment.fingerprint_changed``
  event followed by an ``environment.capabilities_invalidated`` proposal. Both
  payloads are plain JSON-safe dicts (lists/strings/ints only) so the append-only
  ``EventStore`` stays replay-compatible (Requirement 6.1).
* **Inert without a kernel.** ``attach(None)`` and construction without a kernel are
  no-ops; ``observe`` still tracks fingerprints and returns a status but emits
  nothing (Requirement 6.2).
* **Never raises into the bus.** ``observe`` wraps its body and degrades to a safe
  status on any internal error; it never propagates (Requirement 6.3).
* **Proposal-only.** The monitor mutates/deletes NO competence and touches no
  Exploration Engine state; it only emits ``environment.*`` events that those
  subsystems consume, kernel-mediated (Requirement 4.2).
* **Bounded memory.** The per-key registry is an ``OrderedDict`` capped at
  ``max_environments``; the oldest key is evicted on overflow (Requirement 3.4).
* **Axiom 15.** The monitor is fully generic over ``env_key`` + ``WorldState``; it
  contains no application-, site-, or window-title-specific logic. Identity is the
  opaque ``env_key`` the caller supplies.

Perception is not itself a kernel event today, so the monitor is driven by explicit
``observe(...)`` calls (e.g. from the executor's perception cycle). We deliberately do
NOT subscribe to any ``perception.*`` event: no such event type exists and inventing
one would be out of scope for this milestone.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any, List, Optional

from friday.events.event import make_event
from friday.perception.fingerprint import (
    EnvironmentFingerprint,
    compute_fingerprint,
)

__all__ = [
    "FingerprintMonitor",
    "attach_fingerprint_monitor",
]

_logger = logging.getLogger(__name__)

# Event types emitted by the monitor (only these `environment.*` events).
_EVENT_FINGERPRINT_CHANGED = "environment.fingerprint_changed"
_EVENT_CAPABILITIES_INVALIDATED = "environment.capabilities_invalidated"


def _next_tick(kernel: Any) -> int:
    """Best-effort next logical time from kernel health; defaults to 1.

    Mirrors the reflection-layer/reactive-loop emission ordering pattern so emitted
    ``environment.*`` events stay ordered on the bus. Never raises.
    """
    try:
        return int(kernel.health().get("tick", 0)) + 1
    except Exception:  # noqa: BLE001 — health must never break emission ordering
        # Deliberate: a kernel whose health() misbehaves must not stop us emitting;
        # fall back to a defined logical time rather than propagating.
        return 1


class FingerprintMonitor:
    """Tracks the last-seen fingerprint per environment key and detects changes.

    The monitor keeps a bounded ``OrderedDict`` of ``env_key -> last-seen
    EnvironmentFingerprint``. Each :meth:`observe` computes the current fingerprint,
    compares it to the stored one, and returns ``"first_seen"`` / ``"unchanged"`` /
    ``"changed"``. On ``"changed"`` (and only when a kernel is attached) it emits an
    ``environment.fingerprint_changed`` event followed by an
    ``environment.capabilities_invalidated`` proposal.
    """

    def __init__(self, *, max_environments: int = 128) -> None:
        # Bound must be at least 1 so the registry can hold a baseline.
        self._max_environments = max(1, int(max_environments))
        # env_key -> last-seen EnvironmentFingerprint. OrderedDict preserves
        # recency order (newest moved to the end) for oldest-first eviction.
        self._registry: "OrderedDict[str, EnvironmentFingerprint]" = OrderedDict()
        self._kernel: Any = None

    # ------------------------------------------------------------------ wiring
    def attach(self, kernel: Any) -> None:
        """Store the kernel (no-op if ``None``).

        Perception is not a kernel event today, so there is nothing to subscribe to:
        the monitor is driven by explicit :meth:`observe` calls. We intentionally do
        not invent a ``perception.*`` event type.
        """
        if kernel is None:
            return
        self._kernel = kernel

    # ------------------------------------------------------------- observation
    def observe(
        self,
        env_key: Any,
        world_state: Any,
        *,
        platform: Optional[str] = None,
        capability_version: str = "",
        layout_version: str = "",
    ) -> str:
        """Observe an environment; return ``first_seen`` / ``unchanged`` / ``changed``.

        * Not present in the registry -> record baseline (newest), emit NOTHING,
          return ``"first_seen"``.
        * Present with an equal digest -> refresh recency, emit NOTHING, return
          ``"unchanged"``.
        * Present with a differing digest -> update the stored fingerprint, compute
          the changed component keys, emit ``environment.fingerprint_changed`` then
          ``environment.capabilities_invalidated`` (only when a kernel is attached),
          and return ``"changed"``.

        Never raises: any internal error degrades to a safe status (Requirement 6.3).
        The monitor mutates no competence — it only emits events.
        """
        try:
            key = str(env_key)
            current = compute_fingerprint(
                world_state,
                platform=platform,
                capability_version=capability_version,
                layout_version=layout_version,
            )

            last = self._registry.get(key)

            if last is None:
                # First observation of this env_key: record a baseline and mark it
                # newest. No change is reported (Requirement 3.3).
                self._store(key, current)
                return "first_seen"

            if current.digest == last.digest:
                # Unchanged: refresh recency (treat as newest) but emit nothing.
                self._registry.move_to_end(key)
                return "unchanged"

            # Changed: update the stored fingerprint (stays newest) and figure out
            # which generic component signals diverged.
            changed_components = self._changed_components(last, current)
            self._store(key, current)

            # Emit only when a kernel is attached (inert otherwise, Requirement 6.2).
            if self._kernel is not None:
                self._emit_change(
                    env_key=key,
                    previous_digest=last.digest,
                    current_digest=current.digest,
                    changed_components=changed_components,
                )
            return "changed"
        except Exception:  # noqa: BLE001 — observe must never raise into a caller/bus
            # Deliberate: a malformed WorldState or transient internal error degrades
            # to a safe "unchanged" (no event, no mutation) rather than propagating.
            # We do not blanket-swallow silently: log for observability.
            _logger.debug("FingerprintMonitor.observe failed defensively", exc_info=True)
            return "error"

    # --------------------------------------------------------------- accessors
    def last(self, env_key: Any) -> Optional[EnvironmentFingerprint]:
        """Return the last-seen fingerprint for ``env_key`` (or ``None``)."""
        try:
            return self._registry.get(str(env_key))
        except Exception:  # noqa: BLE001 — accessor must stay total
            return None

    @property
    def environment_count(self) -> int:
        """Number of environment keys currently tracked (for testing)."""
        return len(self._registry)

    # ----------------------------------------------------------------- helpers
    def _store(self, key: str, fingerprint: EnvironmentFingerprint) -> None:
        """Insert/update ``key`` as newest and enforce the ``max_environments`` bound."""
        # Ensure the key is (re)positioned as newest.
        if key in self._registry:
            self._registry[key] = fingerprint
            self._registry.move_to_end(key)
        else:
            self._registry[key] = fingerprint
        # Evict oldest (front) entries beyond the bound (Requirement 3.4).
        while len(self._registry) > self._max_environments:
            self._registry.popitem(last=False)

    @staticmethod
    def _changed_components(
        last: EnvironmentFingerprint, current: EnvironmentFingerprint
    ) -> List[str]:
        """Return the sorted list of component keys that diverged between two prints.

        Compares the ``.components`` dicts key-by-key (over the union of keys) and
        appends ``"ui_fingerprint"`` when the interactive-surface digest changed.
        Result is JSON-safe (a list of strings) and deterministically ordered.
        """
        last_components = dict(getattr(last, "components", {}) or {})
        current_components = dict(getattr(current, "components", {}) or {})

        keys = set(last_components) | set(current_components)
        changed = [
            str(key)
            for key in keys
            if last_components.get(key, "") != current_components.get(key, "")
        ]
        changed.sort()

        if getattr(last, "ui_fingerprint", "") != getattr(current, "ui_fingerprint", ""):
            changed.append("ui_fingerprint")

        return changed

    def _emit_change(
        self,
        *,
        env_key: str,
        previous_digest: str,
        current_digest: str,
        changed_components: List[str],
    ) -> None:
        """Emit the change + invalidation proposal events (JSON-safe payloads).

        Emits exactly one ``environment.fingerprint_changed`` followed by one
        ``environment.capabilities_invalidated``. Both payloads contain only
        strings/lists so the EventStore stays replay-compatible (Requirement 6.1).
        """
        # Defensive normalization to guarantee JSON-safe primitives.
        safe_changed = [str(component) for component in changed_components]

        changed_event = make_event(
            event_type=_EVENT_FINGERPRINT_CHANGED,
            source="perception",
            logical_time=_next_tick(self._kernel),
            payload={
                "env_key": str(env_key),
                "previous_digest": str(previous_digest),
                "current_digest": str(current_digest),
                "changed_components": list(safe_changed),
            },
        )
        self._kernel.publish_event(changed_event)

        invalidated_event = make_event(
            event_type=_EVENT_CAPABILITIES_INVALIDATED,
            source="perception",
            logical_time=_next_tick(self._kernel),
            payload={
                "env_key": str(env_key),
                "reason": "fingerprint_changed",
                "changed_components": list(safe_changed),
            },
        )
        self._kernel.publish_event(invalidated_event)


def attach_fingerprint_monitor(
    kernel: Any,
    *,
    monitor: Optional[FingerprintMonitor] = None,
    max_environments: int = 128,
) -> FingerprintMonitor:
    """Attach a :class:`FingerprintMonitor` to ``kernel`` in one reusable place.

    Mirrors the ``attach_reflection_layers`` / ``attach_reactive_loop`` pattern: build
    or reuse a monitor, wire it, and return it so bootstraps do not duplicate the
    wiring dance.

    Passing an existing ``monitor`` reuses it; otherwise a fresh one is constructed
    with ``max_environments``. If ``kernel is None`` the monitor is returned WITHOUT
    attaching (an inert no-op holder), so importing/wiring never crashes bootstrap and
    the default path is unchanged (Requirement 6.2).
    """
    mon = monitor if monitor is not None else FingerprintMonitor(
        max_environments=max_environments
    )
    if kernel is None:
        # Inert: return the (given/new) monitor without attaching.
        return mon
    mon.attach(kernel)
    return mon
