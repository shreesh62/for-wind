"""Gmail email sending plugin using Playwright automation."""

from __future__ import annotations

from core.capability_dispatcher import DispatchContext
from automation.gmail_actions import GmailAutomation
from core.intent_parser import parse_email_intent


def handle_gmail_send(context: DispatchContext, capability: dict) -> str:
    intent = parse_email_intent(context.command)
    if not intent:
        return (
            "Please specify recipient and subject clearly, e.g. "
            "'send email to example@example.com about meeting body let's meet tomorrow'."
        )
    automation = GmailAutomation(headless=True)
    result = automation.send_email(intent.recipient, intent.subject, intent.body)
    return result.message
