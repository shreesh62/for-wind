"""ActionResult — Universal contract for action outcomes.

Every action in FRIDAY must return an ActionResult. This is the single
most important contract in the system. It eliminates "illusion success"
by requiring evidence for every outcome.

Design principles:
- Every action produces an ActionResult (no exceptions)
- Success requires evidence (state change proof)
- Failures include diagnostic information for repair
- Before/after hashes enable verification
- Duration tracking enables performance monitoring
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ActionStatus(str, Enum):
    """Outcome status of an action."""

    SUCCESS = "success"         # Action completed and verified
    PARTIAL = "partial"         # Action partially completed
    FAILED = "failed"           # Action failed
    TIMEOUT = "timeout"         # Action timed out
    BLOCKED = "blocked"         # Action blocked (dialog, auth, etc.)
    SKIPPED = "skipped"         # Action was skipped (precondition not met)
    NEEDS_REPAIR = "needs_repair"  # Action failed but repair is possible


@dataclass
class ActionEvidence:
    """Evidence that an action succeeded or failed.

    Evidence is what distinguishes a verified outcome from an
    "illusion success". At minimum, before/after state hashes
    should differ for state-changing actions.
    """

    before_hash: str = ""
    after_hash: str = ""
    state_changed: bool = False

    # What changed (specific signals)
    window_changed: bool = False
    url_changed: bool = False
    focus_changed: bool = False
    text_appeared: Optional[str] = None
    text_disappeared: Optional[str] = None
    element_appeared: Optional[str] = None
    screenshot_changed: bool = False

    # Raw evidence data (for debugging / repair)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_evidence(self) -> bool:
        """Whether any evidence of change was collected."""
        return (
            self.state_changed
            or self.window_changed
            or self.url_changed
            or self.focus_changed
            or self.text_appeared is not None
            or self.element_appeared is not None
            or self.screenshot_changed
            or self.before_hash != self.after_hash
        )


@dataclass
class ActionResult:
    """Universal result contract for all FRIDAY actions.

    Usage:
        result = ActionResult.success(
            action="click",
            target="Submit button",
            evidence=ActionEvidence(
                before_hash="abc123",
                after_hash="def456",
                state_changed=True,
                text_appeared="Form submitted",
            ),
        )
    """

    # Core outcome
    status: ActionStatus
    action_type: str
    target: str = ""
    message: str = ""

    # Evidence (required for SUCCESS)
    evidence: ActionEvidence = field(default_factory=ActionEvidence)

    # Timing
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_ms: float = 0.0

    # Error information (for FAILED / NEEDS_REPAIR)
    error: Optional[str] = None
    error_category: Optional[str] = None
    repair_hints: List[str] = field(default_factory=list)

    # Context
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """Whether the action succeeded."""
        return self.status == ActionStatus.SUCCESS

    @property
    def verified(self) -> bool:
        """Whether the action outcome is backed by evidence."""
        return self.is_success and self.evidence.has_evidence

    @property
    def needs_repair(self) -> bool:
        """Whether the action failed but repair is possible."""
        return self.status == ActionStatus.NEEDS_REPAIR

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for logging, API responses, telemetry."""
        return {
            "status": self.status.value,
            "action_type": self.action_type,
            "target": self.target,
            "message": self.message,
            "success": self.is_success,
            "verified": self.verified,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "error_category": self.error_category,
            "repair_hints": self.repair_hints,
            "evidence": {
                "before_hash": self.evidence.before_hash,
                "after_hash": self.evidence.after_hash,
                "state_changed": self.evidence.state_changed,
                "has_evidence": self.evidence.has_evidence,
            },
        }

    # --- Factory Methods ---

    @classmethod
    def success(
        cls,
        action: str,
        target: str = "",
        message: str = "",
        evidence: Optional[ActionEvidence] = None,
        **kwargs: Any,
    ) -> "ActionResult":
        """Create a successful action result."""
        now = time.time()
        return cls(
            status=ActionStatus.SUCCESS,
            action_type=action,
            target=target,
            message=message or f"{action} completed successfully",
            evidence=evidence or ActionEvidence(),
            started_at=kwargs.get("started_at", now),
            completed_at=now,
            duration_ms=kwargs.get("duration_ms", 0.0),
            metadata=kwargs.get("metadata", {}),
        )

    @classmethod
    def failed(
        cls,
        action: str,
        error: str,
        target: str = "",
        error_category: Optional[str] = None,
        repair_hints: Optional[List[str]] = None,
        evidence: Optional[ActionEvidence] = None,
        **kwargs: Any,
    ) -> "ActionResult":
        """Create a failed action result."""
        now = time.time()
        return cls(
            status=ActionStatus.FAILED,
            action_type=action,
            target=target,
            message=f"{action} failed: {error}",
            error=error,
            error_category=error_category,
            repair_hints=repair_hints or [],
            evidence=evidence or ActionEvidence(),
            started_at=kwargs.get("started_at", now),
            completed_at=now,
            duration_ms=kwargs.get("duration_ms", 0.0),
            metadata=kwargs.get("metadata", {}),
        )

    @classmethod
    def timeout(
        cls,
        action: str,
        target: str = "",
        duration_ms: float = 0.0,
        **kwargs: Any,
    ) -> "ActionResult":
        """Create a timeout action result."""
        now = time.time()
        return cls(
            status=ActionStatus.TIMEOUT,
            action_type=action,
            target=target,
            message=f"{action} timed out after {duration_ms:.0f}ms",
            error="Timeout",
            error_category="timeout",
            repair_hints=["retry", "increase_timeout", "check_state"],
            started_at=kwargs.get("started_at", now),
            completed_at=now,
            duration_ms=duration_ms,
            metadata=kwargs.get("metadata", {}),
        )

    @classmethod
    def blocked(
        cls,
        action: str,
        reason: str,
        target: str = "",
        repair_hints: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> "ActionResult":
        """Create a blocked action result (dialog, auth barrier, etc.)."""
        now = time.time()
        return cls(
            status=ActionStatus.BLOCKED,
            action_type=action,
            target=target,
            message=f"{action} blocked: {reason}",
            error=reason,
            error_category="blocked",
            repair_hints=repair_hints or ["dismiss_dialog", "handle_auth"],
            started_at=kwargs.get("started_at", now),
            completed_at=now,
            metadata=kwargs.get("metadata", {}),
        )


class ActionTimer:
    """Context manager for timing action execution.

    Usage:
        with ActionTimer() as timer:
            # perform action
            ...
        result.started_at = timer.started_at
        result.completed_at = timer.completed_at
        result.duration_ms = timer.duration_ms
    """

    def __init__(self) -> None:
        self.started_at: float = 0.0
        self.completed_at: float = 0.0
        self.duration_ms: float = 0.0

    def __enter__(self) -> "ActionTimer":
        self.started_at = time.time()
        self._perf_start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self.completed_at = time.time()
        self.duration_ms = (time.perf_counter() - self._perf_start) * 1000
