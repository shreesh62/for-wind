"""Ch 13 — Cognition: reflection, the learning-loop closure (M8).

Re-exports the Reflection_Engine public surface so callers can do
``from friday.cognition import ReflectionEngine`` without reaching into modules.
"""

from friday.cognition.reflection import (
    ConfidenceCalibrator,
    FiveQuestions,
    ReflectionEngine,
    ReflectionRecord,
    ReflectionScale,
)

__all__ = [
    "ReflectionEngine",
    "ReflectionRecord",
    "FiveQuestions",
    "ReflectionScale",
    "ConfidenceCalibrator",
]
