"""M24 — FailureLogSubscriber (audit objective 2: unified observability).

Logging becomes a CONSUMER of the event system. This subscriber listens for the
failure-bearing kernel events (``verification.completed`` failures and
``recovery.proposed``) and emits exactly one structured ``logging`` record per event,
carrying subsystem id, goal id, correlation id, logical time, failure domain, and
severity in the record's ``extra`` fields.

Invariants:
- Reuses the kernel event bus (subscribe), not a private channel.
- Never raises into the bus (a broken observer must not break event delivery),
  mirroring ``EventBus.publish`` isolation.
- Purely a consumer: it publishes nothing and mutates no world state.
"""

from __future__ import annotations

import logging
from typing import Any

from friday.verification.failure import FailureDomain, Severity

_LOGGER_NAME = "friday.observability.failure"

# Severity -> logging level.
_LEVEL_BY_SEVERITY = {
    Severity.LOW: logging.INFO,
    Severity.MEDIUM: logging.INFO,
    Severity.HIGH: logging.WARNING,
    Severity.CRITICAL: logging.ERROR,
}

# RecoveryLevel ordinal at/above which a recovery.proposed is a warning (HUMAN=4).
_HUMAN_LEVEL = 4


class FailureLogSubscriber:
    """Turns failure/recovery kernel events into structured log records."""

    def __init__(self, logger: Any = None) -> None:
        self._logger = logger or logging.getLogger(_LOGGER_NAME)
        self.records_emitted = 0

    def attach(self, kernel: Any) -> None:
        """Subscribe to the failure-bearing kernel event types."""
        kernel.subscribe("verification.completed", self._on_event)
        kernel.subscribe("recovery.proposed", self._on_event)

    def _on_event(self, event: Any) -> None:
        """Emit one structured record for a failure/recovery event. Never raises."""
        try:
            event_type = getattr(event, "event_type", "")
            payload = getattr(event, "payload", {}) or {}

            if event_type == "verification.completed":
                # Only FAILURES are logged (a satisfied verdict is not a failure).
                if payload.get("satisfied"):
                    return
                domain = FailureDomain.VERIFICATION
                severity = Severity.HIGH
                failure_class = "verification"
                message = payload.get("requirement", "") or "requirement unmet"
            elif event_type == "recovery.proposed":
                failure_class = str(payload.get("failure_class", "") or "unknown")
                level = int(payload.get("level", 0) or 0)
                domain = FailureDomain.UNKNOWN
                severity = Severity.HIGH if level >= _HUMAN_LEVEL else Severity.MEDIUM
                message = f"recovery proposed (class={failure_class}, level={level})"
            else:
                return

            level = _LEVEL_BY_SEVERITY.get(severity, logging.INFO)
            self._logger.log(
                level,
                "%s: %s",
                event_type,
                message,
                extra={
                    "subsystem": getattr(event, "source", "") or "unknown",
                    "goal_id": payload.get("goal_id", ""),
                    "correlation_id": getattr(event, "correlation_id", ""),
                    "logical_time": getattr(event, "logical_time", 0),
                    "failure_domain": domain.value,
                    "failure_class": failure_class,
                    "severity": int(severity),
                    "event_type": event_type,
                },
            )
            self.records_emitted += 1
        except Exception:  # noqa: BLE001 - observability must never break the bus
            return
