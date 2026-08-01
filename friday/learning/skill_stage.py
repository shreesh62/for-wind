"""M17 — the ``SkillStage`` taxonomy (FAS §A2.5.1).

FAS §A2.5.1 defines the eight-stage skill-evolution ladder
(``Observation → Experiment → Reflection → Verification → Compilation →
Optimization → Generalization → Capability Registry``). This tiny module holds ONLY
that enum so both the coordinator (:mod:`friday.learning.skill_pipeline`) and the
hermetic benchmark (:mod:`friday.benchmarks.skill_evolution`) can import it without a
cycle.

The stage is a ``str`` enum, so every ``.value`` is a JSON-safe lowercase string, and
an :attr:`SkillStage.ordinal` (0-based declaration index) makes maturity comparable
so a skill's stage can only advance, never regress.
"""

from __future__ import annotations

from enum import Enum


class SkillStage(str, Enum):
    """The eight ordered FAS §A2.5.1 skill-evolution stages.

    Members are declared in normative order; :attr:`ordinal` returns the 0-based
    declaration index (``OBSERVATION == 0`` … ``REGISTRY == 7``) so two stages are
    directly comparable for maturity. Each ``.value`` is a lowercase JSON-safe string.
    """

    OBSERVATION = "observation"
    EXPERIMENT = "experiment"
    REFLECTION = "reflection"
    VERIFICATION = "verification"
    COMPILATION = "compilation"
    OPTIMIZATION = "optimization"
    GENERALIZATION = "generalization"
    REGISTRY = "registry"

    @property
    def ordinal(self) -> int:
        """Return the 0-based declaration index (OBSERVATION=0 … REGISTRY=7)."""
        return list(SkillStage).index(self)
