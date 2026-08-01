"""M24 — Structured failure model (audit objectives 1 & 3).

Turns the free-form ``ActionResult.error_category`` string convention and unmet
``RequirementVerdict`` outcomes into FIRST-CLASS, classifiable failure objects,
WITHOUT rewriting the ~19 existing producers (they keep emitting strings; a pure,
total classifier maps them onto a canonical taxonomy).

Two orthogonal dimensions are kept deliberately separate (no duplicate systems):

* ``FailureDomain`` (THIS module) — *where/at which stage* a failure originated
  (perception, resource, environment, capability, verification, planning,
  execution, external service). New in M24.
* ``recovery.engine.FailureClass`` / ``RecoveryLevel`` — *how recoverable* the
  failure is and the escalation ladder. Reused verbatim, never redefined.

CRITICAL (Axiom 15): the classifier is a DATA map over generic category tokens
plus generic substring heuristics. There is no application/site/browser identity
anywhere — a "timeout" is a timeout regardless of which app produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Dict, Optional, Tuple


class FailureDomain(str, Enum):
    """The stage/subsystem a failure originated in (orthogonal to recoverability)."""

    PERCEPTION = "perception"
    RESOURCE = "resource"
    ENVIRONMENT = "environment"
    CAPABILITY = "capability"
    VERIFICATION = "verification"
    PLANNING = "planning"
    EXECUTION = "execution"
    EXTERNAL_SERVICE = "external_service"
    UNKNOWN = "unknown"


class Severity(IntEnum):
    """Failure severity — drives log level and recovery escalation."""

    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


# --- Structured error model: canonical map from existing free-form categories ---
# These keys are the EXACT free-form ``error_category`` strings observed across
# friday/ (target_not_found, adapter_failed, perception_unavailable, ...). This is
# configuration DATA, not per-app logic (Axiom 15).
_EXACT_CATEGORY_MAP: Dict[str, FailureDomain] = {
    # perception / target resolution
    "target_not_found": FailureDomain.PERCEPTION,
    "perception_unavailable": FailureDomain.PERCEPTION,
    "perception_insufficient": FailureDomain.PERCEPTION,
    "not_found": FailureDomain.PERCEPTION,
    # environment state (window/focus/launch/blocked walls)
    "window_not_found": FailureDomain.ENVIRONMENT,
    "no_focus": FailureDomain.ENVIRONMENT,
    "launch_failed": FailureDomain.ENVIRONMENT,
    "blocked": FailureDomain.ENVIRONMENT,
    # execution / motor / adapter
    "adapter_failed": FailureDomain.EXECUTION,
    "motor": FailureDomain.EXECUTION,
    "action_exception": FailureDomain.EXECUTION,
    "desktop_error": FailureDomain.EXECUTION,
    "window_op_failed": FailureDomain.EXECUTION,
    "timeout": FailureDomain.EXECUTION,
    # capability availability / wiring
    "not_initialized": FailureDomain.CAPABILITY,
    "unwired_descriptor": FailureDomain.CAPABILITY,
    "unsupported_capability": FailureDomain.CAPABILITY,
    # resource acquisition
    "acquisition": FailureDomain.RESOURCE,
    # verification
    "verification_failed": FailureDomain.VERIFICATION,
}

# Generic substring signals (checked only when no exact match). Ordered: the first
# matching token wins. Generic vocabulary, never application identity.
_SUBSTRING_SIGNALS: Tuple[Tuple[str, FailureDomain], ...] = (
    ("percept", FailureDomain.PERCEPTION),
    ("verif", FailureDomain.VERIFICATION),
    ("plan", FailureDomain.PLANNING),
    ("window", FailureDomain.ENVIRONMENT),
    ("focus", FailureDomain.ENVIRONMENT),
    ("blocked", FailureDomain.ENVIRONMENT),
    ("launch", FailureDomain.ENVIRONMENT),
    ("session", FailureDomain.ENVIRONMENT),
    ("capab", FailureDomain.CAPABILITY),
    ("unwired", FailureDomain.CAPABILITY),
    ("unsupported", FailureDomain.CAPABILITY),
    ("initial", FailureDomain.CAPABILITY),
    ("resource", FailureDomain.RESOURCE),
    ("acquisition", FailureDomain.RESOURCE),
    ("memory", FailureDomain.RESOURCE),
    ("budget", FailureDomain.RESOURCE),
    ("network", FailureDomain.EXTERNAL_SERVICE),
    ("http", FailureDomain.EXTERNAL_SERVICE),
    ("api", FailureDomain.EXTERNAL_SERVICE),
    ("model", FailureDomain.EXTERNAL_SERVICE),
    ("provider", FailureDomain.EXTERNAL_SERVICE),
    ("rate", FailureDomain.EXTERNAL_SERVICE),
    ("adapter", FailureDomain.EXECUTION),
    ("motor", FailureDomain.EXECUTION),
    ("exec", FailureDomain.EXECUTION),
    ("action", FailureDomain.EXECUTION),
    ("desktop", FailureDomain.EXECUTION),
    ("timeout", FailureDomain.EXECUTION),
    ("target", FailureDomain.PERCEPTION),
    ("not_found", FailureDomain.PERCEPTION),
)


def _classify_with_confidence(category: Optional[str]) -> Tuple[FailureDomain, float]:
    """Return (domain, classification_confidence) for a free-form category string.

    Total function: any input yields a domain. Exact map hit ⇒ high confidence,
    substring signal ⇒ medium, otherwise ``UNKNOWN`` at low confidence.
    """
    if not category or not str(category).strip():
        return FailureDomain.UNKNOWN, 0.3
    key = str(category).strip().lower()
    exact = _EXACT_CATEGORY_MAP.get(key)
    if exact is not None:
        return exact, 0.9
    for token, domain in _SUBSTRING_SIGNALS:
        if token in key:
            return domain, 0.6
    return FailureDomain.UNKNOWN, 0.3


def classify_error_category(category: Optional[str]) -> FailureDomain:
    """Map a free-form ``error_category`` to a canonical :class:`FailureDomain`.

    A TOTAL, pure function (never raises). Unknown/empty ⇒ ``FailureDomain.UNKNOWN``.
    """
    return _classify_with_confidence(category)[0]


# Recommended first recovery level per domain, as a RecoveryLevel ordinal. Uses the
# EXISTING recovery ladder (recovery.engine.RecoveryLevel) — no new taxonomy.
#   MICRO=0 LOCAL=1 ENVIRONMENTAL=2 STRATEGIC=3 HUMAN=4 ARCHITECTURAL=5
_DOMAIN_RECOVERY_LEVEL: Dict[FailureDomain, int] = {
    FailureDomain.EXECUTION: 0,          # retry the same action
    FailureDomain.EXTERNAL_SERVICE: 0,   # retry with backoff
    FailureDomain.PERCEPTION: 1,         # re-observe / different capability
    FailureDomain.VERIFICATION: 1,
    FailureDomain.RESOURCE: 2,           # change/refresh resource
    FailureDomain.ENVIRONMENT: 2,        # change environment/session
    FailureDomain.CAPABILITY: 3,         # replan with a different capability
    FailureDomain.PLANNING: 3,           # replan the approach
    FailureDomain.UNKNOWN: 1,
}

_HUMAN_LEVEL = 4  # RecoveryLevel.HUMAN — used when a failure is not recoverable


@dataclass(frozen=True)
class StructuredFailure:
    """A first-class failure: domain + severity + recoverability + evidence.

    Carries everything a recovery/observability consumer needs to reason over a
    failure without re-parsing free-form strings. Immutable and JSON-projectable.
    """

    domain: FailureDomain
    severity: Severity
    category: str                 # the original free-form error_category (provenance)
    message: str = ""
    confidence: float = 0.5       # confidence of the classification, in [0,1]
    recoverable: bool = True
    recommended_recovery: int = 1  # a RecoveryLevel ordinal
    goal_id: str = ""
    capability: str = ""
    environment: str = ""
    requirement: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        """Project into a JSON-serializable payload (enums → primitives)."""
        return {
            "domain": self.domain.value,
            "severity": int(self.severity),
            "category": self.category,
            "message": self.message,
            "confidence": self.confidence,
            "recoverable": self.recoverable,
            "recommended_recovery": int(self.recommended_recovery),
            "goal_id": self.goal_id,
            "capability": self.capability,
            "environment": self.environment,
            "requirement": self.requirement,
            "evidence": dict(self.evidence),
        }

    # -- constructors (never raise; default missing fields safely) --

    @classmethod
    def from_action_result(
        cls,
        result: Any,
        *,
        goal_id: str = "",
        capability: str = "",
        environment: str = "",
    ) -> "StructuredFailure":
        """Build a StructuredFailure from an ``ActionResult``-like object."""
        category = str(getattr(result, "error_category", "") or "")
        message = str(getattr(result, "error", "") or "")
        status = getattr(result, "status", None)
        status_val = getattr(status, "value", status)
        domain, conf = _classify_with_confidence(category)
        severity = _severity_from_status(status_val)
        recoverable = _recoverable_from_status(status_val)
        return cls(
            domain=domain,
            severity=severity,
            category=category,
            message=message,
            confidence=conf,
            recoverable=recoverable,
            recommended_recovery=_recommended_level(domain, recoverable),
            goal_id=goal_id,
            capability=capability,
            environment=environment,
            evidence={"status": status_val, "error_category": category},
        )

    @classmethod
    def from_verdict(
        cls,
        verdict: Any,
        *,
        goal_id: str = "",
        capability: str = "",
        environment: str = "",
    ) -> "StructuredFailure":
        """Build a StructuredFailure from an unmet ``RequirementVerdict``-like object.

        An unmet requirement is DETECTED at the verification stage; it is recoverable
        (the repair diagnoser exists to target it).
        """
        requirement = str(getattr(verdict, "description", "") or "")
        reason = str(getattr(verdict, "reason", "") or "")
        kind = getattr(verdict, "kind", None)
        kind_val = str(getattr(kind, "value", kind) or "")
        return cls(
            domain=FailureDomain.VERIFICATION,
            severity=Severity.HIGH,
            category="verification_failed",
            message=reason or f"requirement unmet ({kind_val})",
            confidence=0.9,
            recoverable=True,
            recommended_recovery=_DOMAIN_RECOVERY_LEVEL[FailureDomain.VERIFICATION],
            goal_id=goal_id,
            capability=capability,
            environment=environment,
            requirement=requirement,
            evidence={"requirement_kind": kind_val, "reason": reason},
        )


def _severity_from_status(status_val: Any) -> Severity:
    """Map an ActionStatus value string to a Severity (total; defaults LOW)."""
    mapping = {
        "failed": Severity.HIGH,
        "timeout": Severity.HIGH,
        "needs_repair": Severity.MEDIUM,
        "partial": Severity.MEDIUM,
        "blocked": Severity.MEDIUM,
        "skipped": Severity.LOW,
        "success": Severity.LOW,
    }
    return mapping.get(str(status_val or "").lower(), Severity.MEDIUM)


def _recoverable_from_status(status_val: Any) -> bool:
    """Whether a status is worth attempting recovery on (total)."""
    return str(status_val or "").lower() in {
        "failed", "timeout", "blocked", "needs_repair", "partial"
    }


def _recommended_level(domain: FailureDomain, recoverable: bool) -> int:
    """Recommended first recovery level; escalate to HUMAN when not recoverable."""
    if not recoverable:
        return _HUMAN_LEVEL
    return _DOMAIN_RECOVERY_LEVEL.get(domain, 1)
