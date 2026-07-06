"""Ch 23 — Environment Contract: the uniform interface every environment implements."""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.actions.result import ActionResult
from friday.actions.target import Target
from friday.kernel.contracts.environment import EnvironmentContract as _EnvironmentStub
from friday.perception.observation import Observation
from friday.verification.verifier import VerificationResult
from friday.world.objects import WorldObject
from friday.world.worlds import PredictedWorld


@dataclass(frozen=True)
class Action:
    """An abstract interaction request — never app-specific (Ch 24).

    ``capability`` is the abstract verb from Deliberation (e.g. "click", "type",
    "navigate", "scroll", "read"). ``target`` is a semantic Target. There are NO
    site names or URLs baked into an Action; a "navigate" Action carries a URL
    supplied by the goal/plan at runtime, never hardcoded in source.
    """

    capability: str
    target: Optional[Target] = None
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ObjectQuery:
    """A generic query over the objects an environment currently exposes."""

    object_type: Optional[str] = None       # "button", "link", "textbox", ...
    text_contains: Optional[str] = None
    editable_only: bool = False
    limit: int = 60


class EnvironmentContract(_EnvironmentStub):
    """Ch 23 — A digital environment the operator perceives and acts in (Ch 23.22).

    This is the single uniform interface every environment implements.
    Callers describe WHAT they want (abstract capabilities and semantic targets),
    never WHERE or HOW. Extends the kernel stub to maintain backward compatibility.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier, e.g. 'browser.chrome.dedicated'. NEVER a site name."""

    @abstractmethod
    def observe(self) -> List[Observation]:
        """Return the current uniform Observations (Ch 12). Observation precedes action."""

    @abstractmethod
    def interact(self, action: Action) -> ActionResult:
        """Perform one abstract interaction; always returns an ActionResult (Ch 24)."""

    @abstractmethod
    def verify(self, expected: PredictedWorld) -> VerificationResult:
        """Check whether the environment now matches the predicted world (Ch 32)."""

    @abstractmethod
    def query_objects(self, query: ObjectQuery) -> List[WorldObject]:
        """Return objects matching a generic query (Ch 23) — site-agnostic."""

    @abstractmethod
    def query_capabilities(self) -> List[str]:
        """Return the abstract capabilities this environment currently affords."""

    @abstractmethod
    def pause(self) -> None:
        """Pause environment observation/interaction (lifecycle management)."""

    @abstractmethod
    def resume(self) -> None:
        """Resume environment observation/interaction after a pause."""

    @abstractmethod
    def shutdown(self) -> None:
        """Gracefully shut down the environment, releasing resources."""

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Liveness/degradation snapshot, same shape as runtime health()."""
