"""M16 — RecoveryContract: how a candidate action can be walked back if it
goes wrong. FAS §A2.3.3 — every action declares
``{undo, rollback, verification, compensation, recovery}``.

The descriptor strings *name* the plan (empty = none); the object is a pure,
immutable, JSON-projectable value with no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class RecoveryContract:
    """A candidate's declared walk-back plan (Requirement 1.1)."""

    undoable: bool = False
    rollback: str = ""
    verification: str = ""
    compensation: str = ""
    recovery: str = ""

    @property
    def has_undo_path(self) -> bool:
        """True when the action is undoable, or a rollback/compensation is
        declared (Requirement 1.2)."""
        return self.undoable or bool(self.rollback) or bool(self.compensation)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe projection of all fields (Requirement 1.5)."""
        return {
            "undoable": self.undoable,
            "rollback": self.rollback,
            "verification": self.verification,
            "compensation": self.compensation,
            "recovery": self.recovery,
        }
