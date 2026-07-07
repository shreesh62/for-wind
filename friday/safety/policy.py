"""Ch 35 — SafetyPolicy: immutable hard boundaries + confirmation rules.

The SafetyPolicy is the constitutional core the PermissionManager consults
(Constitution Article IX): a table of PermissionLevels that always require
explicit confirmation and a set of levels that are never allowed autonomously.
It is a frozen dataclass so it cannot be mutated at runtime (self-protection,
Ch 35.7). This module imports nothing from the rest of ``friday`` — the level
enum is referenced lazily inside :meth:`SafetyPolicy.default` to avoid a
circular import with ``friday.safety.permission``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from friday.safety.permission import PermissionLevel


@dataclass(frozen=True)
class SafetyPolicy:
    """Ch 35 — hard boundaries + confirmation rules; immutable at runtime."""

    confirm_levels: frozenset = field(default_factory=frozenset)
    forbidden_levels: frozenset = field(default_factory=frozenset)
    irreversible_confidence_floor: float = 0.85

    def requires_confirmation(self, level: "PermissionLevel") -> bool:
        """True when ``level`` is one that always requires explicit confirmation."""
        return level in self.confirm_levels

    def is_forbidden(self, level: "PermissionLevel") -> bool:
        """True when ``level`` is never allowed autonomously."""
        return level in self.forbidden_levels

    @classmethod
    def default(cls) -> "SafetyPolicy":
        """The default policy: confirm risky levels, forbid autonomous KERNEL."""
        # Lazy import so policy.py never imports permission.py at module load
        # (permission.py imports policy.py — avoids the circular/ordering problem).
        from friday.safety.permission import PermissionLevel

        return cls(
            confirm_levels=frozenset(
                {
                    PermissionLevel.DELETION,
                    PermissionLevel.FINANCIAL,
                    PermissionLevel.IDENTITY,
                    PermissionLevel.ADMINISTRATIVE,
                    PermissionLevel.HARDWARE,
                }
            ),
            forbidden_levels=frozenset({PermissionLevel.KERNEL}),
        )
