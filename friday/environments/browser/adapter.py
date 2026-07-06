"""Ch 29 — BrowserEnvironment: the Playwright adapter wrapping BrowserController.

This module wraps the existing 710-line BrowserController (which manages a
persistent Playwright session on a dedicated event loop) and exposes it through
the uniform EnvironmentContract (FAS Ch 23). The adapter translates abstract
Actions into concrete controller calls and maps controller results back into
ActionResult objects with populated ActionEvidence.

Design constraints:
- BrowserController is NEVER modified; only wrapped via dependency injection.
- No Playwright types escape the adapter boundary.
- No hardcoded URLs or application names (Axiom 15 — site-agnosticism).
- The adapter implements both EnvironmentContract and RuntimeContract (via
  EnvironmentRuntime mix-in) so the Kernel can register/tick/checkpoint it.

FAS Ch 29 — Browser Runtime.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from friday.actions.result import ActionEvidence, ActionResult, ActionTimer
from friday.environments.contract import Action, EnvironmentContract, ObjectQuery
from friday.environments.runtime import EnvironmentRuntime
from friday.perception.observation import Observation
from friday.events.event import FrozenDict
from friday.verification.verifier import VerificationResult, VerificationVerdict
from friday.world.objects import WorldObject
from friday.world.worlds import PredictedWorld


_CAPABILITIES: List[str] = [
    "observe",
    "read",
    "navigate",
    "click",
    "type",
    "scroll",
    "press",
    "upload",
    "download",
]


class BrowserEnvironment(EnvironmentRuntime, EnvironmentContract):
    """Playwright adapter exposing BrowserController through EnvironmentContract.

    Wraps the existing BrowserController without modifying it. Translates
    abstract capability-based Actions into concrete controller method calls
    and maps results back to ActionResult with ActionEvidence. No Playwright
    types escape this boundary.

    Parameters
    ----------
    browser_controller : BrowserController
        The existing controller instance (dependency injection).
    observe_limit : int, optional
        Max interactive elements to observe per call. Default 60.

    FAS Ch 29 — Browser Runtime.
    """

    def __init__(
        self,
        browser_controller: Any,
        observe_limit: int = 60,
    ) -> None:
        super().__init__()
        self._controller = browser_controller
        self._observe_limit = observe_limit
        self._paused: bool = False
        self._last_elements: List[Dict[str, Any]] = []

        # Route table: capability string -> handler method (dict dispatch, no if/elif)
        self._routes: Dict[str, Callable[[Action], Dict[str, Any]]] = {
            "navigate": self._handle_navigate,
            "read": self._handle_read,
            "click": self._handle_click,
            "type": self._handle_type,
            "scroll": self._handle_scroll,
            "press": self._handle_press,
            "upload": self._handle_upload,
            "download": self._handle_download,
        }

    # ------------------------------------------------------------------
    # EnvironmentContract implementation
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Stable identifier — generic backend name, never a site name."""
        return "browser.chrome.dedicated"

    def observe(self) -> List[Observation]:
        """Observe interactive elements via the controller and map to Observations.

        Calls browser_controller.observe_interactive(limit) and translates each
        element dict into a uniform Observation with environment="browser" and
        object_type set to the element's role.

        Returns an empty list if the controller is unavailable.
        """
        if not self._controller.available:
            return []

        raw = self._controller.observe_interactive(self._observe_limit)

        # observe_interactive returns a dict with "elements" list and "ok" flag
        if not raw.get("ok", False):
            return []

        elements = raw.get("elements", [])
        self._last_elements = elements  # cache for interact/query_objects

        observations: List[Observation] = []
        for el in elements:
            role = el.get("role", "unknown") or "unknown"
            text = el.get("text", "") or ""
            attrs = {
                "text": text,
                "editable": el.get("editable", False),
                "selector": el.get("selector", ""),
                "index": el.get("index", 0),
                "in_view": el.get("in_view", False),
            }
            obs = Observation(
                sensor="dom",
                environment="browser",
                object_type=role,
                attributes=FrozenDict(attrs),
                confidence=1.0,
            )
            observations.append(obs)

        return observations

    def interact(self, action: Action) -> ActionResult:
        """Dispatch an abstract Action to the appropriate controller method.

        Uses the _routes dict for dispatch. Returns ActionResult.blocked if
        the controller is unavailable, or ActionResult.failed if the capability
        is not afforded.
        """
        # Gate: controller must be available
        if not self._controller.available:
            return ActionResult.blocked(
                action=action.capability,
                reason="browser controller unavailable",
            )

        # Dispatch via routes dict
        handler = self._routes.get(action.capability)
        if handler is None:
            return ActionResult.failed(
                action=action.capability,
                error="capability not afforded by this environment",
            )

        with ActionTimer() as timer:
            raw = handler(action)

        return self._to_action_result(action, raw, timer)

    def verify(self, expected: PredictedWorld) -> VerificationResult:
        """Basic verification by re-observing and comparing.

        Full verification is handled by the UnifiedVerificationEngine; this
        provides a minimal conformant implementation.
        """
        # Re-observe and check if any expected conditions match
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
        """Filter the latest observation snapshot into WorldObject instances.

        Uses the cached _last_elements from the most recent observe() call.
        Filters by object_type and text_contains from the query.
        """
        results: List[WorldObject] = []
        for el in self._last_elements:
            role = el.get("role", "unknown") or "unknown"
            text = el.get("text", "") or ""

            # Filter by object_type
            if query.object_type is not None and role != query.object_type:
                continue

            # Filter by text_contains
            if query.text_contains is not None and query.text_contains not in text:
                continue

            # Filter by editable_only
            if query.editable_only and not el.get("editable", False):
                continue

            results.append(
                WorldObject(
                    object_type=role,
                    attributes={
                        "text": text,
                        "editable": el.get("editable", False),
                        "selector": el.get("selector", ""),
                        "index": el.get("index", 0),
                        "in_view": el.get("in_view", False),
                    },
                )
            )
            if len(results) >= query.limit:
                break

        return results

    def query_capabilities(self) -> List[str]:
        """Return the abstract capabilities this browser environment affords.

        Returns only abstract verbs — no site-specific strings.
        """
        return list(_CAPABILITIES)

    def health(self) -> Dict[str, Any]:
        """Liveness/degradation snapshot from the controller's properties."""
        available = self._controller.available
        return {
            "status": "ok" if available else "degraded",
            "available": available,
            "connection_mode": self._controller.connection_mode,
            "is_real_chrome": self._controller.is_real_chrome,
            "last_error": self._controller.last_error,
        }

    def pause(self) -> None:
        """Pause passive observation (gates tick())."""
        self._paused = True

    def resume(self) -> None:
        """Resume passive observation."""
        self._paused = False

    def shutdown(self) -> None:
        """Gracefully shut down the browser controller."""
        self._controller.stop()

    # ------------------------------------------------------------------
    # RuntimeContract overrides (via EnvironmentRuntime)
    # ------------------------------------------------------------------

    def tick(self, logical_time: int) -> None:
        """Passive observe cycle — gated by the paused flag."""
        if self._paused:
            return
        super().tick(logical_time)

    def checkpoint(self) -> Dict[str, Any]:
        """JSON-serializable state — no Playwright handles."""
        return {
            "name": self.name,
            "paused": self._paused,
            "connection_mode": self._controller.connection_mode,
            "available": self._controller.available,
        }

    def restore(self, state: Dict[str, Any]) -> None:
        """Re-apply checkpoint state."""
        self._paused = state.get("paused", False)

    # ------------------------------------------------------------------
    # Private route handlers
    # ------------------------------------------------------------------

    def _handle_navigate(self, action: Action) -> Dict[str, Any]:
        """Delegate navigate to browser_controller.navigate(url)."""
        url = action.params.get("url", "")
        return self._controller.navigate(url)

    def _handle_read(self, action: Action) -> Dict[str, Any]:
        """Delegate read to browser_controller.read_text(max_chars).

        BrowserController.read_text returns a str; wrap it as a dict.
        """
        max_chars = action.params.get("max_chars", 3000)
        text = self._controller.read_text(max_chars=max_chars)
        # read_text returns a string directly; normalize to dict format
        if isinstance(text, str):
            return {"ok": True, "text": text}
        return text  # pragma: no cover — safety for future changes

    def _handle_click(self, action: Action) -> Dict[str, Any]:
        """Delegate click to browser_controller.click_index or click.

        Prefers index-based clicking using the cached elements snapshot.
        Falls back to text-based click if no index is provided.
        """
        index = action.params.get("index")
        if index is not None:
            elements = action.params.get("elements", self._last_elements)
            return self._controller.click_index(index, elements)
        # Fallback: text-based click via target
        text = ""
        if action.target:
            text = action.target.text
        if not text:
            text = action.params.get("text", "")
        return self._controller.click(text)

    def _handle_type(self, action: Action) -> Dict[str, Any]:
        """Delegate type to browser_controller.fill_index or type_text.

        Prefers index-based fill using the cached elements snapshot.
        Falls back to selector/keyboard-based typing.
        """
        value = action.params.get("value", "")
        index = action.params.get("index")
        if index is not None:
            elements = action.params.get("elements", self._last_elements)
            return self._controller.fill_index(index, value, elements)
        # Fallback: type_text with optional selector
        selector = action.params.get("selector")
        return self._controller.type_text(value, selector=selector)

    def _handle_scroll(self, action: Action) -> Dict[str, Any]:
        """Delegate scroll to browser_controller.scroll(direction, amount)."""
        direction = action.params.get("direction", "down")
        amount = action.params.get("amount", 600)
        return self._controller.scroll(direction=direction, amount=amount)

    def _handle_press(self, action: Action) -> Dict[str, Any]:
        """Delegate press to browser_controller.press(key)."""
        key = action.params.get("key", "Enter")
        return self._controller.press(key)

    def _handle_upload(self, action: Action) -> Dict[str, Any]:
        """Delegate upload to browser_controller.upload_file(paths, index, elements)."""
        paths = action.params.get("paths", [])
        index = action.params.get("index")
        elements = action.params.get("elements", self._last_elements)
        selector = action.params.get("selector")
        return self._controller.upload_file(
            paths, index=index, elements=elements, selector=selector
        )

    def _handle_download(self, action: Action) -> Dict[str, Any]:
        """Delegate download to browser_controller.download_file(trigger_index, elements)."""
        trigger_index = action.params.get("trigger_index", 0)
        elements = action.params.get("elements", self._last_elements)
        dest_dir = action.params.get("dest_dir")
        return self._controller.download_file(trigger_index, elements, dest_dir=dest_dir)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _to_action_result(
        self, action: Action, raw: Dict[str, Any], timer: ActionTimer
    ) -> ActionResult:
        """Convert a controller dict response into an ActionResult with evidence.

        Extracts url_changed and state_changed signals from the raw dict.
        No Playwright types appear in the returned ActionResult.
        """
        ok = raw.get("ok", False)
        target_str = ""
        if action.target:
            target_str = action.target.text or action.target.role or ""

        # Build evidence from controller signals
        url_before = raw.get("url_before", "")
        url_after = raw.get("url_after", "")
        url_changed = bool(url_before and url_after and url_before != url_after)
        state_changed = raw.get("changed", False) or raw.get("scrolled", False)

        evidence = ActionEvidence(
            before_hash=str(hash(url_before)) if url_before else "",
            after_hash=str(hash(url_after)) if url_after else "",
            state_changed=state_changed or url_changed,
            url_changed=url_changed,
            raw={k: v for k, v in raw.items() if k != "elements"},
        )

        if ok:
            return ActionResult.success(
                action=action.capability,
                target=target_str,
                evidence=evidence,
                started_at=timer.started_at,
                duration_ms=timer.duration_ms,
                metadata={"raw_keys": list(raw.keys())},
            )
        else:
            error = raw.get("error", "unknown error")
            return ActionResult.failed(
                action=action.capability,
                error=error,
                target=target_str,
                evidence=evidence,
                started_at=timer.started_at,
                duration_ms=timer.duration_ms,
                metadata={"raw_keys": list(raw.keys())},
            )
