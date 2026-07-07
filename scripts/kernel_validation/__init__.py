"""Kernel production-validation tooling (M13, non-production).

Runnable harness that exercises the kernel execution path
(``FRIDAY_USE_KERNEL_EXECUTION=1``) against realistic end-to-end goals and
compares it to the legacy path on identical workloads. This package lives under
``scripts/`` and is NOT imported by any production entry point; it changes no
production default.
"""

from scripts.kernel_validation.scenarios import (
    ValidationScenario,
    all_scenarios,
    categories,
)
from scripts.kernel_validation.evidence import ValidationEvidence

__all__ = [
    "ValidationScenario",
    "all_scenarios",
    "categories",
    "ValidationEvidence",
]
