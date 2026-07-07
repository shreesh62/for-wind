"""Ch 35 — PermissionManager: classify every action by permission level and
trust zone, then decide whether it may proceed autonomously, requires
notification, or requires explicit confirmation.

The PermissionManager is the runtime guardian that consults the constitutional
:class:`~friday.safety.policy.SafetyPolicy` (Constitution Article IX). It maps a
:class:`PermissionLevel` to a base :class:`Decision`, escalates that decision
toward safety for untrusted/hostile environments, and fails safe for
irreversible low-confidence actions. It never de-escalates a decision and never
returns ALLOW/NOTIFY for a forbidden level.

Import boundary (Ch 52): this module imports only stdlib, ``friday.events``
(for kernel event emission), and ``friday.safety.policy`` (a sibling within
``friday.safety``). It MUST NOT import memory/competence/learning/resources/
identity modules. Kernel wiring (``attach`` and event emissions) subscribes to
``action.requested`` and publishes ``permission.granted``/``permission.denied``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any

from friday.events.event import make_event
from friday.safety.policy import SafetyPolicy


class PermissionLevel(IntEnum):
    """Ch 35 — nine ascending permission levels; higher = more dangerous."""

    OBSERVATION = 0     # read/inspect/hover — autonomous
    INTERACTION = 1     # click/type/navigate — autonomous
    MODIFICATION = 2    # create files, send messages — notify
    DELETION = 3        # delete files, close apps — confirm
    FINANCIAL = 4       # purchases, transfers — always confirm
    IDENTITY = 5        # passwords, auth tokens — always confirm + vault
    ADMINISTRATIVE = 6  # system settings — always confirm
    KERNEL = 7          # kernel/self-modification — forbidden autonomously
    HARDWARE = 8        # device/hardware control — always confirm


class TrustZone(str, Enum):
    """Ch 35.3 — environment trust classification."""

    TRUSTED = "trusted"
    VERIFIED = "verified"
    RESTRICTED = "restricted"
    UNTRUSTED = "untrusted"
    HOSTILE = "hostile"


class Decision(str, Enum):
    """Ch 35 — the four possible verdicts, ordered from permissive to safe."""

    ALLOW = "allow"      # proceed autonomously
    NOTIFY = "notify"    # proceed but announce
    CONFIRM = "confirm"  # require explicit user approval
    DENY = "deny"        # never allowed


# Safety ordering: a larger index is strictly "more toward safety". Used to keep
# every escalation monotonic — the manager never de-escalates a decision.
_SAFETY_ORDER: dict[Decision, int] = {
    Decision.ALLOW: 0,
    Decision.NOTIFY: 1,
    Decision.CONFIRM: 2,
    Decision.DENY: 3,
}


def _safer(a: Decision, b: Decision) -> Decision:
    """Return whichever of ``a``/``b`` is further toward safety (never de-escalates)."""
    return a if _SAFETY_ORDER[a] >= _SAFETY_ORDER[b] else b


@dataclass(frozen=True)
class PermissionRequest:
    """Ch 35 — an immutable classified request for the manager to judge."""

    action: str
    level: PermissionLevel
    trust_zone: TrustZone
    reversible: bool
    confidence: float


@dataclass(frozen=True)
class PermissionVerdict:
    """Ch 35 — an immutable decision plus the level judged and a short reason."""

    decision: Decision
    level: PermissionLevel
    reason: str


class PermissionManager:
    """Ch 35 — decide autonomy vs confirmation for every action."""

    def __init__(self, *, policy: SafetyPolicy = None) -> None:
        self.policy: SafetyPolicy = policy if policy is not None else SafetyPolicy.default()
        self._kernel: Any = None

    def evaluate(self, request: PermissionRequest) -> PermissionVerdict:
        """Judge ``request`` and return a :class:`PermissionVerdict`.

        The order of checks is deliberate and fails safe:

        1. Forbidden levels are always DENY (Property 1: never ALLOW/NOTIFY for a
           forbidden level).
        2. Irreversible actions below the confidence floor are CONFIRM
           (Property 3: never ALLOW when irreversible + low-confidence).
        3. Levels the policy always confirms are CONFIRM (Property 2).
        4. Otherwise a base decision by level: OBSERVATION/INTERACTION → ALLOW,
           MODIFICATION → NOTIFY, everything else → CONFIRM.
        5. Trust-zone escalation nudges the decision one step toward safety for
           UNTRUSTED/HOSTILE zones (HOSTILE may reach DENY for MODIFICATION+).
           Escalation is monotonic — it never de-escalates.
        6. Requirement 1.4: OBSERVATION/INTERACTION in a TRUSTED/VERIFIED zone is
           always ALLOW.
        """
        level = request.level

        # 1. Hard boundary — forbidden levels can never be granted autonomously.
        if self.policy.is_forbidden(level):
            return PermissionVerdict(
                Decision.DENY,
                level,
                f"level {level.name} is forbidden autonomously",
            )

        # 2. Irreversible + low confidence fails safe to CONFIRM.
        if not request.reversible and request.confidence < self.policy.irreversible_confidence_floor:
            return PermissionVerdict(
                Decision.CONFIRM,
                level,
                (
                    f"irreversible action below confidence floor "
                    f"({request.confidence:.2f} < {self.policy.irreversible_confidence_floor:.2f})"
                ),
            )

        # 3. Policy-mandated confirmation levels.
        if self.policy.requires_confirmation(level):
            return PermissionVerdict(
                Decision.CONFIRM,
                level,
                f"level {level.name} always requires confirmation",
            )

        # 6. Fast path — safe levels in a trusted/verified zone are always ALLOW.
        if level <= PermissionLevel.INTERACTION and request.trust_zone in (
            TrustZone.TRUSTED,
            TrustZone.VERIFIED,
        ):
            return PermissionVerdict(
                Decision.ALLOW,
                level,
                f"{level.name} in {request.trust_zone.value} zone is autonomous",
            )

        # 4. Base decision by level.
        if level <= PermissionLevel.INTERACTION:
            decision = Decision.ALLOW
        elif level == PermissionLevel.MODIFICATION:
            decision = Decision.NOTIFY
        else:
            decision = Decision.CONFIRM

        reason = f"base decision for {level.name}"

        # 5. Trust-zone escalation — one step toward safety, monotonic.
        if request.trust_zone == TrustZone.UNTRUSTED:
            escalated = _safer(decision, Decision.CONFIRM)
            if escalated != decision:
                decision = escalated
                reason = f"{level.name} escalated for untrusted zone"
        elif request.trust_zone == TrustZone.HOSTILE:
            # HOSTILE may escalate to DENY for MODIFICATION and above.
            target = Decision.DENY if level >= PermissionLevel.MODIFICATION else Decision.CONFIRM
            escalated = _safer(decision, target)
            if escalated != decision:
                decision = escalated
                reason = f"{level.name} escalated for hostile zone"

        return PermissionVerdict(decision, level, reason)

    # --- kernel wiring (Ch 52 — kernel-driven; never raises into the tick loop) ---
    def attach(self, kernel: Any) -> None:
        """Subscribe to ``action.requested`` so every action is judged (Req 1.5)."""
        self._kernel = kernel
        kernel.subscribe("action.requested", self._on_action_requested)

    def _on_action_requested(self, event: Any) -> None:
        """Judge an ``action.requested`` event and emit granted/denied (Req 1.5, 1.6).

        Reads the payload defensively. ``level`` may arrive as an int or a
        :class:`PermissionLevel`; ``trust_zone`` may arrive as a string. Missing
        required fields cause a skip. Wrapped in try/except so a malformed event
        can never raise into the kernel tick loop (Req 1.6).
        """
        try:
            payload = getattr(event, "payload", {}) or {}

            action = payload.get("action")
            if not action:
                return

            level = PermissionLevel(int(payload.get("level", 0)))

            try:
                trust_zone = TrustZone(payload.get("trust_zone", "restricted"))
            except Exception:  # noqa: BLE001 — unknown zone → default RESTRICTED
                trust_zone = TrustZone.RESTRICTED

            reversible = bool(payload.get("reversible", True))
            confidence = float(payload.get("confidence", 1.0))

            request = PermissionRequest(
                action=action,
                level=level,
                trust_zone=trust_zone,
                reversible=reversible,
                confidence=confidence,
            )
            verdict = self.evaluate(request)

            if verdict.decision in (Decision.ALLOW, Decision.NOTIFY):
                self._emit(
                    "permission.granted",
                    {
                        "action": action,
                        "level": int(level),
                        "reason": verdict.reason,
                    },
                )
            else:
                self._emit(
                    "permission.denied",
                    {
                        "action": action,
                        "level": int(level),
                        "reason": verdict.reason,
                        "decision": verdict.decision.value,
                    },
                )
        except Exception:  # noqa: BLE001 — never raise into the tick loop
            return

    def _next_tick(self) -> int:
        """Best-effort next logical time from kernel health; defaults to 1."""
        try:
            return int(self._kernel.health().get("tick", 0)) + 1
        except Exception:  # noqa: BLE001 — health must never break emission
            return 1

    def _emit(self, event_type: str, payload: dict) -> None:
        """Publish a kernel event; no-op when no kernel is attached."""
        if self._kernel is None:
            return
        event = make_event(
            event_type,
            source="safety",
            logical_time=self._next_tick(),
            payload=payload,
        )
        self._kernel.publish_event(event)
