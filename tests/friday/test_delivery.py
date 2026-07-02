"""Tests for trusted delivery (M6) — personal-agent confirmation, NOT moderation.

Proves: nothing is sent without explicit confirmation OR autoconfirm; the user's
content is never judged/refused; success requires observed 'sent' evidence;
declines and unverified sends are reported honestly.
"""

from __future__ import annotations

import pytest

from friday.actions.delivery import (
    DeliveryChannel,
    DeliveryGate,
    DeliveryRequest,
    DeliveryResult,
)


def _req():
    return DeliveryRequest(
        channel=DeliveryChannel.EMAIL,
        recipient="boss@example.com",
        subject="Q3 report",
        body="Here is the report.",
        attachments=["report.docx"],
        app="gmail",
    )


class TestPreview:
    def test_preview_shows_exactly_what_will_send(self):
        p = _req().preview()
        assert "boss@example.com" in p
        assert "Q3 report" in p
        assert "report.docx" in p
        assert "Here is the report." in p


class TestNoAccidentalSend:
    def test_no_confirm_handler_and_no_autoconfirm_does_not_send(self):
        gate = DeliveryGate(send_fn=lambda r: True)  # send would succeed IF called
        result = gate.deliver(_req())
        assert result.sent is False
        assert "not confirmed" in result.reason.lower()

    def test_user_decline_does_not_send(self):
        sent = {"called": False}
        def _send(r):
            sent["called"] = True
            return True
        gate = DeliveryGate(confirm_fn=lambda preview: False, send_fn=_send)
        result = gate.deliver(_req())
        assert result.sent is False
        assert sent["called"] is False
        assert "declined" in result.reason.lower()


class TestConfirmedSend:
    def test_confirmed_and_verified_send_succeeds(self):
        gate = DeliveryGate(
            confirm_fn=lambda preview: True,
            send_fn=lambda r: True,
            verify_fn=lambda r: "Found in Sent folder",
        )
        result = gate.deliver(_req())
        assert result.sent is True
        assert result.confirmation_detail == "Found in Sent folder"

    def test_autoconfirm_skips_prompt(self, monkeypatch):
        monkeypatch.setenv("FRIDAY_AUTOCONFIRM", "1")
        gate = DeliveryGate(
            send_fn=lambda r: True,
            verify_fn=lambda r: "sent ok",
        )
        result = gate.deliver(_req())
        assert result.confirmed is True
        assert result.sent is True

    def test_per_call_auto_confirm(self):
        gate = DeliveryGate(send_fn=lambda r: True, verify_fn=lambda r: "ok")
        result = gate.deliver(_req(), auto_confirm=True)
        assert result.sent is True


class TestHonestVerification:
    def test_send_without_verification_marked_unverified(self):
        gate = DeliveryGate(confirm_fn=lambda p: True, send_fn=lambda r: True)
        result = gate.deliver(_req())
        assert result.sent is True
        assert "no independent verification" in result.confirmation_detail.lower()

    def test_send_issued_but_not_verified_is_not_success(self):
        gate = DeliveryGate(
            confirm_fn=lambda p: True,
            send_fn=lambda r: True,
            verify_fn=lambda r: "",  # could not confirm delivery
        )
        result = gate.deliver(_req())
        assert result.sent is False
        assert "not verified" in result.reason.lower()

    def test_send_handler_failure_reported(self):
        gate = DeliveryGate(confirm_fn=lambda p: True, send_fn=lambda r: False)
        result = gate.deliver(_req())
        assert result.sent is False
        assert "failure" in result.reason.lower()


class TestExecutorIntegration:
    def test_executor_gated_without_handler(self):
        from friday.executor import GoalExecutor, ExecutionContext
        from friday.tools.registry import ToolCapability
        ex = GoalExecutor(model_router=None, browser_controller=None)
        ctx = ExecutionContext(goal="email the report to boss")
        out = ex._execute_delivery(ToolCapability.SEND_EMAIL, "boss@example.com", ctx)
        assert "gated" in out.lower()

    def test_executor_records_delivery_evidence_on_success(self, monkeypatch):
        from friday.executor import GoalExecutor, ExecutionContext
        from friday.tools.registry import ToolCapability
        from friday.verification.evidence_law import EvidenceKind

        monkeypatch.setenv("FRIDAY_AUTOCONFIRM", "1")
        gate = DeliveryGate(send_fn=lambda r: True, verify_fn=lambda r: "Sent OK")
        ex = GoalExecutor(model_router=None, browser_controller=None, delivery_gate=gate)
        ctx = ExecutionContext(goal="email the report")
        ctx.generated_content = "report body"
        out = ex._execute_delivery(ToolCapability.SEND_EMAIL, "boss@example.com", ctx)
        assert "Delivered" in out
        # DELIVER requirement can now be satisfied by recorded evidence
        assert ctx.evidence.has(EvidenceKind.DELIVERY_CONFIRMATION)
