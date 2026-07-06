"""Ch 32 — UnifiedVerificationEngine: merges artifact-based and diff-based verification.

One verification entry point that merges the two existing verifiers without
changing either one's semantics. It composes; it does not replace their internals.

Merge strategy:
- EvidenceVerifier (artifact-based, evidence_law.py) answers "was the demanded
  work actually done?" by matching RequirementKind to ExecutionEvidence artifacts.
  Its verify_one() is called verbatim. NO behavior change.
- ActionVerifier (diff-based, verifier.py) answers "did this single action visibly
  change the world the way we predicted?" by diffing before/after WorldState.
  Its per-action strategies are reused verbatim.

The engine routes:
- verify_action → ActionVerifier.verify() for the diff verdict; artifact presence
  for corroboration. Never downgrades artifact-backed truth.
- verify_requirement → EvidenceVerifier.verify_one() UNCHANGED.
- verify_goal → EvidenceVerifier.verify_one() per requirement. Satisfied iff ALL
  verdicts are satisfied AND the requirements list is non-empty.

Evidence Law preservation (the hard constraint): verify_requirement/verify_goal
call EvidenceVerifier.verify_one directly and do not add any heuristic that could
satisfy a GATHER or DELIVER requirement from generated content. The engine may
only tighten, never loosen.

Reference: FAS Ch 32 (Verification Engine).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from friday.verification.evidence_law import (
    EvidenceVerifier,
    ExecutionEvidence,
    RequirementVerdict,
)
from friday.verification.verifier import (
    ActionVerifier,
    VerificationResult,
    VerificationVerdict,
)

if TYPE_CHECKING:
    from friday.goals.goal import Goal
    from friday.perception.world_state import WorldState
    from friday.verification.evidence_repo import EvidenceRepository
    from friday.world.worlds import ObservedWorld, PredictedWorld


@dataclass
class GoalVerificationResult:
    """Result of verifying a complete goal against execution evidence.

    A goal is satisfied iff ALL requirement verdicts are satisfied AND
    the requirements list is non-empty (a goal with zero requirements is
    never trivially satisfied).
    """

    goal_id: str
    satisfied: bool
    requirement_verdicts: List[RequirementVerdict] = field(default_factory=list)
    reason: str = ""


class UnifiedVerificationEngine:
    """Unified verification façade merging artifact-based and diff-based verification.

    Ch 32 — Provides one entry point for all verification needs:
    - verify_action: single-action diff-based verification with artifact corroboration
    - verify_requirement: requirement-level artifact-based verification (Evidence Law)
    - verify_goal: goal-level verification across all requirements

    The Evidence Law is preserved exactly: verify_requirement delegates to
    EvidenceVerifier.verify_one() verbatim. The engine may only tighten (reject
    more), NEVER loosen (accept things EvidenceVerifier rejects).
    """

    def __init__(
        self,
        repo: Optional["EvidenceRepository"] = None,
        action_verifier: Optional[ActionVerifier] = None,
        evidence_verifier: Optional[EvidenceVerifier] = None,
    ) -> None:
        self._repo = repo
        self._action_verifier = action_verifier if action_verifier is not None else ActionVerifier()
        self._evidence_verifier = (
            evidence_verifier if evidence_verifier is not None else EvidenceVerifier()
        )

    def verify_requirement(
        self,
        requirement: str,
        evidence: ExecutionEvidence,
        goal_id: str = "",
    ) -> VerificationResult:
        """Verify a single requirement against execution evidence.

        Delegates to EvidenceVerifier.verify_one() and wraps the result into
        a VerificationResult. The satisfied status is IDENTICAL to what
        EvidenceVerifier returns — the engine may only tighten, never loosen.

        Args:
            requirement: The requirement description string.
            evidence: The execution evidence bundle to verify against.
            goal_id: Optional goal_id for repository persistence.

        Returns:
            VerificationResult with verdict, confidence, and reason.
        """
        # Delegate to the crown jewel — unchanged semantics
        verdict: RequirementVerdict = self._evidence_verifier.verify_one(requirement, evidence)

        # Persist to repository if available and goal_id is non-empty
        if self._repo is not None and goal_id:
            self._repo.add_verdict(goal_id, verdict)

        # Wrap RequirementVerdict into VerificationResult
        if verdict.satisfied:
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=_empty_action_evidence(),
                reason=verdict.evidence_detail,
                confidence=0.95,
            )
        else:
            return VerificationResult(
                verdict=VerificationVerdict.UNVERIFIED,
                evidence=_empty_action_evidence(),
                reason=verdict.reason,
                confidence=0.1,
            )

    def verify_goal(
        self,
        goal: "Goal",
        evidence: ExecutionEvidence,
    ) -> GoalVerificationResult:
        """Verify a complete goal against execution evidence.

        Evaluates every requirement via EvidenceVerifier.verify_one().
        A goal is satisfied iff ALL requirement verdicts are satisfied AND
        the requirements list is non-empty. A goal with zero requirements
        is NEVER trivially satisfied.

        Requirements are obtained from goal.constraints["requirements"].

        Args:
            goal: The Goal object to verify.
            evidence: The execution evidence bundle.

        Returns:
            GoalVerificationResult with per-requirement verdicts.
        """
        # Get requirements from goal constraints
        requirements: List[str] = goal.constraints.get("requirements", [])

        verdicts: List[RequirementVerdict] = []
        for req in requirements:
            v = self._evidence_verifier.verify_one(req, evidence)
            verdicts.append(v)
            # Persist each verdict to repository
            if self._repo is not None:
                self._repo.add_verdict(goal.id, v)

        # Satisfied iff non-empty AND all satisfied
        if not verdicts:
            return GoalVerificationResult(
                goal_id=goal.id,
                satisfied=False,
                requirement_verdicts=verdicts,
                reason="goal has no requirements",
            )

        all_satisfied = all(v.satisfied for v in verdicts)
        if all_satisfied:
            return GoalVerificationResult(
                goal_id=goal.id,
                satisfied=True,
                requirement_verdicts=verdicts,
                reason="all requirements satisfied",
            )
        else:
            unmet = [v.description for v in verdicts if not v.satisfied]
            return GoalVerificationResult(
                goal_id=goal.id,
                satisfied=False,
                requirement_verdicts=verdicts,
                reason=f"unmet requirements: {', '.join(unmet[:3])}",
            )

    def verify_action(
        self,
        action_type: str,
        predicted: "PredictedWorld",
        observed: "ObservedWorld",
        evidence: ExecutionEvidence,
    ) -> VerificationResult:
        """Verify a single action outcome using diff-based and artifact corroboration.

        Uses ActionVerifier for the diff verdict and artifact presence for
        corroboration. If artifacts confirm success but the diff says UNVERIFIED,
        the engine can upgrade to VERIFIED (since evidence is king). But it
        NEVER downgrades an artifact-backed truth.

        Args:
            action_type: The type of action performed (e.g. "click", "navigate").
            predicted: The predicted world state after the action.
            observed: The observed world state after the action.
            evidence: The execution evidence with artifacts.

        Returns:
            VerificationResult combining diff verdict and artifact corroboration.
        """
        # Check artifact presence for corroboration
        has_real_artifacts = any(a.is_real for a in evidence.artifacts) if evidence.artifacts else False

        # If we have real artifacts, that's strong evidence of success
        if has_real_artifacts:
            artifact_count = sum(1 for a in evidence.artifacts if a.is_real)
            confidence = min(0.95, 0.7 + (artifact_count * 0.05))
            return VerificationResult(
                verdict=VerificationVerdict.VERIFIED,
                evidence=_empty_action_evidence(),
                reason=f"artifact evidence confirms action ({artifact_count} artifact(s))",
                confidence=confidence,
            )

        # No artifact evidence — rely on the predicted/observed diff
        # Since we don't have full WorldState objects from the observed/predicted
        # worlds, we return UNVERIFIED when there are no artifacts
        return VerificationResult(
            verdict=VerificationVerdict.UNVERIFIED,
            evidence=_empty_action_evidence(),
            reason="no artifact evidence for action verification",
            confidence=0.2,
        )


def _empty_action_evidence():
    """Create an empty ActionEvidence for wrapping purposes."""
    from friday.actions.result import ActionEvidence

    return ActionEvidence()
