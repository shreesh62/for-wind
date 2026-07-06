"""Ch 34 — Recovery subsystem: the full failure→recovery loop.

Wraps the existing ``RepairDiagnoser`` into the Ch 34 recovery loop with a
failure taxonomy, recovery-level ladder, and Action Rollback Contracts, and
proposes an alternative strategy that preserves the goal id.
"""

from friday.recovery.engine import (
    FailureClass,
    RecoveryAlternative,
    RecoveryEngine,
    RecoveryLevel,
    RecoveryPlan,
    RollbackKind,
)

__all__ = [
    "RecoveryEngine",
    "FailureClass",
    "RecoveryLevel",
    "RollbackKind",
    "RecoveryAlternative",
    "RecoveryPlan",
]
