"""Ch 27 — the capability lifecycle state machine (legal transitions only)."""

from __future__ import annotations

from enum import Enum
from typing import Dict, Set


class LifecycleState(str, Enum):
    DRAFT = "draft"
    EXPERIMENTAL = "experimental"
    VERIFIED = "verified"
    STABLE = "stable"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class CapabilityLifecycle:
    """Ch 27 — the capability lifecycle state machine (legal transitions only)."""

    def __init__(self) -> None:
        self._states: Dict[str, LifecycleState] = {}
        # Legal transitions: forward promotion + deprecation/archival + sanctioned rollbacks.
        self._legal: Dict[LifecycleState, Set[LifecycleState]] = {
            LifecycleState.DRAFT: {
                LifecycleState.EXPERIMENTAL,
                LifecycleState.DEPRECATED,
            },
            LifecycleState.EXPERIMENTAL: {
                LifecycleState.VERIFIED,
                LifecycleState.DRAFT,        # sanctioned rollback
                LifecycleState.DEPRECATED,
            },
            LifecycleState.VERIFIED: {
                LifecycleState.STABLE,
                LifecycleState.EXPERIMENTAL,  # sanctioned rollback
                LifecycleState.DEPRECATED,
            },
            LifecycleState.STABLE: {
                LifecycleState.VERIFIED,      # sanctioned rollback
                LifecycleState.DEPRECATED,
            },
            LifecycleState.DEPRECATED: {
                LifecycleState.ARCHIVED,
            },
            LifecycleState.ARCHIVED: set(),
        }

    def state_of(self, capability_id: str) -> LifecycleState:
        """Return the tracked state, defaulting to DRAFT for an unseen id."""
        return self._states.get(capability_id, LifecycleState.DRAFT)

    def can_transition(self, frm: LifecycleState, to: LifecycleState) -> bool:
        """True iff (frm -> to) is a legal forward step or a sanctioned rollback."""
        return to in self._legal.get(frm, set())

    def transition(self, capability_id: str, to: LifecycleState) -> LifecycleState:
        """Advance a capability; raises ValueError on an illegal transition (state unchanged)."""
        frm = self.state_of(capability_id)
        if not self.can_transition(frm, to):
            raise ValueError(f"illegal transition {frm} -> {to} for {capability_id!r}")
        self._states[capability_id] = to
        return to

    def is_usable_for(self, capability_id: str, risk: str) -> bool:
        """DRAFT/EXPERIMENTAL capabilities may not perform irreversible-risk actions."""
        state = self.state_of(capability_id)
        if risk == "irreversible":
            return state in (LifecycleState.VERIFIED, LifecycleState.STABLE)
        # Any other risk: usable unless archived (archived capabilities are never usable).
        return state is not LifecycleState.ARCHIVED
