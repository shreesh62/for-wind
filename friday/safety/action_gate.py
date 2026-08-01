"""Ch 35 — ActionGate: the permission gate wired into the execution path.

The :class:`~friday.safety.permission.PermissionManager` decides whether an action
may proceed autonomously, but a decision nobody asks for withholds nothing. This
module is the missing caller: it classifies an execution capability into a
:class:`PermissionLevel` plus a reversibility flag, asks the real manager, and
returns a decision the executor must honor **before** dispatching the step.

Confirmation philosophy (matching ``friday.actions.delivery.DeliveryGate``, which
this generalizes from delivery-only to every capability):

* A ``CONFIRM`` decision requires explicit approval. With no approval handler and
  no ``FRIDAY_AUTOCONFIRM``, the action is **withheld** — nothing irreversible ever
  happens silently by accident.
* ``FRIDAY_AUTOCONFIRM=1`` grants approval, so full autonomy stays one flag away.
* ``DENY`` is never approvable.

On confidence: this layer has no independent confidence estimate for a plan step.
Rather than invent one, it passes the honest value — ``0.0`` for an irreversible
action whose confidence is genuinely unknown, which lets the policy's existing
``irreversible_confidence_floor`` rule escalate it to ``CONFIRM``. A step that
carries its own confidence is passed through unchanged.

Delivery capabilities (``SEND_MESSAGE`` / ``SEND_EMAIL``) are the one deliberate
exception: ``DeliveryGate`` already performs the user-facing preview-and-confirm for
them further down the path, so this gate consults the manager (it is still asked)
but does not double-prompt. See ``_DELIVERY_CONFIRMED_DOWNSTREAM``.

Import boundary (Ch 52): imports only ``friday.safety`` and stdlib. The capability
enum arrives as a plain value, so this module never imports ``friday.tools``.
It contains no application or site names (Axiom 15).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from friday.safety.permission import (
    Decision,
    PermissionLevel,
    PermissionManager,
    PermissionRequest,
    TrustZone,
)

logger = logging.getLogger(__name__)

# Capability name -> (permission level, reversible). Keyed by the capability's
# STRING value so this module needs no import of the tool registry.
_CAPABILITY_POLICY: dict = {
    # Observation — read-only, autonomous.
    "read_screen": (PermissionLevel.OBSERVATION, True),
    "read_dom": (PermissionLevel.OBSERVATION, True),
    "read_ui_controls": (PermissionLevel.OBSERVATION, True),
    "read_file": (PermissionLevel.OBSERVATION, True),
    "search_web": (PermissionLevel.OBSERVATION, True),
    "extract_web_content": (PermissionLevel.OBSERVATION, True),
    "check_process": (PermissionLevel.OBSERVATION, True),
    "recall_memory": (PermissionLevel.OBSERVATION, True),
    "verify_result": (PermissionLevel.OBSERVATION, True),
    "verify_goal": (PermissionLevel.OBSERVATION, True),
    "generate_text": (PermissionLevel.OBSERVATION, True),
    "summarize": (PermissionLevel.OBSERVATION, True),
    # Interaction — reversible UI input, autonomous.
    "open_application": (PermissionLevel.INTERACTION, True),
    "switch_window": (PermissionLevel.INTERACTION, True),
    "navigate_url": (PermissionLevel.INTERACTION, True),
    "click_element": (PermissionLevel.INTERACTION, True),
    "type_text": (PermissionLevel.INTERACTION, True),
    "scroll": (PermissionLevel.INTERACTION, True),
    # Agentic website operation — interactive by nature.
    "operate_website": (PermissionLevel.INTERACTION, True),
    # Modification — creates/changes state; reversible enough to notify.
    "create_file": (PermissionLevel.MODIFICATION, True),
    "edit_file": (PermissionLevel.MODIFICATION, True),
    "create_document": (PermissionLevel.MODIFICATION, True),
    "move_file": (PermissionLevel.MODIFICATION, False),
    "store_memory": (PermissionLevel.MODIFICATION, True),
    "download_file": (PermissionLevel.MODIFICATION, True),
    # Irreversible external effects.
    "upload_file": (PermissionLevel.MODIFICATION, False),
    "send_message": (PermissionLevel.MODIFICATION, False),
    "send_email": (PermissionLevel.MODIFICATION, False),
    # Destructive / privileged.
    "delete_file": (PermissionLevel.DELETION, False),
    "run_command": (PermissionLevel.ADMINISTRATIVE, False),
}

# Capabilities whose user-facing confirmation is owned by DeliveryGate further
# down the execution path. The manager is still consulted for them; this gate just
# does not raise a second prompt for the same action.
_DELIVERY_CONFIRMED_DOWNSTREAM = frozenset({"send_message", "send_email"})

# An unknown capability is treated as a modification rather than as observation:
# defaulting to the safer classification means a newly added capability cannot
# quietly acquire more authority than it was reviewed for.
_UNKNOWN_POLICY: Tuple[PermissionLevel, bool] = (PermissionLevel.MODIFICATION, False)


def _autoconfirm_enabled() -> bool:
    return os.environ.get("FRIDAY_AUTOCONFIRM", "0").strip().lower() in ("1", "true", "yes")


def capability_name(capability: Any) -> str:
    """The string name of a capability, whether enum or plain string."""
    return str(getattr(capability, "value", capability) or "").strip().lower()


def classify_capability(capability: Any) -> Tuple[PermissionLevel, bool]:
    """Return ``(level, reversible)`` for ``capability`` (safe default if unknown)."""
    return _CAPABILITY_POLICY.get(capability_name(capability), _UNKNOWN_POLICY)


@dataclass(frozen=True)
class GateDecision:
    """The gate's answer for one action, with the reason it can be audited by."""

    allowed: bool
    decision: Decision
    level: PermissionLevel
    reason: str
    approved_by: str = ""       # "autoconfirm" | "approval_handler" | ""
    capability: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "decision": self.decision.value,
            "level": int(self.level),
            "reason": self.reason,
            "approved_by": self.approved_by,
            "capability": self.capability,
        }


class ActionGate:
    """Consults the real PermissionManager before an action is executed.

    ``approval_fn(preview: str) -> bool`` asks the human when a decision is
    ``CONFIRM``. Absent a handler (and absent ``FRIDAY_AUTOCONFIRM``) a ``CONFIRM``
    is withheld — the fail-safe direction.
    """

    def __init__(
        self,
        *,
        manager: Optional[PermissionManager] = None,
        approval_fn: Optional[Callable[[str], bool]] = None,
        trust_zone: TrustZone = TrustZone.RESTRICTED,
    ) -> None:
        self._manager = manager or PermissionManager()
        self._approval_fn = approval_fn
        self._trust_zone = trust_zone

    @property
    def manager(self) -> PermissionManager:
        return self._manager

    def authorize(
        self,
        capability: Any,
        target: str = "",
        *,
        confidence: Optional[float] = None,
        trust_zone: Optional[TrustZone] = None,
    ) -> GateDecision:
        """Judge one action. Never raises — an internal error fails safe to withheld."""
        name = capability_name(capability)
        level, reversible = classify_capability(capability)

        if confidence is None:
            # No independent confidence signal at this layer. For an irreversible
            # action that genuinely-unknown confidence is 0.0, which lets the
            # policy's irreversible-confidence floor escalate to CONFIRM.
            if reversible or name in _DELIVERY_CONFIRMED_DOWNSTREAM:
                confidence = 1.0
            else:
                confidence = 0.0

        try:
            verdict = self._manager.evaluate(
                PermissionRequest(
                    action=f"{name}:{target}"[:200],
                    level=level,
                    trust_zone=trust_zone or self._trust_zone,
                    reversible=reversible,
                    confidence=float(confidence),
                )
            )
        except Exception as exc:  # noqa: BLE001 — fail safe, never fail open
            logger.warning("permission evaluation failed for %s: %r", name, exc)
            return GateDecision(
                allowed=False, decision=Decision.DENY, level=level,
                reason=f"permission evaluation failed: {exc}", capability=name,
            )

        if verdict.decision in (Decision.ALLOW, Decision.NOTIFY):
            return GateDecision(
                allowed=True, decision=verdict.decision, level=verdict.level,
                reason=verdict.reason, capability=name,
            )

        if verdict.decision == Decision.DENY:
            return GateDecision(
                allowed=False, decision=Decision.DENY, level=verdict.level,
                reason=verdict.reason, capability=name,
            )

        # CONFIRM — approval required.
        if name in _DELIVERY_CONFIRMED_DOWNSTREAM:
            return GateDecision(
                allowed=True, decision=verdict.decision, level=verdict.level,
                reason=(f"{verdict.reason}; confirmation owned by the delivery gate "
                        "further down the execution path"),
                approved_by="delivery_gate", capability=name,
            )
        if _autoconfirm_enabled():
            return GateDecision(
                allowed=True, decision=verdict.decision, level=verdict.level,
                reason=f"{verdict.reason}; approved via FRIDAY_AUTOCONFIRM",
                approved_by="autoconfirm", capability=name,
            )
        if self._approval_fn is not None:
            preview = f"{name} -> {target}" if target else name
            try:
                approved = bool(self._approval_fn(preview))
            except Exception as exc:  # noqa: BLE001 — an error is not an approval
                logger.warning("approval handler failed for %s: %r", name, exc)
                return GateDecision(
                    allowed=False, decision=verdict.decision, level=verdict.level,
                    reason=f"approval handler error: {exc}", capability=name,
                )
            if approved:
                return GateDecision(
                    allowed=True, decision=verdict.decision, level=verdict.level,
                    reason=f"{verdict.reason}; approved by handler",
                    approved_by="approval_handler", capability=name,
                )
            return GateDecision(
                allowed=False, decision=verdict.decision, level=verdict.level,
                reason=f"{verdict.reason}; approval declined", capability=name,
            )

        return GateDecision(
            allowed=False, decision=verdict.decision, level=verdict.level,
            reason=(f"{verdict.reason}; no approval handler and FRIDAY_AUTOCONFIRM "
                    "is off, so the action was withheld"),
            capability=name,
        )
