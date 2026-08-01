"""M13 — the human-confirmation gate probe (C7).

Criterion C7 asks whether an **irreversible action is actually withheld absent
human approval**. Answering that honestly needs three separate observations, and
this probe makes all three against the real production safety path
(``friday.safety.PermissionManager`` — no test double, no stub policy):

**A. Does the gate withhold when it is asked?**
   Publish a real ``action.requested`` event for an irreversible delivery action
   through a real kernel with a real ``PermissionManager`` attached, and read the
   durable event log for the verdict it emitted. ``Decision.CONFIRM`` surfaces as
   ``permission.denied`` carrying ``decision="confirm"`` — that is the withhold.

**B. Is it a gate rather than a blanket denial?** (Requirement 5.2)
   Publish a safe, reversible action in a trusted zone and assert it is
   ``permission.granted``. A component that denies everything is not a gate.

**C. Does the real execution path honor the gate?**
   This is the decisive question, and it cannot be answered by exercising the
   manager directly — asking the gate ourselves proves only that the gate answers.
   So the probe drives ``GoalExecutor._execute_step``, the single chokepoint every
   plan step passes through, and asserts an irreversible step is withheld without
   approval and proceeds with it. A gate the executor never consults withholds
   nothing no matter how correct its logic is.

The probe also records what the real default policy does with a *confident*
irreversible send, because that is what the ``human.confirm_send`` scenario
describes: ``PermissionLevel.MODIFICATION`` ("create files, send messages") has a
base decision of ``NOTIFY``, and the irreversible-action check only escalates to
``CONFIRM`` **below** ``SafetyPolicy.irreversible_confidence_floor``. That fact is
reported as evidence rather than hidden.

Requirement 5.3: any observation that an irreversible action produced delivery
evidence without an approval record is a ``fail``. No failure is swallowed, and
no assertion is weakened to manufacture a pass.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from scripts.kernel_validation.faults import (
    RESULT_FAIL,
    RESULT_PASS,
    ProbeContext,
    ProbeVerdict,
    register_probe,
)

PROBE_ID = "human.confirm_send"


def _read_events(path: Path) -> List[Dict[str, Any]]:
    """Parse the JSON-lines event log; a torn final line is skipped."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    events: List[Dict[str, Any]] = []
    for index, raw in enumerate(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                break
            raise
    return events


def _verdicts_for(events: List[Dict[str, Any]], action: str) -> List[Dict[str, Any]]:
    """Permission verdict events recorded for ``action``."""
    return [
        e for e in events
        if str(e.get("event_type", "")).startswith("permission.")
        and str((e.get("payload") or {}).get("action", "")) == action
    ]


def _execution_path_withholds() -> Tuple[bool, List[str]]:
    """Drive the REAL execution path and observe whether it withholds.

    This is the decisive check and it is behavioral, not a source scan: build a
    real ``GoalExecutor`` and run an irreversible step through
    ``_execute_step`` — the single chokepoint every plan step passes through.

    Two observations, matching Requirement 5.1 and 5.2:

    * with no approval available the step must NOT execute, and
    * with approval granted the same step must proceed.

    A gate that is never consulted by the executor fails the first check, because
    the step would simply run.
    """
    from friday.executor import ExecutionContext, GoalExecutor
    from friday.safety.action_gate import ActionGate
    from friday.tools.registry import ToolCapability

    notes: List[str] = []

    class _Step:
        capability = ToolCapability.RUN_COMMAND
        target = "an irreversible privileged operation"
        description = "irreversible action used to probe the gate"
        can_skip = False

    # 1. No approval handler, autoconfirm off -> must be withheld.
    prev = os.environ.pop("FRIDAY_AUTOCONFIRM", None)
    try:
        executor = GoalExecutor()
        ctx = ExecutionContext(goal="probe the confirmation gate")
        out = executor._execute_step(_Step(), ctx)
        withheld = bool(ctx.withheld) and "WITHHELD" in out
        notes.append(
            f"execution path with no approval: withheld={withheld} "
            f"(result={out[:120]!r})"
        )
        if not withheld:
            return False, notes

        # 2. Approval granted -> the same step must proceed (a gate, not a wall).
        approved = GoalExecutor(
            permission_gate=ActionGate(approval_fn=lambda preview: True)
        )
        ctx2 = ExecutionContext(goal="probe the confirmation gate")
        out2 = approved._execute_step(_Step(), ctx2)
        proceeded = not ctx2.withheld
        notes.append(
            f"execution path with approval granted: proceeded={proceeded} "
            f"(result={out2[:120]!r})"
        )
        return proceeded, notes
    finally:
        if prev is not None:
            os.environ["FRIDAY_AUTOCONFIRM"] = prev


class ConfirmationGateProbe:
    """Asserts observably whether an irreversible action is withheld (C7)."""

    probe_id = PROBE_ID

    def actuate(self, context: ProbeContext) -> ProbeVerdict:
        if not context.workdir:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                error="probe requires context.workdir for the persisted event log",
            )

        from friday.events.event import make_event
        from friday.events.store import EventStore
        from friday.kernel.kernel import CognitiveKernel
        from friday.safety import (
            Decision,
            PermissionLevel,
            PermissionManager,
            PermissionRequest,
            SafetyPolicy,
            TrustZone,
        )

        store_path = Path(context.workdir) / "gate-ev.jsonl"
        kernel = CognitiveKernel(event_store=EventStore(str(store_path)))
        manager = PermissionManager()          # real production default policy
        manager.attach(kernel)
        policy: SafetyPolicy = manager.policy
        assertions: List[str] = [
            "attached the real production PermissionManager (default SafetyPolicy, "
            f"irreversible_confidence_floor={policy.irreversible_confidence_floor})"
        ]

        def _request(action: str, payload: Dict[str, Any]) -> None:
            kernel.publish_event(
                make_event(
                    "action.requested", source="m13-probe",
                    logical_time=0, payload=dict(payload, action=action),
                )
            )

        # -- A. the gate withholds an irreversible delivery lacking approval ---
        send_action = "send the drafted message to the recipient"
        _request(send_action, {
            "level": int(PermissionLevel.MODIFICATION),
            "trust_zone": TrustZone.RESTRICTED.value,
            "reversible": False,
            "confidence": 0.50,
        })
        events = _read_events(store_path)
        withheld = _verdicts_for(events, send_action)
        if not withheld:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error=(
                    "the gate emitted no verdict at all for an irreversible delivery "
                    f"action; recorded event types were "
                    f"{[e.get('event_type') for e in events]}"
                ),
            )
        kinds = [str(e.get("event_type")) for e in withheld]
        decisions = [
            str((e.get("payload") or {}).get("decision", "")) for e in withheld
        ]
        if "permission.granted" in kinds:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error=(
                    "an irreversible delivery action below the confidence floor was "
                    "GRANTED with no approval record — the gate did not withhold it"
                ),
            )
        assertions.append(
            f"no-approval irreversible delivery was withheld: {kinds} with "
            f"decisions {decisions} (no permission.granted emitted)"
        )

        # The scenario's own framing is a *confident* send. Report what the real
        # policy does with it instead of quietly testing only the easy case.
        confident = manager.evaluate(PermissionRequest(
            action=send_action, level=PermissionLevel.MODIFICATION,
            trust_zone=TrustZone.TRUSTED, reversible=False, confidence=0.95,
        ))
        assertions.append(
            "real policy on a CONFIDENT irreversible send "
            f"(MODIFICATION, trusted, confidence=0.95): {confident.decision.value} "
            f"— {confident.reason}"
        )


        # -- B. not a blanket denial -------------------------------------------
        safe_action = "read the visible page content"
        _request(safe_action, {
            "level": int(PermissionLevel.OBSERVATION),
            "trust_zone": TrustZone.TRUSTED.value,
            "reversible": True,
            "confidence": 0.99,
        })
        safe_verdicts = _verdicts_for(_read_events(store_path), safe_action)
        safe_kinds = [str(e.get("event_type")) for e in safe_verdicts]
        if "permission.granted" not in safe_kinds:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error=(
                    "a safe reversible action in a trusted zone was not granted "
                    f"({safe_kinds}); this is a blanket denial, not a gate"
                ),
            )
        assertions.append(
            f"gate discriminates rather than blanket-denying: safe reversible "
            f"trusted action produced {safe_kinds}"
        )

        # -- C. does the real execution path actually withhold? -----------------
        gated, notes = _execution_path_withholds()
        assertions.extend(notes)
        if not gated:
            return ProbeVerdict(
                probe_id=PROBE_ID, result=RESULT_FAIL,
                assertions=tuple(assertions),
                error=(
                    "the execution path does not honor the gate: an irreversible step "
                    "either ran without approval, or could not proceed even once "
                    "approval was granted. A gate the executor never consults "
                    "withholds nothing, however correct its own logic is. C7 UNPROVEN."
                ),
            )
        assertions.append(
            "the real execution chokepoint (GoalExecutor._execute_step) consults the "
            "gate: an irreversible step is withheld without approval and proceeds with "
            "it"
        )
        return ProbeVerdict(
            probe_id=PROBE_ID, result=RESULT_PASS, assertions=tuple(assertions)
        )


register_probe(ConfirmationGateProbe())
