"""Ch 31 — closed-loop motor control (observe→predict→move→observe→correct).

The Motor System never issues a blind ``pyautogui.click(x, y)``. It acquires a
re-verifiable :class:`TargetLock`, moves in increments while comparing the
observed cursor position against the predicted trajectory, corrects on drift,
and re-verifies the target is still present on arrival. This is FAS Ch 31's
core distinction from open-loop RPA.

Coordinate-space assumption
---------------------------
Every physical move is routed through :meth:`DisplayManager.to_physical` so a
target expressed in logical coordinates lands correctly under any DPI/scale.
Under ``FRIDAY_DRY_RUN=1`` the default :class:`DisplayManager` provides a single
1920x1080 monitor at ``scale == 1.0``, so *physical == logical*. All arrival /
tolerance / residual math therefore lives in one consistent coordinate space:
``backend.position()`` (physical) is compared directly against
``target.center`` (physical, equal to logical at scale 1.0). The simulated
cursor inside :class:`MotorBackend` makes this fully deterministic for tests.

Under ``FRIDAY_DRY_RUN=1`` nothing in this module touches the real
``pyautogui`` — :class:`MotorBackend` uses an internal simulated cursor.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from friday.actions.result import ActionEvidence, ActionResult, ActionStatus
from friday.perception.contracts import SensorContract
from friday.perception.observation import Observation
from friday.perception.types import BoundingBox, PerceptionSource
from friday.world.worlds import ObservedWorld


# --------------------------------------------------------------------------- #
# Motion profiles
# --------------------------------------------------------------------------- #


class MotionProfile(str, Enum):
    """Ch 31 — movement style trading speed vs. precision vs. safety."""

    PRECISE = "precise"   # small steps, verify each, slow settle — default for clicks
    FAST = "fast"         # larger steps, minimal correction — coarse repositioning
    SMOOTH = "smooth"     # human-like eased trajectory — demos / anti-bot contexts
    SAFE = "safe"         # slowest, re-acquires target before every step — risky UI


@dataclass(frozen=True)
class _ProfileParams:
    """Per-profile tuning knobs for the closed loop."""

    step_fraction: float          # fraction of the remaining vector to traverse
    reacquire_each_step: bool     # re-acquire the target before every step
    settle: float                 # settle time (seconds) after a move


PROFILE_PARAMS = {
    MotionProfile.PRECISE: _ProfileParams(step_fraction=0.5, reacquire_each_step=False, settle=0.02),
    MotionProfile.FAST: _ProfileParams(step_fraction=0.9, reacquire_each_step=False, settle=0.0),
    MotionProfile.SMOOTH: _ProfileParams(step_fraction=0.4, reacquire_each_step=False, settle=0.01),
    MotionProfile.SAFE: _ProfileParams(step_fraction=0.34, reacquire_each_step=True, settle=0.03),
}


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TargetLock:
    """Ch 31 — a resolved, re-verifiable handle on a target object."""

    target_text: str                     # semantic description used to acquire
    bbox: BoundingBox                    # last-known physical bounds
    center: Tuple[int, int]              # physical click point
    monitor_index: int
    confidence: float                    # 0..1 — acquisition confidence
    source: PerceptionSource             # UIA (preferred) or OCR/VISION
    acquired_at: float

    def __post_init__(self) -> None:
        clamped = max(0.0, min(1.0, self.confidence))
        object.__setattr__(self, "confidence", clamped)


@dataclass
class MotorStep:
    """One increment of a closed-loop move (for evidence + property testing)."""

    from_xy: Tuple[int, int]
    to_xy: Tuple[int, int]
    predicted_xy: Tuple[int, int]
    observed_xy: Tuple[int, int]
    corrected: bool
    residual: float                      # distance |observed - predicted|


@dataclass
class MotorResult:
    """Ch 31 — outcome of a closed-loop motor operation."""

    action: str                          # "move" | "click" | "type" | "scroll"
    success: bool
    final_lock: Optional[TargetLock]
    steps: List[MotorStep]
    evidence: ActionEvidence
    error: Optional[str] = None

    def to_action_result(self) -> ActionResult:
        """Bridge to the universal :class:`ActionResult` contract."""
        target = self.final_lock.target_text if self.final_lock else ""
        if self.success:
            return ActionResult.success(
                action=self.action,
                target=target,
                evidence=self.evidence,
            )
        # Failure is repairable — expose it as NEEDS_REPAIR so the deliberator
        # can attempt an alternative rather than treating it as terminal.
        result = ActionResult.failed(
            action=self.action,
            error=self.error or "motor_failed",
            target=target,
            error_category="motor",
            repair_hints=["reacquire_target", "retry", "increase_tolerance"],
            evidence=self.evidence,
        )
        result.status = ActionStatus.NEEDS_REPAIR
        result.message = f"{self.action} needs repair: {self.error or 'motor_failed'}"
        return result


# --------------------------------------------------------------------------- #
# Backend (wraps pyautogui; simulated under DRY_RUN)
# --------------------------------------------------------------------------- #


def _is_dry_run() -> bool:
    return os.environ.get("FRIDAY_DRY_RUN", "0") == "1"


class MotorBackend:
    """Ch 31 — thin actuator wrapping ``pyautogui``.

    Under ``FRIDAY_DRY_RUN=1`` (the default detection) the real ``pyautogui`` is
    never imported or touched: an internal simulated cursor position (starting
    at ``(0, 0)``) is maintained instead. ``move`` / ``click`` set the cursor;
    ``position`` reads it back. Tests may construct their own backend (or a
    subclass) and inject it into :class:`MotorSystem`.
    """

    def __init__(self, dry_run: Optional[bool] = None) -> None:
        self._dry_run = _is_dry_run() if dry_run is None else dry_run
        self._pos: Tuple[int, int] = (0, 0)
        self._pyautogui = None
        if not self._dry_run:  # pragma: no cover - real OS path, not run under DRY_RUN
            import pyautogui  # type: ignore

            self._pyautogui = pyautogui
            self._pos = tuple(pyautogui.position())

    def move(self, x: int, y: int) -> None:
        """Move the cursor to physical ``(x, y)``."""
        if self._dry_run:
            self._pos = (int(x), int(y))
            return
        self._pyautogui.moveTo(x, y)  # pragma: no cover
        self._pos = (int(x), int(y))  # pragma: no cover

    def click(self, x: int, y: int) -> None:
        """Click at physical ``(x, y)``."""
        if self._dry_run:
            self._pos = (int(x), int(y))
            return
        self._pyautogui.click(x, y)  # pragma: no cover
        self._pos = (int(x), int(y))  # pragma: no cover

    def type(self, text: str) -> None:
        """Type ``text`` at the current focus."""
        if self._dry_run:
            return
        self._pyautogui.typewrite(text)  # pragma: no cover

    def scroll(self, clicks: int) -> None:
        """Scroll by ``clicks`` (positive up, negative down)."""
        if self._dry_run:
            return
        self._pyautogui.scroll(clicks)  # pragma: no cover

    def position(self) -> Tuple[int, int]:
        """Observe the current cursor position (physical)."""
        if self._dry_run:
            return self._pos
        return tuple(self._pyautogui.position())  # pragma: no cover


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #


def distance(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    """Euclidean distance between two points."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def step_toward(
    src: Tuple[int, int], dst: Tuple[int, int], fraction: float
) -> Tuple[int, int]:
    """Return a point a ``fraction`` of the way from ``src`` toward ``dst``."""
    fraction = max(0.0, min(1.0, fraction))
    nx = src[0] + (dst[0] - src[0]) * fraction
    ny = src[1] + (dst[1] - src[1]) * fraction
    return (int(round(nx)), int(round(ny)))


def _source_of(obs: Observation) -> PerceptionSource:
    """Best-effort perception source for an observation."""
    raw = obs.attributes.get("source") if obs.attributes else None
    for candidate in (raw, obs.sensor):
        if candidate is None:
            continue
        if isinstance(candidate, PerceptionSource):
            return candidate
        try:
            return PerceptionSource(str(candidate).lower())
        except ValueError:
            continue
    return PerceptionSource.VISION


# Source preference ordering: UIA (semantic) is preferred over OCR/vision.
_SOURCE_RANK = {
    PerceptionSource.UIA: 0,
    PerceptionSource.BROWSER: 1,
    PerceptionSource.OCR: 2,
    PerceptionSource.VISION: 3,
    PerceptionSource.SCREEN: 4,
    PerceptionSource.PROCESS: 5,
}


def _match_text(obs: Observation) -> str:
    attrs = obs.attributes or {}
    return str(attrs.get("text") or attrs.get("name") or "")


# --------------------------------------------------------------------------- #
# MotorSystem
# --------------------------------------------------------------------------- #


class MotorSystem:
    """Ch 31 — closed-loop motor control (observe→predict→move→observe→correct)."""

    def __init__(
        self,
        sensors: List[SensorContract],
        display,
        backend: Optional[MotorBackend] = None,
        max_steps: int = 12,
        arrival_tolerance: int = 3,
    ) -> None:
        self._sensors = list(sensors)
        self._display = display
        self._backend = backend if backend is not None else MotorBackend()
        self.max_steps = max_steps
        self.arrival_tolerance = arrival_tolerance

    # --- observation helpers --------------------------------------------- #

    def _observe(self) -> List[Observation]:
        observations: List[Observation] = []
        for sensor in self._sensors:
            try:
                observations.extend(sensor.observe())
            except Exception:  # pragma: no cover - defensive; sensors mocked in tests
                continue
        return observations

    def _observe_cursor(self) -> Tuple[int, int]:
        return self._backend.position()

    def _observe_world(self) -> ObservedWorld:
        # acquire_target re-observes via sensors directly; a fresh empty world
        # is a valid ObservedWorld handle for the read-only acquisition path.
        return ObservedWorld()

    # --- acquisition (read-only, RiskLevel.OBSERVE) ---------------------- #

    def acquire_target(
        self, description: str, world: ObservedWorld
    ) -> Optional[TargetLock]:
        """Resolve a re-verifiable :class:`TargetLock` for ``description``.

        Returns ``None`` when no observation matches. When a matching object
        appears in both a UIA-source and an OCR/vision-source observation, the
        UIA source is preferred. Acquisition performs no cursor movement.
        """
        if not description or not description.strip():
            return None

        needle = description.strip().lower()
        candidates: List[Tuple[int, float, Observation]] = []
        for obs in self._observe():
            if obs.bbox is None:
                continue
            text = _match_text(obs)
            if not text or needle not in text.lower():
                continue
            source = _source_of(obs)
            rank = _SOURCE_RANK.get(source, 99)
            candidates.append((rank, obs.confidence, obs))

        if not candidates:
            return None

        # Prefer UIA source (lowest rank), then highest confidence.
        candidates.sort(key=lambda c: (c[0], -c[1]))
        _, _, best = candidates[0]

        bx, by, bw, bh = best.bbox
        bbox = BoundingBox(x=int(bx), y=int(by), width=int(bw), height=int(bh))
        center = bbox.center

        monitor_index = 0
        try:
            monitor = self._display.monitor_at(*center)
            if monitor is not None:
                monitor_index = monitor.index
            else:
                monitor_index = self._display.primary().index
        except Exception:  # pragma: no cover - defensive
            monitor_index = 0

        return TargetLock(
            target_text=description,
            bbox=bbox,
            center=center,
            monitor_index=monitor_index,
            confidence=best.confidence,
            source=_source_of(best),
            acquired_at=time.time(),
        )

    # --- closed-loop move ------------------------------------------------ #

    def move_to(
        self, target: TargetLock, profile: MotionProfile = MotionProfile.PRECISE
    ) -> MotorResult:
        """Move to ``target`` through the closed loop; see module docstring."""
        assert target is not None, "move_to requires a TargetLock"
        params = PROFILE_PARAMS[profile]
        steps: List[MotorStep] = []
        cursor = self._observe_cursor()
        start_cursor = cursor
        lock = target

        for _ in range(self.max_steps):
            # Loop invariant (stationary target): dist(cursor, center) is
            # non-increasing across iterations.
            remaining = distance(cursor, lock.center)
            if remaining <= self.arrival_tolerance:
                break

            predicted = step_toward(cursor, lock.center, params.step_fraction)
            # NEVER a direct coordinate call — always through the display transform.
            self._backend.move(*self._display.to_physical(*predicted))

            observed = self._observe_cursor()
            residual = distance(observed, predicted)
            corrected = False

            if profile is MotionProfile.SAFE or params.reacquire_each_step:
                fresh = self.acquire_target(lock.target_text, self._observe_world())
                if fresh is not None and distance(fresh.center, lock.center) > self.arrival_tolerance:
                    lock = fresh                      # target moved → correct
                    corrected = True

            steps.append(
                MotorStep(
                    from_xy=cursor,
                    to_xy=predicted,
                    predicted_xy=predicted,
                    observed_xy=observed,
                    corrected=corrected,
                    residual=residual,
                )
            )
            cursor = observed

        # Arrival verification: the target must still be present AND the cursor
        # must have converged to where the target IS NOW — the freshly
        # re-acquired ``final`` lock, not the (possibly stale) in-loop ``lock``.
        # If the target moved on the final observation, arrival is judged against
        # its new position, so a cursor that only reached the old center reports
        # no_convergence rather than a false success (closed-loop correctness).
        final = self.acquire_target(lock.target_text, self._observe_world())

        if final is None:
            success = False
            error: Optional[str] = "target_lost"
        elif distance(cursor, final.center) > self.arrival_tolerance:
            success = False
            error = "no_convergence"
        else:
            success = True
            error = None

        evidence = self._evidence_from(start_cursor, cursor, steps, success)
        return MotorResult("move", success, final, steps, evidence, error)

    # --- terminal actions ------------------------------------------------ #

    def click(
        self, target: TargetLock, profile: MotionProfile = MotionProfile.PRECISE
    ) -> MotorResult:
        """Move to ``target`` then click at its center; observe after-state."""
        move = self.move_to(target, profile)
        if not move.success:
            move.action = "click"
            return move

        lock = move.final_lock or target
        before = self._observe_cursor()
        self._backend.click(*self._display.to_physical(*lock.center))
        after = self._observe_cursor()

        evidence = self._evidence_from(before, after, move.steps, True)
        evidence.state_changed = True
        return MotorResult("click", True, lock, move.steps, evidence, None)

    def type_text(self, text: str, target: TargetLock) -> MotorResult:
        """Move+click the target, then type ``text``; observe after-state."""
        click = self.click(target, MotionProfile.PRECISE)
        if not click.success:
            click.action = "type"
            return click

        lock = click.final_lock or target
        before = self._observe_cursor()
        self._backend.type(text)
        after = self._observe_cursor()

        evidence = self._evidence_from(before, after, click.steps, True)
        evidence.state_changed = True
        evidence.text_appeared = text
        return MotorResult("type", True, lock, click.steps, evidence, None)

    def scroll_to_visible(
        self, target: TargetLock, scroll_budget: int = 20, clicks_per_scroll: int = 3
    ) -> MotorResult:
        """Scroll until ``target`` center enters a monitor work area or budget spent."""
        steps: List[MotorStep] = []
        start_cursor = self._observe_cursor()

        def _visible(center: Tuple[int, int]) -> bool:
            try:
                for monitor in self._display.monitors():
                    if monitor.work_area.contains(*center):
                        return True
            except Exception:  # pragma: no cover - defensive
                return False
            return False

        lock = target
        success = _visible(lock.center)
        budget = scroll_budget
        while not success and budget > 0:
            self._backend.scroll(clicks_per_scroll)
            budget -= 1
            fresh = self.acquire_target(lock.target_text, self._observe_world())
            if fresh is not None:
                lock = fresh
            success = _visible(lock.center)

        after_cursor = self._observe_cursor()
        evidence = self._evidence_from(start_cursor, after_cursor, steps, success)
        evidence.state_changed = success
        error = None if success else "scroll_budget_exhausted"
        return MotorResult("scroll", success, lock, steps, evidence, error)

    # --- evidence -------------------------------------------------------- #

    def _evidence_from(
        self,
        before: Tuple[int, int],
        after: Tuple[int, int],
        steps: List[MotorStep],
        success: bool,
    ) -> ActionEvidence:
        before_hash = f"cursor:{before[0]},{before[1]}"
        after_hash = f"cursor:{after[0]},{after[1]}"
        return ActionEvidence(
            before_hash=before_hash,
            after_hash=after_hash,
            state_changed=success and before != after,
            raw={
                "steps": len(steps),
                "final_cursor": list(after),
                "start_cursor": list(before),
            },
        )
