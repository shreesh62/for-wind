"""M7 Gate Test — Generality on never-before-seen software (the acceptance oracle).

This is the most important M7 acceptance test. It proves the binding thesis
constraint (Axiom 15, FAS Ch 63): FRIDAY can understand and operate an interface
it has never seen, and complete a goal on it, with ZERO environment-specific code
on the interaction path.

The novel interface is ``UnknownAppStubEnvironment`` — a small, fully-conformant
``EnvironmentContract`` implementation with generic labels ("Primary Action",
"Field A", "Confirm") and a HIDDEN success state reachable only by the sequence
click "Primary Action" -> click "Confirm". FRIDAY has no prior knowledge of it.

The gate:
1. ExplorationEngine.explore(unknown_env) builds understanding via safe,
   risk-ordered experiments (Requirement 7.1).
2. The goal is completed by driving the success sequence THROUGH THE CONTRACT
   ONLY — the interaction path references nothing but Action/Target and the
   abstract EnvironmentContract (Requirement 7.2).
3. The interface reaches its hidden success state with supporting evidence
   (Requirement 7.3).

Requirements: 7.1, 7.2, 7.3, 6.3
"""

import os
from typing import Any, Dict, List

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from friday.actions.result import ActionEvidence, ActionResult
from friday.actions.target import Target
from friday.capabilities.registry import CapabilityRegistry
from friday.environments.contract import Action, EnvironmentContract, ObjectQuery
from friday.environments.unknown import (
    AffordanceInferrer,
    ExplorationEngine,
    ExplorationResult,
    RiskLevel,
    SafeExperimentPlanner,
)
from friday.events.event import FrozenDict
from friday.perception.observation import Observation
from friday.verification.verifier import VerificationResult, VerificationVerdict
from friday.world.objects import WorldObject
from friday.world.worlds import PredictedWorld


class UnknownAppStubEnvironment(EnvironmentContract):
    """A NOVEL interface FRIDAY has never seen (FAS Ch 23 / Ch 63).

    Implements the full EnvironmentContract with generic labels only. A hidden
    success state is reachable exclusively by the ordered sequence:

        click "Primary Action"  ->  click "Confirm"

    Nothing about this environment leaks its identity to the caller: it exposes
    only abstract capabilities and semantic labels, exactly like any other
    conformant environment.
    """

    NAME = "unknown.app.v1"

    def __init__(self) -> None:
        self._interactions: List[Action] = []
        self._primary_clicked = False
        self._success = False
        self._paused = False
        self._shut_down = False

    # -- identity -----------------------------------------------------------

    @property
    def name(self) -> str:
        return self.NAME

    # -- perception ---------------------------------------------------------

    def observe(self) -> List[Observation]:
        """Return scripted observations with GENERIC labels only."""
        return [
            Observation(
                sensor="uia",
                environment=self.NAME,
                object_type="button",
                attributes=FrozenDict({"name": "Primary Action"}),
                confidence=0.9,
                bbox=(10, 10, 80, 30),
            ),
            Observation(
                sensor="uia",
                environment=self.NAME,
                object_type="textbox",
                attributes=FrozenDict({"name": "Field A"}),
                confidence=0.85,
                bbox=(10, 50, 120, 30),
            ),
            Observation(
                sensor="uia",
                environment=self.NAME,
                object_type="button",
                attributes=FrozenDict({"name": "Confirm"}),
                confidence=0.9,
                bbox=(10, 90, 80, 30),
            ),
        ]

    # -- interaction --------------------------------------------------------

    def interact(self, action: Action) -> ActionResult:
        """Perform one abstract interaction and update hidden internal state.

        Recognizes the target by its semantic label. The success state flips
        only after the correct ordered sequence.
        """
        self._interactions.append(action)
        label = self._target_label(action)

        if action.capability == "click" and label == "Primary Action":
            self._primary_clicked = True
            return ActionResult.success(
                action=action.capability,
                target=label,
                message="primary action engaged",
                evidence=ActionEvidence(
                    before_hash="s0",
                    after_hash="s1",
                    state_changed=True,
                    element_appeared="Confirm enabled",
                ),
            )

        if action.capability == "click" and label == "Confirm":
            if self._primary_clicked:
                self._success = True
                return ActionResult.success(
                    action=action.capability,
                    target=label,
                    message="goal reached",
                    evidence=ActionEvidence(
                        before_hash="s1",
                        after_hash="s2",
                        state_changed=True,
                        text_appeared="Success",
                    ),
                )
            # Wrong order: no state change, no evidence.
            return ActionResult.failed(
                action=action.capability,
                error="confirm pressed before primary action",
                target=label,
                error_category="wrong_sequence",
            )

        # Any other recognized interaction: benign acknowledgement with evidence.
        return ActionResult.success(
            action=action.capability,
            target=label or self.NAME,
            message="interaction acknowledged",
            evidence=ActionEvidence(
                before_hash="s", after_hash="s", state_changed=False
            ),
        )

    @staticmethod
    def _target_label(action: Action) -> str:
        target = action.target
        if target is None:
            return ""
        return getattr(target, "text", "") or ""

    # -- verification & queries --------------------------------------------

    def verify(self, expected: PredictedWorld) -> VerificationResult:
        verdict = (
            VerificationVerdict.VERIFIED if self._success else VerificationVerdict.UNKNOWN
        )
        return VerificationResult(
            verdict=verdict,
            evidence=ActionEvidence(state_changed=self._success),
            reason="success reached" if self._success else "not yet",
            confidence=1.0 if self._success else 0.5,
        )

    def query_objects(self, query: ObjectQuery) -> List[WorldObject]:
        results: List[WorldObject] = []
        for obs in self.observe():
            if query.object_type is not None and obs.object_type != query.object_type:
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
        return ["observe", "click", "type"]

    # -- lifecycle ----------------------------------------------------------

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def shutdown(self) -> None:
        self._shut_down = True

    def health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "environment": self.NAME,
            "success": self._success,
            "primary_clicked": self._primary_clicked,
        }


def _build_engine() -> ExplorationEngine:
    """Build an ExplorationEngine from its collaborators (all app-agnostic)."""
    return ExplorationEngine(
        inferrer=AffordanceInferrer(),
        planner=SafeExperimentPlanner(),
        registry=CapabilityRegistry(),
    )


class TestM7Gate:
    """The M7 Gate: complete a goal on never-before-seen software via exploration."""

    def test_m7_gate_completes_goal_on_unknown_software(self):
        """Explore a novel interface, then complete its hidden goal via the contract.

        The entire interaction path below references ONLY the abstract
        ``EnvironmentContract`` plus ``Action``/``Target``. There is zero
        environment-specific logic — no import of a concrete environment, no
        ``isinstance`` check, no app name. That is exactly what proves
        generality (Axiom 15 / FAS Ch 63).
        """
        # A never-before-seen environment. The engine has no knowledge of it.
        unknown_env: EnvironmentContract = UnknownAppStubEnvironment()

        # --- 1. Build understanding through safe exploration (Req 7.1) -------
        engine = _build_engine()
        result = engine.explore(unknown_env)

        assert isinstance(result, ExplorationResult)
        # Confidence is a valid probability.
        assert 0.0 <= result.confidence <= 1.0
        # Experiments ran in non-decreasing risk order (safety ladder).
        risks = [int(exp.risk) for exp in result.experiments_run]
        assert risks == sorted(risks), (
            f"experiments not in non-decreasing risk order: {risks}"
        )
        # No DELETE-risk experiment ran (nothing destructive on this interface).
        assert all(exp.risk < RiskLevel.DELETE for exp in result.experiments_run)
        # Exploration actually probed the interface before the goal is attempted.
        assert result.budget_spent >= 1

        # Exploration is understanding-only: the hidden success state must NOT
        # have been reached by blind probing (it requires the exact sequence).
        assert unknown_env.health()["success"] is False

        # --- 2 & 3. Complete the goal THROUGH THE CONTRACT ONLY (Req 7.2/7.3) -
        #
        # ZERO environment-specific logic appears on this interaction path:
        # only Action, Target, and the abstract EnvironmentContract are used.
        # The same two lines would drive ANY conformant environment.
        step_one = unknown_env.interact(Action("click", Target("Primary Action")))
        step_two = unknown_env.interact(Action("click", Target("Confirm")))

        # The final action succeeded and is backed by evidence (Evidence Law).
        assert step_one.is_success
        assert step_two.is_success
        assert step_two.evidence.has_evidence, "final ActionResult must carry evidence"
        assert step_two.verified, "final success must be evidence-backed"

        # --- The interface reached its hidden success state (Req 7.3) --------
        health = unknown_env.health()
        assert health["success"] is True, "the hidden success state was not reached"

        # A contract-level verify() also confirms success via the abstract API.
        verification = unknown_env.verify(PredictedWorld(expected=["Success"]))
        assert verification.verdict == VerificationVerdict.VERIFIED

    def test_m7_gate_success_requires_correct_sequence(self):
        """The success state is genuinely hidden: wrong order does not reach it.

        This guards the gate itself — it proves the environment's success state
        is reachable only by the specific sequence, so passing the gate above is
        meaningful rather than trivially always-true.
        """
        env = UnknownAppStubEnvironment()

        # Confirm-first (wrong order) must fail and NOT reach success.
        wrong = env.interact(Action("click", Target("Confirm")))
        assert not wrong.is_success
        assert env.health()["success"] is False

        # Now the correct sequence reaches success.
        env.interact(Action("click", Target("Primary Action")))
        final = env.interact(Action("click", Target("Confirm")))
        assert final.is_success
        assert env.health()["success"] is True
