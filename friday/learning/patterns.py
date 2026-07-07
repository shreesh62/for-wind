"""Ch 15.5 — pattern discovery: patterns emerge from repetition, never a single success.

``PatternDiscovery`` accumulates :class:`VerifiedExperience` records and only emits a
:class:`DiscoveredPattern` once the *same* stable signature
``(capability, environment, outcome_signature)`` has recurred at least
``min_repetitions`` times. A single verified success proves nothing (Ch 15.5); only
repeated verified evidence is a pattern.

Isolation (Property 1 / Req 5.2): this module holds only pure discovery logic over the
plain data models in :mod:`friday.learning.models`. It MUST NOT import
``friday.memory.controller``, ``friday.memory.runtime``, or any ``friday.competence``
module, and MUST NOT reference ``FridayMemory``/``MemoryStore``. No literal application
name, site name, or URL appears here (Axiom 15).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from friday.learning.models import DiscoveredPattern, VerifiedExperience


def _signature(experience: VerifiedExperience) -> str:
    """Stable string key grouping repeated verified experience.

    Derived deterministically from ``(capability, environment, outcome_signature)`` so the
    same recurring outcome always buckets together. Uses a NUL delimiter so component
    values cannot collide across bucket boundaries.
    """

    return "\x00".join(
        (experience.capability, experience.environment, experience.outcome_signature)
    )


class PatternDiscovery:
    """Ch 15.5 — patterns emerge from repetition, never a single success."""

    def __init__(self, *, min_repetitions: int = 3) -> None:
        self._min_repetitions = min_repetitions
        # signature -> list of verified experiences backing it (repetition evidence).
        self._buckets: Dict[str, List[VerifiedExperience]] = {}

    def observe(self, experience: VerifiedExperience) -> Optional[DiscoveredPattern]:
        """Accumulate a verified experience; return a pattern once repetition threshold met.

        Only records whose ``verified`` field is ``True`` are counted toward support
        (the hard gate of Ch 15.19). Returns ``None`` until the same
        ``(capability, environment, outcome_signature)`` has recurred at least
        ``min_repetitions`` times; the returned pattern's ``support`` equals the observed
        verified repetition count.
        """

        if experience.verified is not True:
            return None

        signature = _signature(experience)
        bucket = self._buckets.setdefault(signature, [])
        bucket.append(experience)

        support = len(bucket)
        if support < self._min_repetitions:
            return None

        mean_prediction_error = sum(e.prediction_error for e in bucket) / support
        return DiscoveredPattern(
            signature=signature,
            capability=experience.capability,
            environment=experience.environment,
            support=support,
            mean_prediction_error=mean_prediction_error,
        )

    def support(self, signature: str) -> int:
        """How many verified repetitions currently back this pattern signature."""

        return len(self._buckets.get(signature, ()))
