"""Ch 15.4/15.19 — the validated pipeline: promote a learning only after measurable, verified improvement.

``PatternDiscovery`` proves a lesson *recurred* and the :class:`Generalizer` lifts it into a
transferable :class:`Principle`; the :class:`LearningValidator` is the final gate before that
principle may be promoted to procedural memory. It enforces the two conditions of Ch 15.4/15.19:

* **Hard verification gate (Ch 15.19).** Only a ``verified is True`` experience may ever be
  promoted — an unverified experience is always ``REJECTED``, regardless of any measured delta.
* **Measurable improvement.** Even when verified, promotion requires a signed improvement delta
  ``observed - baseline >= min_improvement`` — a learning that does not measurably help is
  ``REJECTED``.

The validator also provides the *unlearning* predicate: a previously-validated principle whose
confidence has decayed at or below the configured ``retire_floor`` should be retired
(:meth:`should_unlearn`), so it is no longer proposed for procedural promotion.

Isolation (Property 1 / Req 5.2): this module holds only pure validation logic over the plain
data models in :mod:`friday.learning.models`. It MUST NOT import ``friday.memory.controller``,
``friday.memory.runtime``, or any ``friday.competence`` module, and MUST NOT reference
``FridayMemory``/``MemoryStore``. No literal application name, site name, or URL appears here
(Axiom 15).
"""

from __future__ import annotations

from friday.learning.models import Principle, ValidationResult, ValidationStatus


class LearningValidator:
    """Ch 15.4/15.19 — promote a learning only after measurable, verified improvement."""

    def __init__(self, *, min_improvement: float = 0.05, retire_floor: float = 0.2) -> None:
        self._min_improvement = min_improvement
        self._retire_floor = retire_floor

    def validate(
        self,
        principle: Principle,
        *,
        baseline: float,
        observed: float,
        verified: bool,
    ) -> ValidationResult:
        """Return ``VALIDATED`` iff ``verified is True`` AND ``observed - baseline >= min_improvement``.

        The result always carries the signed ``improvement`` delta (``observed - baseline``) so the
        outcome is auditable. Returns ``REJECTED`` when the experience is unverified (the hard gate
        of Ch 15.19) or when the improvement falls below ``min_improvement``.
        """

        improvement = observed - baseline

        if verified is not True:
            return ValidationResult(
                status=ValidationStatus.REJECTED,
                principle_id=principle.id,
                improvement=improvement,
                reason="unverified experience (hard gate, Ch 15.19)",
            )

        if improvement < self._min_improvement:
            return ValidationResult(
                status=ValidationStatus.REJECTED,
                principle_id=principle.id,
                improvement=improvement,
                reason=(
                    f"improvement {improvement:.4f} below min_improvement "
                    f"{self._min_improvement:.4f}"
                ),
            )

        return ValidationResult(
            status=ValidationStatus.VALIDATED,
            principle_id=principle.id,
            improvement=improvement,
            reason=(
                f"verified improvement {improvement:.4f} >= min_improvement "
                f"{self._min_improvement:.4f}"
            ),
        )

    def should_unlearn(self, principle: Principle, current_confidence: float) -> bool:
        """``True`` when a previously-validated principle's confidence has decayed to/below the retire floor.

        The retire floor is a fixed policy of this validator (``retire_floor`` from ``__init__``).
        Fires exactly at or below the floor so a principle sitting on the boundary is retired.
        """

        return current_confidence <= self._retire_floor
