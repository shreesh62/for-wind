"""Ch 52 — EnvironmentRuntime: mix-in bridging RuntimeContract and EnvironmentContract.

Every environment registered with the CognitiveKernel must satisfy
RuntimeContract (tick, checkpoint, receive, etc.). This mix-in implements
those runtime lifecycle methods by delegating to the EnvironmentContract
methods that concrete environment classes provide (observe, interact,
shutdown, health).

The Kernel never imports Playwright or environment-specific code; it only
speaks the RuntimeContract interface. This mix-in is the translation layer.

FAS Ch 52 — Runtimes never call each other directly; all communication
flows through kernel-published events.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from friday.events.event import Event, make_event
from friday.kernel.contracts.runtime import RuntimeContract

logger = logging.getLogger(__name__)


class EnvironmentRuntime(RuntimeContract):
    """Mix-in that implements RuntimeContract by delegating to EnvironmentContract.

    Concrete environment classes (BrowserEnvironment, StubEnvironment, etc.)
    inherit from both EnvironmentRuntime and EnvironmentContract. This mix-in
    provides the kernel-facing lifecycle methods; the concrete class provides
    the environment-facing perception/interaction methods.

    FAS Ch 52 — runtime lifecycle bridge.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._kernel: Any = None
        self._paused: bool = False

    # -------------------------------------------------------------- RuntimeContract

    @property
    def name(self) -> str:
        """Delegate to the concrete EnvironmentContract.name property."""
        # Concrete classes MUST provide the name property via EnvironmentContract.
        # This satisfies RuntimeContract.name by deferring to the MRO.
        raise NotImplementedError(
            "Concrete environment must implement the 'name' property."
        )

    def initialize(self, kernel: Any) -> None:
        """Store a reference to the kernel for event publishing.

        Called by CognitiveKernel.register_runtime().
        """
        self._kernel = kernel

    def tick(self, logical_time: int) -> None:
        """Passive observe cycle — called by the Kernel scheduler each tick.

        Calls self.observe() (the EnvironmentContract method returning
        List[Observation]) and publishes each observation as an
        'observation.received' kernel event.
        """
        if self._paused:
            return

        try:
            observations = self.observe()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            logger.exception("Environment observe failed during tick on %s", self.name)
            return

        for obs in observations:
            obs_payload: Dict[str, Any] = {
                "sensor": getattr(obs, "sensor", ""),
                "environment": getattr(obs, "environment", ""),
                "object_type": getattr(obs, "object_type", ""),
                "attributes": dict(getattr(obs, "attributes", {})),
                "confidence": getattr(obs, "confidence", 1.0),
            }
            event = make_event(
                event_type="observation.received",
                source=self.name,
                logical_time=logical_time,
                payload=obs_payload,
            )
            self.publish(event)

    def observe(self) -> List[Dict[str, Any]]:  # type: ignore[override]
        """RuntimeContract.observe() — returns observations as List[Dict].

        Bridges EnvironmentContract.observe() (List[Observation]) into the
        dict-based format the Kernel expects. In practice, the concrete
        class's observe() returns List[Observation] and tick() uses that
        directly. This fallback returns [] for safety.
        """
        return []

    def receive(self, event: Event) -> None:
        """Handle incoming kernel events.

        Routes 'capability.requested' events to self.interact() so the
        environment can fulfil capability requests from other runtimes.
        """
        if event.event_type == "capability.requested":
            capability = event.payload.get("capability", "")
            params = dict(event.payload.get("params", {}))
            try:
                # Import Action locally to avoid circular imports at module level
                from friday.environments.contract import Action

                action = Action(capability=capability, params=params)
                self.interact(action)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to handle capability.requested on %s: %s",
                    self.name,
                    capability,
                )

    def publish(self, event: Event) -> None:
        """Publish an event through the kernel's event bus.

        Routes the event via self._kernel.publish_event() so it flows
        through the kernel's persistence and broadcast machinery.
        """
        if self._kernel is not None:
            self._kernel.publish_event(event)

    def checkpoint(self) -> Dict[str, Any]:
        """Return JSON-serializable state snapshot.

        MUST contain only primitives (no Playwright handles, no live objects).
        Returns basic runtime state: paused flag and environment name.
        """
        return {
            "name": self.name,
            "paused": self._paused,
        }

    def restore(self, state: Dict[str, Any]) -> None:
        """Re-apply checkpoint state.

        Restores paused flag from the serialized state dict.
        """
        self._paused = state.get("paused", False)

    def shutdown(self) -> None:
        """Delegate to the EnvironmentContract's shutdown() method."""
        # Concrete classes override this with their own shutdown logic.
        pass

    def health(self) -> Dict[str, Any]:
        """Delegate to the EnvironmentContract's health() method."""
        # Concrete classes override this with their own health logic.
        return {"status": "ok"}
