"""M13 — structured, JSON-serializable validation evidence records.

Every scenario run (on each path) produces a :class:`ValidationEvidence`
capturing the observable result, the lifecycle event types seen, timing, and any
error. Records are pure values with a ``to_dict`` for the parity report and
persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class ValidationEvidence:
    """Evidence from running one scenario on one path (legacy or kernel)."""

    scenario_id: str
    path: str                       # "legacy" | "kernel"
    result: str                     # "pass" | "fail" | "skipped"
    output: str = ""
    event_types: Tuple[str, ...] = ()
    latency_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "path": self.path,
            "result": self.result,
            "output": self.output,
            "event_types": list(self.event_types),
            "latency_ms": self.latency_ms,
            "error": self.error,
        }
