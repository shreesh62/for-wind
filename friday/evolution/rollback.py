"""Ch 27 — restore the last-known-good capability version."""

from __future__ import annotations

from typing import Any, Dict


class RollbackManager:
    """Ch 27.12 — restore the last-known-good capability version."""

    def __init__(self) -> None:
        self._snapshots: Dict[str, Any] = {}

    def record_stable(self, capability_id: str, snapshot: Any) -> None:
        """Remember a known-good snapshot before promoting a replacement."""
        self._snapshots[capability_id] = snapshot

    def can_rollback(self, capability_id: str) -> bool:
        """True iff a snapshot exists for the capability."""
        return capability_id in self._snapshots

    def rollback(self, capability_id: str) -> Any:
        """Return the last-known-good snapshot; raises LookupError if none exists."""
        if capability_id not in self._snapshots:
            raise LookupError(f"no snapshot recorded for {capability_id!r}")
        return self._snapshots[capability_id]
