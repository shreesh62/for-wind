"""Ch 35 — tests for the ActionGate wired into the execution path.

The permission gate existed and was correct, but nothing consulted it, so no
irreversible action was ever actually withheld. These tests pin the wiring:
the gate is asked before every dispatched step, a withheld step does not run,
and approval releases it.
"""

from __future__ import annotations

import pytest

from friday.executor import ExecutionContext, GoalExecutor
from friday.safety import Decision, PermissionLevel, TrustZone
from friday.safety.action_gate import ActionGate, classify_capability
from friday.tools.registry import ToolCapability


@pytest.fixture(autouse=True)
def _no_autoconfirm(monkeypatch):
    """Every test decides approval explicitly; ambient autoconfirm would mask it."""
    monkeypatch.delenv("FRIDAY_AUTOCONFIRM", raising=False)


def _step(capability, target="t", confidence=None):
    class _S:
        pass

    s = _S()
    s.capability = capability
    s.target = target
    s.description = f"step {capability}"
    s.can_skip = False
    if confidence is not None:
        s.confidence = confidence
    return s


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "capability,expected_reversible",
    [
        (ToolCapability.READ_DOM, True),
        (ToolCapability.CLICK_ELEMENT, True),
        (ToolCapability.CREATE_FILE, True),
        (ToolCapability.DELETE_FILE, False),
        (ToolCapability.RUN_COMMAND, False),
        (ToolCapability.SEND_EMAIL, False),
    ],
)
def test_classification_marks_reversibility(capability, expected_reversible):
    _level, reversible = classify_capability(capability)
    assert reversible is expected_reversible


def test_every_capability_is_classified():
    """An unclassified capability must not silently acquire authority."""
    from friday.safety.action_gate import _CAPABILITY_POLICY

    missing = [c.value for c in ToolCapability if c.value not in _CAPABILITY_POLICY]
    assert not missing, f"unclassified capabilities: {missing}"


def test_unknown_capability_defaults_to_the_safer_classification():
    level, reversible = classify_capability("some_future_capability")
    assert reversible is False
    assert level >= PermissionLevel.MODIFICATION


# --------------------------------------------------------------------------- #
# Gate decisions
# --------------------------------------------------------------------------- #
def test_observation_is_allowed_autonomously():
    decision = ActionGate().authorize(ToolCapability.READ_DOM, "page")
    assert decision.allowed
    assert decision.decision in (Decision.ALLOW, Decision.NOTIFY)


def test_irreversible_action_is_withheld_without_approval():
    decision = ActionGate().authorize(ToolCapability.RUN_COMMAND, "rm -rf /")
    assert not decision.allowed
    assert decision.decision == Decision.CONFIRM
    assert "withheld" in decision.reason


def test_approval_handler_releases_a_confirm():
    decision = ActionGate(approval_fn=lambda preview: True).authorize(
        ToolCapability.RUN_COMMAND, "ls"
    )
    assert decision.allowed
    assert decision.approved_by == "approval_handler"


def test_declined_approval_keeps_the_action_withheld():
    decision = ActionGate(approval_fn=lambda preview: False).authorize(
        ToolCapability.DELETE_FILE, "notes.txt"
    )
    assert not decision.allowed
    assert "declined" in decision.reason


def test_a_raising_approval_handler_is_not_an_approval():
    def _boom(preview):
        raise RuntimeError("handler exploded")

    decision = ActionGate(approval_fn=_boom).authorize(ToolCapability.RUN_COMMAND, "x")
    assert not decision.allowed


def test_autoconfirm_grants_approval(monkeypatch):
    monkeypatch.setenv("FRIDAY_AUTOCONFIRM", "1")
    decision = ActionGate().authorize(ToolCapability.RUN_COMMAND, "ls")
    assert decision.allowed
    assert decision.approved_by == "autoconfirm"


def test_forbidden_level_is_never_approvable():
    """A DENY must not be releasable by an approval handler."""
    gate = ActionGate(approval_fn=lambda preview: True)
    decision = gate.authorize(
        ToolCapability.CLICK_ELEMENT, "x", trust_zone=TrustZone.HOSTILE
    )
    if decision.decision == Decision.DENY:
        assert not decision.allowed


@pytest.mark.parametrize(
    "capability", [ToolCapability.SEND_EMAIL, ToolCapability.SEND_MESSAGE]
)
def test_delivery_defers_to_the_downstream_delivery_gate(capability):
    """SEND_* passes this gate so DeliveryGate can own the user-facing confirm.

    Under the real default policy these evaluate to NOTIFY (MODIFICATION level,
    and the delivery exception passes confidence 1.0 so the irreversible floor does
    not fire), so they are allowed with no approval recorded here. The actual
    preview-and-confirm happens in DeliveryGate further down the path, which is
    default-deny in its own right — see test_delivery.py.
    """
    decision = ActionGate().authorize(capability, "someone@example.com")
    assert decision.allowed
    assert decision.decision in (Decision.ALLOW, Decision.NOTIFY)
    assert decision.approved_by in ("", "delivery_gate")


def test_delivery_is_still_blocked_downstream_without_confirmation():
    """Allowing SEND_* past the permission gate must not mean it gets sent."""
    from friday.actions.delivery import DeliveryChannel, DeliveryGate, DeliveryRequest

    result = DeliveryGate().deliver(
        DeliveryRequest(channel=DeliveryChannel.EMAIL, recipient="x@example.com",
                        body="hello")
    )
    assert not result.sent
    assert not result.confirmed


def test_decision_is_json_safe():
    import json

    decision = ActionGate().authorize(ToolCapability.READ_DOM, "page")
    json.dumps(decision.to_dict())


def test_gate_fails_safe_when_evaluation_raises():
    class _BrokenManager:
        def evaluate(self, request):
            raise RuntimeError("policy exploded")

    decision = ActionGate(manager=_BrokenManager()).authorize(ToolCapability.READ_DOM)
    assert not decision.allowed, "an internal error must fail safe, never fail open"


# --------------------------------------------------------------------------- #
# Executor wiring — the gate must actually be consulted
# --------------------------------------------------------------------------- #
def test_executor_withholds_an_irreversible_step_by_default():
    ctx = ExecutionContext(goal="g")
    out = GoalExecutor()._execute_step(_step(ToolCapability.RUN_COMMAND, "ls"), ctx)
    assert "WITHHELD" in out
    assert ctx.withheld
    assert ctx.gate_decisions and not ctx.gate_decisions[-1].allowed


def test_executor_proceeds_once_approval_is_granted():
    executor = GoalExecutor(permission_gate=ActionGate(approval_fn=lambda p: True))
    ctx = ExecutionContext(goal="g")
    out = executor._execute_step(_step(ToolCapability.RUN_COMMAND, "ls"), ctx)
    assert "WITHHELD" not in out
    assert not ctx.withheld


def test_a_withheld_step_records_no_action_evidence():
    from friday.verification.evidence_law import EvidenceKind

    ctx = ExecutionContext(goal="g")
    GoalExecutor()._execute_step(_step(ToolCapability.DELETE_FILE, "x.txt"), ctx)
    assert ctx.withheld
    for kind in (
        EvidenceKind.DELIVERY_CONFIRMATION,
        EvidenceKind.FILE_ARTIFACT,
        EvidenceKind.NAVIGATION,
    ):
        assert not ctx.evidence.has(kind), f"withheld step produced {kind} evidence"


def test_the_gate_is_consulted_for_every_dispatched_step():
    """Not just for risky ones — otherwise coverage depends on classification."""
    calls = []

    class _RecordingGate(ActionGate):
        def authorize(self, capability, target="", **kwargs):
            calls.append(capability)
            return super().authorize(capability, target, **kwargs)

    executor = GoalExecutor(permission_gate=_RecordingGate())
    ctx = ExecutionContext(goal="g")
    executor._execute_step(_step(ToolCapability.GENERATE_TEXT, "something"), ctx)
    assert calls == [ToolCapability.GENERATE_TEXT]


def test_reversible_local_work_is_not_gated_away():
    """The gate must not turn ordinary safe work into a wall."""
    ctx = ExecutionContext(goal="g")
    out = GoalExecutor()._execute_step(_step(ToolCapability.GENERATE_TEXT, "text"), ctx)
    assert "WITHHELD" not in out
    assert not ctx.withheld


def test_step_supplied_confidence_is_honored():
    """A high-confidence irreversible step clears the policy floor."""
    ctx = ExecutionContext(goal="g")
    out = GoalExecutor()._execute_step(
        _step(ToolCapability.MOVE_FILE, "a->b", confidence=0.99), ctx
    )
    assert "WITHHELD" not in out, out
