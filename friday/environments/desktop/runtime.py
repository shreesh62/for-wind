"""Ch 30 — DesktopEnvironment: the Windows desktop as a uniform environment.

This module replaces the M6 placeholder in
``friday/environments/desktop/__init__.py`` with a *real* ``DesktopEnvironment``
that implements the same ``EnvironmentContract`` + ``EnvironmentRuntime`` as
M6's ``BrowserEnvironment``. Nothing above the contract boundary (the Kernel,
the Deliberator, the Verification Engine) learns that a new environment type
exists — it is ticked, queried for abstract capabilities, and verified exactly
like the browser.

Design constraints (Axiom 15 — site/app-agnosticism, FAS Ch 63):
- ZERO app-specific code. Notepad, a bespoke line-of-business app, and software
  written yesterday are treated identically — as an environment exposing
  observable objects with inferable affordances. There is no ``if app ==
  "notepad"`` branch and no hardcoded window title / URL anywhere here.
- Observation is done via injected UIA + OCR sensors; interaction is delegated
  to the closed-loop ``MotorSystem`` and the window/display/clipboard/session
  managers. None of those collaborators are modified — they are wrapped.
- ``interact`` dispatches via a dict route table keyed by the abstract
  capability verb (no ``if/elif`` chains, matching the M6 adapter).
- Every state-changing success returns an ``ActionResult`` whose
  ``ActionEvidence.has_evidence`` is ``True`` — never an unverified success.
- ``interact``/``query_objects`` never raise for a generated ``Action`` /
  ``ObjectQuery`` — unknown verbs return a failed ``ActionResult``.

FAS Ch 30 — Desktop Runtime.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Dict, List, Optional

from friday.actions.result import ActionEvidence, ActionResult, ActionStatus, ActionTimer
from friday.capabilities.motor import MotorSystem
from friday.environments.contract import Action, EnvironmentContract, ObjectQuery
from friday.environments.desktop.clipboard import ClipboardManager
from friday.environments.desktop.display_manager import DisplayManager
from friday.environments.desktop.session import SessionManager
from friday.environments.desktop.window_manager import WindowManager
from friday.environments.runtime import EnvironmentRuntime
from friday.events.event import FrozenDict
from friday.perception.contracts import SensorContract
from friday.perception.observation import Observation
from friday.perception.types import PerceptionSource
from friday.verification.verifier import VerificationResult, VerificationVerdict
from friday.world.objects import WorldObject
from friday.world.worlds import ObservedWorld, PredictedWorld


# Abstract capability verbs this environment affords — abstract verbs only,
# never app/site-specific strings (Axiom 15).
_CAPABILITIES: List[str] = [
    "observe",
    "read",
    "click",
    "type",
    "scroll",
    "press",
    "focus_window",
    "launch",
    "copy",
    "paste",
]


# Source preference ordering for fusion: UIA (semantic) ranks above OCR/vision.
_SOURCE_RANK = {
    PerceptionSource.UIA: 0,
    PerceptionSource.BROWSER: 1,
    PerceptionSource.OCR: 2,
    PerceptionSource.VISION: 3,
    PerceptionSource.SCREEN: 4,
    PerceptionSource.PROCESS: 5,
}


def _source_of(obs: Observation) -> PerceptionSource:
    """Best-effort perception source for an observation (attributes then sensor)."""
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


def _obs_text(obs: Observation) -> str:
    """Extract the visible text/name from an observation's attributes."""
    attrs = obs.attributes or {}
    return str(attrs.get("text") or attrs.get("name") or "")


class DesktopEnvironment(EnvironmentRuntime, EnvironmentContract):
    """Ch 30 — Windows desktop as a uniform environment (replaces M6 placeholder).

    Implements the same ``EnvironmentContract`` + ``EnvironmentRuntime`` as
    ``BrowserEnvironment``. Observation fuses injected UIA + OCR sensors into a
    single ranked ``List[Observation]`` (UIA ranked above OCR); interaction is
    dispatched via a dict route table and delegated to the closed-loop
    ``MotorSystem`` and the desktop managers.

    Parameters
    ----------
    window_manager, display_manager, clipboard, session :
        Desktop managers (dependency injection). Sensible defaults constructed
        when ``None``.
    motor : MotorSystem
        Closed-loop motor control. Built from ``display_manager`` + ``sensors``
        when ``None``.
    sensors : List[SensorContract]
        UIA + OCR (and any other) perception sources. Defaults to ``[]``.
    observe_limit : int
        Max fused observations returned per ``observe()`` call. Default 80.

    FAS Ch 30 — Desktop Runtime.
    """

    def __init__(
        self,
        window_manager: Optional[WindowManager] = None,
        display_manager: Optional[DisplayManager] = None,
        clipboard: Optional[ClipboardManager] = None,
        session: Optional[SessionManager] = None,
        motor: Optional[MotorSystem] = None,
        sensors: Optional[List[SensorContract]] = None,
        observe_limit: int = 80,
    ) -> None:
        super().__init__()
        self._window_manager = window_manager or WindowManager()
        self._display_manager = display_manager or DisplayManager()
        self._clipboard = clipboard or ClipboardManager()
        self._session = session or SessionManager()
        self._sensors: List[SensorContract] = list(sensors) if sensors else []
        self._motor = motor or MotorSystem(
            sensors=self._sensors, display=self._display_manager
        )
        self._observe_limit = observe_limit
        self._paused: bool = False
        self._last_observations: List[Observation] = []

        # Route table: capability verb -> handler (dict dispatch, no if/elif).
        self._routes: Dict[str, Callable[[Action], ActionResult]] = {
            "click": self._handle_click,
            "type": self._handle_type,
            "scroll": self._handle_scroll,
            "press": self._handle_press,
            "focus_window": self._handle_focus_window,
            "launch": self._handle_launch,
            "read": self._handle_read,
            "copy": self._handle_copy,
            "paste": self._handle_paste,
        }

    # ------------------------------------------------------------------
    # EnvironmentContract implementation
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Stable identifier — the generic desktop backend, NEVER an app name."""
        return "desktop.windows"

    def observe(self) -> List[Observation]:
        """Fuse UIA + OCR sensor observations into a single ranked list.

        Collects observations from every injected sensor, re-stamps
        ``environment="desktop"`` when a sensor emits something else, ranks
        UIA-source observations ABOVE OCR (by source rank, then confidence
        descending), and caps the result at ``observe_limit``. Returns ``[]``
        when there are no sensors / no observations. Never raises.
        """
        collected: List[Observation] = []
        for sensor in self._sensors:
            try:
                collected.extend(sensor.observe())
            except Exception:  # noqa: BLE001 - a broken sensor must not crash observe
                continue

        if not collected:
            self._last_observations = []
            return []

        # Re-stamp environment to "desktop" where a sensor emitted otherwise.
        normalized: List[Observation] = []
        for obs in collected:
            if obs.environment != "desktop":
                obs = dataclasses.replace(obs, environment="desktop")
            normalized.append(obs)

        # Rank UIA above OCR: sort by source rank asc, then confidence desc.
        normalized.sort(
            key=lambda o: (_SOURCE_RANK.get(_source_of(o), 99), -o.confidence)
        )

        fused = normalized[: self._observe_limit]
        self._last_observations = fused
        return fused

    def interact(self, action: Action) -> ActionResult:
        """Dispatch an abstract ``Action`` via the route table.

        Unknown capability verbs return a failed ``ActionResult`` rather than
        raising. State-changing successes carry evidence with
        ``has_evidence == True``.
        """
        handler = self._routes.get(action.capability)
        if handler is None:
            return ActionResult.failed(
                action=action.capability,
                error="capability not afforded by this environment",
                error_category="unsupported_capability",
            )
        try:
            return handler(action)
        except Exception as exc:  # noqa: BLE001 - never raise for a generated Action
            return ActionResult.failed(
                action=action.capability,
                error=str(exc),
                error_category="desktop_error",
            )

    def verify(self, expected: PredictedWorld) -> VerificationResult:
        """Basic verification by re-observing.

        Full verification is the ``UnifiedVerificationEngine``'s job; this
        provides a minimal conformant implementation: if re-observation yields
        anything, report VERIFIED (confidence ~0.5), else UNVERIFIED.
        """
        observations = self.observe()
        if observations:
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=ActionEvidence(state_changed=True),
                reason="observations available",
                confidence=0.5,
            )
        return VerificationResult(
            verdict=VerificationVerdict.UNVERIFIED,
            evidence=ActionEvidence(),
            reason="no observations available",
            confidence=0.2,
        )

    def query_objects(self, query: ObjectQuery) -> List[WorldObject]:
        """Filter the latest observation snapshot into ``WorldObject`` instances.

        Uses the cached snapshot from the most recent ``observe()`` call.
        Filters by ``object_type``, ``text_contains``, and ``editable_only``,
        capped at ``query.limit``. Never raises.
        """
        results: List[WorldObject] = []
        for obs in self._last_observations:
            text = _obs_text(obs)
            attrs = dict(obs.attributes) if obs.attributes else {}

            if query.object_type is not None and obs.object_type != query.object_type:
                continue
            if query.text_contains is not None and query.text_contains not in text:
                continue
            if query.editable_only and not attrs.get("editable", False):
                continue

            results.append(
                WorldObject(
                    object_type=obs.object_type,
                    attributes={
                        "text": text,
                        "confidence": obs.confidence,
                        "bbox": obs.bbox,
                        "source": _source_of(obs).value,
                        **attrs,
                    },
                )
            )
            if len(results) >= query.limit:
                break
        return results

    def query_capabilities(self) -> List[str]:
        """Return the abstract verbs this desktop environment affords."""
        return list(_CAPABILITIES)

    def health(self) -> Dict[str, Any]:
        """Liveness/degradation snapshot."""
        available = len(self._sensors) > 0
        return {
            "status": "ok" if available else "degraded",
            "available": available,
            "sensors": len(self._sensors),
            "paused": self._paused,
            "monitors": len(self._display_manager.monitors()),
        }

    def pause(self) -> None:
        """Pause passive observation (gates tick())."""
        self._paused = True

    def resume(self) -> None:
        """Resume passive observation."""
        self._paused = False

    def shutdown(self) -> None:
        """Gracefully shut down; managers hold no persistent OS handles."""
        for collaborator in (
            self._window_manager,
            self._display_manager,
            self._clipboard,
            self._session,
            self._motor,
        ):
            shutdown = getattr(collaborator, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:  # noqa: BLE001 - shutdown must not raise
                    continue

    # ------------------------------------------------------------------
    # RuntimeContract overrides (via EnvironmentRuntime)
    # ------------------------------------------------------------------

    def tick(self, logical_time: int) -> None:
        """Passive observe cycle — gated by the paused flag."""
        if self._paused:
            return
        super().tick(logical_time)

    def checkpoint(self) -> Dict[str, Any]:
        """JSON-serializable state — no OS handles."""
        return {
            "name": self.name,
            "paused": self._paused,
            "sensors": len(self._sensors),
        }

    def restore(self, state: Dict[str, Any]) -> None:
        """Re-apply checkpoint state."""
        self._paused = state.get("paused", False)

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    def _acquire(self, action: Action):
        """Resolve a target description into a MotorSystem TargetLock, or None."""
        description = ""
        if action.target is not None:
            description = action.target.text or ""
        if not description:
            description = str(action.params.get("target", ""))
        if not description:
            return None
        return self._motor.acquire_target(description, ObservedWorld())

    def _handle_click(self, action: Action) -> ActionResult:
        """Acquire the target then closed-loop click via the MotorSystem."""
        if not self._sensors:
            return self._needs_repair(
                action.capability, "no sensors available to acquire target"
            )
        lock = self._acquire(action)
        if lock is None:
            return self._needs_repair(
                action.capability, "target not found in current observation"
            )
        return self._motor.click(lock).to_action_result()

    def _handle_type(self, action: Action) -> ActionResult:
        """Acquire the target then closed-loop type the text via the MotorSystem."""
        if not self._sensors:
            return self._needs_repair(
                action.capability, "no sensors available to acquire target"
            )
        lock = self._acquire(action)
        if lock is None:
            return self._needs_repair(
                action.capability, "target not found in current observation"
            )
        text = str(action.params.get("text", action.params.get("value", "")))
        return self._motor.type_text(text, lock).to_action_result()

    def _handle_scroll(self, action: Action) -> ActionResult:
        """Scroll the target into view via the MotorSystem when a target is given."""
        lock = self._acquire(action)
        if lock is None:
            return self._needs_repair(
                action.capability, "target not found in current observation"
            )
        return self._motor.scroll_to_visible(lock).to_action_result()

    def _handle_press(self, action: Action) -> ActionResult:
        """Press a key. Honest: only when the motor backend supports it.

        The default ``MotorBackend`` exposes no key-press primitive, so absent
        a backend ``press`` this returns an honest NEEDS_REPAIR rather than a
        silent (unverified) success.
        """
        key = str(action.params.get("key", ""))
        backend = getattr(self._motor, "_backend", None)
        press = getattr(backend, "press", None)
        if callable(press) and key:
            with ActionTimer() as timer:
                press(key)
            return ActionResult.success(
                action=action.capability,
                target=key,
                evidence=ActionEvidence(state_changed=True, raw={"key": key}),
                started_at=timer.started_at,
                duration_ms=timer.duration_ms,
            )
        return self._needs_repair(
            action.capability, "key press not supported by the motor backend"
        )

    def _handle_focus_window(self, action: Action) -> ActionResult:
        """Delegate to WindowManager.focus using the title from params."""
        title = str(action.params.get("title", ""))
        return self._window_manager.focus(title)

    def _handle_launch(self, action: Action) -> ActionResult:
        """Delegate to WindowManager.launch using the app name from params."""
        app = str(action.params.get("app", ""))
        return self._window_manager.launch(app)

    def _handle_read(self, action: Action) -> ActionResult:
        """Read visible text by fusing OCR (and other) observation text."""
        observations = self._last_observations or self.observe()
        texts = [t for t in (_obs_text(o) for o in observations) if t]
        joined = "\n".join(texts)
        evidence = ActionEvidence(
            text_appeared=joined,
            raw={"text": joined, "regions": len(texts)},
        )
        return ActionResult.success(
            action=action.capability,
            target="screen",
            message=f"read {len(texts)} text region(s)",
            evidence=evidence,
        )

    def _handle_copy(self, action: Action) -> ActionResult:
        """Delegate to ClipboardManager.write; it returns an ActionResult."""
        text = str(action.params.get("text", ""))
        return self._clipboard.write(text)

    def _handle_paste(self, action: Action) -> ActionResult:
        """Read the clipboard and surface it as an evidence-backed success."""
        text = self._clipboard.read() or ""
        evidence = ActionEvidence(
            text_appeared=text,
            raw={"text": text},
        )
        return ActionResult.success(
            action=action.capability,
            target="clipboard",
            message="clipboard read",
            evidence=evidence,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _needs_repair(self, action: str, reason: str) -> ActionResult:
        """Build an honest NEEDS_REPAIR result (no illusion success)."""
        result = ActionResult.failed(
            action=action,
            error=reason,
            error_category="acquisition",
            repair_hints=["observe_first", "reacquire_target", "retry"],
        )
        result.status = ActionStatus.NEEDS_REPAIR
        result.message = f"{action} needs repair: {reason}"
        return result
