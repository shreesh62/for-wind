"""M20 — Reflection v2: the three higher reflection layers (consumers).

FAS §A2.10.1 defines five reflection layers. The existing
``friday/cognition/reflection.py::ReflectionEngine`` already covers the two lowest
layers (IMMEDIATE = its micro/action reflection; SESSION = its goal/session
reflection) and emits ``reflection.completed`` audit events. This module adds the
three higher **consumer** layers that subscribe to that stream and aggregate it:

    LongTermReflector       — across sessions, per (capability, environment)
    SkillReflector          — per capability (feeds the §A2.5 skill pipeline)
    ArchitecturalReflector  — meta / cross-capability, advisory only

plus a reusable wiring helper, :func:`attach_reflection_layers`, mirroring the M24
``attach_reactive_loop`` pattern.

Isolation invariant (Req 5.1/5.2 — "Reflection proposes; Memory decides"): this
module MUST NOT import ``friday.memory.*``, ``friday.competence.*`` or
``friday.recovery.*``, MUST NOT write long-term memory, and its ONLY side effect is
emitting JSON-safe ``reflection.*`` proposal events on the kernel bus via
``kernel.publish_event(make_event(...))``. Every handler is defensive and never
raises into the event bus (A2.14.2): it catches narrowly and degrades to a no-op.

The ``reflection.completed`` payload produced by the existing engine is:

    {"goal_id", "scale", "prediction_error" (0..1), "calibration" (0..1)}

It does NOT currently carry ``capability`` / ``environment`` / ``verified``, so the
layers read those defensively via ``payload.get(...)`` with documented fallbacks and
never assume they exist.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional, Tuple

from friday.events.event import make_event

# Default tuning knobs (all overridable via constructor / wiring kwargs).
_DEFAULT_WINDOW = 50          # bounded samples retained per aggregation key
_DEFAULT_MIN_SAMPLES = 5      # samples required before a proposal can fire
_DEFAULT_ERROR_THRESHOLD = 0.5   # long-term: mean error at/above → adverse trend
_DEFAULT_VERIFIED_THRESHOLD = 0.7  # skill: verified_rate at/above → mature
_DEFAULT_SKILL_ERROR_THRESHOLD = 0.3  # skill: mean error at/below → low-error
_DEFAULT_ARCH_MIN_CAPABILITIES = 3    # architectural: distinct hot capabilities
_DEFAULT_ARCH_ERROR_THRESHOLD = 0.5   # architectural: per-cap running-mean bound


def _payload_of(event: Any) -> Dict[str, Any]:
    """Return the event payload as a plain dict, defensively (never raises)."""
    payload = getattr(event, "payload", None)
    if isinstance(payload, dict):
        return payload
    try:
        return dict(payload) if payload else {}
    except Exception:  # noqa: BLE001 — malformed payload → treat as empty
        return {}


def _as_float(value: Any, default: float = 0.0) -> float:
    """Coerce ``value`` to a clamped [0, 1] float; fall back on any error."""
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:  # noqa: BLE001 — non-numeric → documented fallback
        return default


def _read_verified(payload: Dict[str, Any], prediction_error: float) -> bool:
    """Read the ``verified`` flag defensively with a documented proxy fallback.

    The ``reflection.completed`` payload does not currently carry ``verified``;
    when absent we use ``prediction_error < 0.5`` as a proxy for a low-error /
    likely-verified experience.
    """
    raw = payload.get("verified")
    if raw is None:
        return prediction_error < 0.5
    return bool(raw)


def _next_tick(kernel: Any) -> int:
    """Best-effort next logical time from kernel health; defaults to 1.

    Mirrors ``ReflectionEngine._next_tick`` so emissions stay ordered on the bus.
    """
    try:
        return int(kernel.health().get("tick", 0)) + 1
    except Exception:  # noqa: BLE001 — health must never break emission
        return 1


# ---------------------------------------------------------------------------
# C2 — Long-Term layer (across sessions)
# ---------------------------------------------------------------------------
class LongTermReflector:
    """Across-sessions reflection: recurring per-(capability, environment) trends.

    Consumes ``reflection.completed`` and keeps a bounded window of recent
    ``(prediction_error, calibration)`` samples per ``(capability, environment)``
    key. When a key has ``>= min_samples`` and its mean prediction error is
    ``>= error_threshold`` it emits a ``reflection.longterm`` proposal describing
    the adverse trend. Never writes memory; never raises into the bus.
    """

    def __init__(
        self,
        *,
        window: int = _DEFAULT_WINDOW,
        min_samples: int = _DEFAULT_MIN_SAMPLES,
        error_threshold: float = _DEFAULT_ERROR_THRESHOLD,
    ) -> None:
        self._window = max(1, int(window))
        self._min_samples = max(1, int(min_samples))
        self._error_threshold = float(error_threshold)
        self._kernel: Any = None
        # key=(capability, environment) → bounded deque of (error, calibration).
        self._samples: Dict[Tuple[str, str], Deque[Tuple[float, float]]] = {}

    def attach(self, kernel: Any) -> None:
        """Subscribe to ``reflection.completed`` (no-op without a kernel)."""
        if kernel is None:
            return
        self._kernel = kernel
        kernel.subscribe("reflection.completed", self._on_reflection)

    def _on_reflection(self, event: Any) -> None:
        """Append the sample; emit a trend proposal when the threshold is crossed."""
        try:
            payload = _payload_of(event)
            prediction_error = _as_float(payload.get("prediction_error"))
            calibration = _as_float(payload.get("calibration"))
            capability = str(payload.get("capability", "") or "")
            environment = str(payload.get("environment", "") or "")
            key = (capability, environment)

            window = self._samples.get(key)
            if window is None:
                window = deque(maxlen=self._window)
                self._samples[key] = window
            window.append((prediction_error, calibration))

            if len(window) < self._min_samples:
                return
            mean_error = sum(e for e, _ in window) / len(window)
            if mean_error < self._error_threshold:
                return

            mean_calibration = sum(c for _, c in window) / len(window)
            self._emit(
                capability=capability,
                environment=environment,
                sample_count=len(window),
                mean_error=mean_error,
                mean_calibration=mean_calibration,
            )
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _emit(
        self,
        *,
        capability: str,
        environment: str,
        sample_count: int,
        mean_error: float,
        mean_calibration: float,
    ) -> None:
        """Publish a JSON-safe ``reflection.longterm`` proposal (never memory)."""
        if self._kernel is None:
            return
        event = make_event(
            event_type="reflection.longterm",
            source="reflection",
            logical_time=_next_tick(self._kernel),
            payload={
                "capability": capability,
                "environment": environment,
                "sample_count": int(sample_count),
                "mean_error": float(mean_error),
                "mean_calibration": float(mean_calibration),
            },
        )
        self._kernel.publish_event(event)

    def trend(self, capability: str, environment: str) -> Dict[str, Any]:
        """Return the current aggregate for a ``(capability, environment)`` key."""
        key = (str(capability or ""), str(environment or ""))
        window = self._samples.get(key)
        if not window:
            return {
                "capability": key[0],
                "environment": key[1],
                "sample_count": 0,
                "mean_error": 0.0,
                "mean_calibration": 0.0,
            }
        count = len(window)
        return {
            "capability": key[0],
            "environment": key[1],
            "sample_count": count,
            "mean_error": sum(e for e, _ in window) / count,
            "mean_calibration": sum(c for _, c in window) / count,
        }


# ---------------------------------------------------------------------------
# C3 — Skill layer (per capability)
# ---------------------------------------------------------------------------
class SkillReflector:
    """Per-capability reflection feeding the §A2.5 skill-evolution pipeline.

    Consumes ``reflection.completed`` and aggregates, per capability, a bounded
    window of ``(prediction_error, verified)`` samples. When a capability reaches
    ``>= min_samples`` with ``verified_rate >= v_thresh`` AND
    ``mean_error <= e_thresh`` it emits a ``reflection.skill`` proposal flagging a
    skill-pipeline candidate. This is a PROPOSAL only — promotion remains the
    pipeline's/Memory's decision. Never writes memory; never raises into the bus.
    """

    def __init__(
        self,
        *,
        window: int = _DEFAULT_WINDOW,
        min_samples: int = _DEFAULT_MIN_SAMPLES,
        verified_threshold: float = _DEFAULT_VERIFIED_THRESHOLD,
        error_threshold: float = _DEFAULT_SKILL_ERROR_THRESHOLD,
    ) -> None:
        self._window = max(1, int(window))
        self._min_samples = max(1, int(min_samples))
        self._verified_threshold = float(verified_threshold)
        self._error_threshold = float(error_threshold)
        self._kernel: Any = None
        # capability → bounded deque of (prediction_error, verified_bool).
        self._samples: Dict[str, Deque[Tuple[float, bool]]] = {}

    def attach(self, kernel: Any) -> None:
        """Subscribe to ``reflection.completed`` (no-op without a kernel)."""
        if kernel is None:
            return
        self._kernel = kernel
        kernel.subscribe("reflection.completed", self._on_reflection)

    def _on_reflection(self, event: Any) -> None:
        """Aggregate per capability; emit a candidate proposal when mature."""
        try:
            payload = _payload_of(event)
            prediction_error = _as_float(payload.get("prediction_error"))
            capability = str(payload.get("capability", "") or "")
            verified = _read_verified(payload, prediction_error)

            window = self._samples.get(capability)
            if window is None:
                window = deque(maxlen=self._window)
                self._samples[capability] = window
            window.append((prediction_error, verified))

            if len(window) < self._min_samples:
                return
            count = len(window)
            mean_error = sum(e for e, _ in window) / count
            verified_rate = sum(1 for _, v in window if v) / count
            if verified_rate < self._verified_threshold:
                return
            if mean_error > self._error_threshold:
                return

            self._emit(
                capability=capability,
                sample_count=count,
                mean_error=mean_error,
                verified_rate=verified_rate,
            )
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _emit(
        self,
        *,
        capability: str,
        sample_count: int,
        mean_error: float,
        verified_rate: float,
    ) -> None:
        """Publish a JSON-safe ``reflection.skill`` candidate proposal."""
        if self._kernel is None:
            return
        event = make_event(
            event_type="reflection.skill",
            source="reflection",
            logical_time=_next_tick(self._kernel),
            payload={
                "capability": capability,
                "sample_count": int(sample_count),
                "mean_error": float(mean_error),
                "verified_rate": float(verified_rate),
                "candidate": True,
            },
        )
        self._kernel.publish_event(event)

    def summaries(self) -> Dict[str, Dict[str, Any]]:
        """Return the current per-capability summary (count, mean error, rate)."""
        result: Dict[str, Dict[str, Any]] = {}
        for capability, window in self._samples.items():
            count = len(window)
            if count == 0:
                result[capability] = {
                    "sample_count": 0,
                    "mean_error": 0.0,
                    "verified_rate": 0.0,
                }
                continue
            result[capability] = {
                "sample_count": count,
                "mean_error": sum(e for e, _ in window) / count,
                "verified_rate": sum(1 for _, v in window if v) / count,
            }
        return result


# ---------------------------------------------------------------------------
# C4 — Architectural layer (meta / cross-capability)
# ---------------------------------------------------------------------------
class ArchitecturalReflector:
    """Meta-reflection: is the architecture still serving the user?

    Consumes ``reflection.completed`` and tracks, per capability, a bounded window
    of prediction errors. The cross-capability meta-signal is the count of distinct
    capabilities whose running mean error is high (``>= error_threshold`` over
    ``>= min_samples``). When that count reaches ``min_capabilities`` it emits ONE
    advisory ``reflection.architectural`` proposal and latches, so it does not
    re-emit until the condition clears and re-crosses. Advisory only: mutates
    nothing, writes no memory, never raises into the bus.
    """

    def __init__(
        self,
        *,
        window: int = _DEFAULT_WINDOW,
        min_samples: int = _DEFAULT_MIN_SAMPLES,
        error_threshold: float = _DEFAULT_ARCH_ERROR_THRESHOLD,
        min_capabilities: int = _DEFAULT_ARCH_MIN_CAPABILITIES,
    ) -> None:
        self._window = max(1, int(window))
        self._min_samples = max(1, int(min_samples))
        self._error_threshold = float(error_threshold)
        self._min_capabilities = max(1, int(min_capabilities))
        self._kernel: Any = None
        # capability → bounded deque of prediction_error.
        self._samples: Dict[str, Deque[float]] = {}
        # Latch: True once a proposal was emitted; cleared when condition clears.
        self._latched = False

    def attach(self, kernel: Any) -> None:
        """Subscribe to ``reflection.completed`` (no-op without a kernel)."""
        if kernel is None:
            return
        self._kernel = kernel
        kernel.subscribe("reflection.completed", self._on_reflection)

    def _hot_capabilities(self) -> Tuple[str, ...]:
        """Capabilities whose running mean error is high over enough samples."""
        hot = []
        for capability, window in self._samples.items():
            if len(window) < self._min_samples:
                continue
            mean_error = sum(window) / len(window)
            if mean_error >= self._error_threshold:
                hot.append(capability)
        return tuple(sorted(hot))

    def _on_reflection(self, event: Any) -> None:
        """Update the meta-signal; emit one deduplicated advisory proposal."""
        try:
            payload = _payload_of(event)
            prediction_error = _as_float(payload.get("prediction_error"))
            capability = str(payload.get("capability", "") or "")

            window = self._samples.get(capability)
            if window is None:
                window = deque(maxlen=self._window)
                self._samples[capability] = window
            window.append(prediction_error)

            hot = self._hot_capabilities()
            crossed = len(hot) >= self._min_capabilities

            if not crossed:
                # Condition cleared — reset the latch so a future crossing re-emits.
                self._latched = False
                return
            if self._latched:
                # Already advised for this crossing; do not spam the bus.
                return

            self._latched = True
            self._emit(capabilities_affected=hot, metric=len(hot))
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _emit(self, *, capabilities_affected: Tuple[str, ...], metric: int) -> None:
        """Publish a JSON-safe advisory ``reflection.architectural`` proposal."""
        if self._kernel is None:
            return
        event = make_event(
            event_type="reflection.architectural",
            source="reflection",
            logical_time=_next_tick(self._kernel),
            payload={
                "reason": "persistent_miscalibration_across_capabilities",
                "capabilities_affected": list(capabilities_affected),
                "metric": int(metric),
            },
        )
        self._kernel.publish_event(event)


# ---------------------------------------------------------------------------
# C5 — Wiring helper
# ---------------------------------------------------------------------------
@dataclass
class ReflectionLayers:
    """Holder for the attached higher reflection layers (inspectable by callers)."""

    longterm: Optional[LongTermReflector]
    skill: Optional[SkillReflector]
    architectural: Optional[ArchitecturalReflector]


def attach_reflection_layers(
    kernel: Any,
    *,
    longterm: Optional[LongTermReflector] = None,
    skill: Optional[SkillReflector] = None,
    architectural: Optional[ArchitecturalReflector] = None,
    **thresholds: Any,
) -> ReflectionLayers:
    """Attach the three higher reflection layers to ``kernel`` in one place.

    Mirrors the M24 ``attach_reactive_loop`` pattern: any bootstrap gets the same
    wired layers instead of duplicating the subscription dance. Passing an existing
    layer reuses it; otherwise a fresh one is constructed. ``**thresholds`` are
    forwarded to freshly-constructed layers (unknown kwargs are ignored per layer).

    Inert without a kernel (no-op, returns a holder of the given/None layers). Each
    layer isolates its own ``attach`` exception so one failing layer never prevents
    the others from wiring and never crashes bootstrap (Req 6.3).
    """
    if kernel is None:
        # Inert: return whatever was injected (or None) without attaching.
        return ReflectionLayers(longterm=longterm, skill=skill, architectural=architectural)

    lt = longterm if longterm is not None else _make(LongTermReflector, thresholds)
    sk = skill if skill is not None else _make(SkillReflector, thresholds)
    arch = (
        architectural
        if architectural is not None
        else _make(ArchitecturalReflector, thresholds)
    )

    for layer in (lt, sk, arch):
        try:
            layer.attach(kernel)
        except Exception:  # noqa: BLE001 — one layer failing must not crash wiring
            continue

    return ReflectionLayers(longterm=lt, skill=sk, architectural=arch)


def _make(cls: Any, thresholds: Dict[str, Any]) -> Any:
    """Construct ``cls`` forwarding only the kwargs it accepts (ignore the rest)."""
    try:
        import inspect

        accepted = set(inspect.signature(cls.__init__).parameters) - {"self"}
        kwargs = {k: v for k, v in thresholds.items() if k in accepted}
        return cls(**kwargs)
    except Exception:  # noqa: BLE001 — defensive: fall back to defaults
        return cls()
