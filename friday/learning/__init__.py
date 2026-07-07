"""Ch 15 — Learning layer: improve durably from repeated verified experience.

The M9 Learning subsystem discovers patterns from repeated verified experience,
generalizes them into transferable principles, and promotes learnings to
procedural memory only after a validated pipeline demonstrates measurable
improvement. Like M8 Reflection, it never writes memory directly — it proposes
procedural writes only through ``memory.candidate`` kernel events.

Isolation (Property 1 / Req 5.2): the learning package MUST NOT import
``friday.memory.controller``, ``friday.memory.runtime``, or any
``friday.competence`` module, and MUST NOT reference ``FridayMemory``/``MemoryStore``.

This module re-exports the public learning surface: the kernel-attached
:class:`LearningEngine`, its pure collaborators (:class:`PatternDiscovery`,
:class:`Generalizer`, :class:`LearningValidator`), and the plain data models the
pipeline folds one verified experience through.
"""

from friday.learning.engine import LearningEngine
from friday.learning.generalization import Generalizer
from friday.learning.models import (
    CompetenceKey,
    DiscoveredPattern,
    LearningStep,
    Principle,
    ValidationResult,
    ValidationStatus,
    VerifiedExperience,
)
from friday.learning.patterns import PatternDiscovery
from friday.learning.validation import LearningValidator

__all__ = [
    # Kernel-attached orchestrator + pure collaborators.
    "LearningEngine",
    "PatternDiscovery",
    "Generalizer",
    "LearningValidator",
    # Data models.
    "CompetenceKey",
    "DiscoveredPattern",
    "LearningStep",
    "Principle",
    "ValidationResult",
    "ValidationStatus",
    "VerifiedExperience",
]
