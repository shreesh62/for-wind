"""Verification layer — confirm action outcomes against perception.

Every action must be verified. Verification compares WorldState
before and after an action to determine if the expected outcome
was achieved.

Core operations:
- verify(): Check if action achieved expected outcome
- collect_evidence(): Build ActionEvidence from state diff
- ActionVerifier: Registered strategies per action type

Verdicts:
- VERIFIED: Action succeeded and evidence confirms it
- UNVERIFIED: Action may have succeeded but no evidence found
- FAILED: Evidence shows action did not achieve goal
- INCONCLUSIVE: Cannot determine (perception unavailable)
"""

from friday.verification.verifier import ActionVerifier, VerificationVerdict, VerificationResult
from friday.verification.evidence import collect_evidence

__all__ = [
    "ActionVerifier",
    "VerificationVerdict",
    "VerificationResult",
    "collect_evidence",
]
