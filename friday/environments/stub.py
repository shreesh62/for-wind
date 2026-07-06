"""Ch 23 — StubEnvironment: a deterministic, Playwright-free environment (M6 gate + CI).

This module provides a fully-conformant EnvironmentContract implementation that
requires no external dependencies (no Playwright, no I/O). It is used for:

- M6 Gate tests proving backend independence (Kernel/Deliberation produce the same
  DecisionRecord structure regardless of which environment is registered).
- CI tests without Playwright installed.
- Property-based tests with scripted observation data.

FAS Ch 23 — every digital environment is interchangeable at the contract boundary.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from friday.actions.result import ActionEvidence, ActionResult
from friday.environments.contract import Action, EnvironmentContract, ObjectQuery
from friday.environments.runtime import EnvironmentRuntime
from friday.perception.observation import Observation
from friday.verification.verifier import VerificationResult, VerificationVerdict
from friday.world.objects import WorldObject
from friday.world.worlds import PredictedWorld


_DEFAULT_CAPABILITIES: List[str] = [
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


class StubEnvironment(EnvironmentRuntime, EnvironmentContract):
    """A deterministic, Playwright-free fake environment (FAS Ch 23).

    Returns scripted observations and always-successful ActionResults.
    Used to prove that the Kernel and Deliberation layers are completely
    backend-independent — they never need to know whether they talk to a
    real browser or this stub.

    Parameters
    ----------
    scripted : list of Observation, optional
        The observations that ``observe()`` will return. Defaults to ``[]``.
    capabilities : list of str, optional
        The capability vocabulary returned by ``query_capabilities()``.
        Defaults to the standard browser capability set.
    """

    def __init__(
        self,
        scripted: Optional[List[Observation]] = None,
        capabilities: Optional[List[str]] = None,
    ) -> None:
        super().__init__()
        self._scripted: List[Observation] = scripted if scripted is not None else []
        self._capabilities: List[str] = (
            capabilities if capabilities is not None else list(_DEFAULT_CAPABILITIES)
        )
        self._interactions: List[Action] = []
        self._paused: bool = False
        self._resumed: bool = True
        self._shut_down: bool = False

    # ------------------------------------------------------------------
    # EnvironmentContract — satisfies both RuntimeContract.name and
    # EnvironmentContract.name via MRO.
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Stable identifier for this stub environment."""
        return "stub.testenv"

    def observe(self) -> List[Observation]:
        """Return the scripted observations list (deterministic, no I/O)."""
        return list(self._scripted)

    def interact(self, action: Action) -> ActionResult:
        """Return a successful ActionResult without performing any I/O.

        Records the action internally for test assertions.
        """
        self._interactions.append(action)
        return ActionResult.success(
            action=action.capability,
            target=str(action.target or "stub"),
            evidence=ActionEvidence(
                before_hash="stub_a",
                after_hash="stub_b",
                state_changed=True,
            ),
        )

    def verify(self, expected: PredictedWorld) -> VerificationResult:
        """Return a deterministic VERIFIED result (stub always passes)."""
        return VerificationResult(
            verdict=VerificationVerdict.VERIFIED,
            evidence=ActionEvidence(state_changed=True),
            reason="stub verified",
            confidence=1.0,
        )

    def query_objects(self, query: ObjectQuery) -> List[WorldObject]:
        """Filter scripted observations into WorldObject instances.

        Filters by ``query.object_type`` (if set) and ``query.text_contains``
        (if set), limited by ``query.limit``.
        """
        results: List[WorldObject] = []
        for obs in self._scripted:
            # Filter by object_type
            if query.object_type is not None and obs.object_type != query.object_type:
                continue
            # Filter by text_contains
            if query.text_contains is not None:
                text = obs.attributes.get("text", "") or obs.attributes.get("name", "")
                if query.text_contains not in str(text):
                    continue
            results.append(
                WorldObject(
                    object_type=obs.object_type,
                    id=obs.id,
                    attributes=dict(obs.attributes),
                )
            )
            if len(results) >= query.limit:
                break
        return results

    def query_capabilities(self) -> List[str]:
        """Return the configured capability list (abstract verbs only)."""
        return list(self._capabilities)

    def health(self) -> Dict[str, Any]:
        """Return a healthy status snapshot (stub is always ok)."""
        return {
            "status": "ok",
            "environment": self.name,
            "paused": self._paused,
            "shut_down": self._shut_down,
        }

    def pause(self) -> None:
        """No-op pause (set internal flag)."""
        self._paused = True
        self._resumed = False

    def resume(self) -> None:
        """No-op resume (set internal flag)."""
        self._paused = False
        self._resumed = True

    def shutdown(self) -> None:
        """No-op shutdown (set internal flag)."""
        self._shut_down = True
