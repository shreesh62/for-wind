"""Utility functions for extracting structured intents from natural language."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class EmailIntent:
    recipient: str
    subject: str
    body: str


_EMAIL_RECIPIENT_RE = re.compile(r"send (?:an? )?email to ([^,]+?)(?: about | regarding | with subject |$)", re.IGNORECASE)
_EMAIL_SUBJECT_RE = re.compile(r"(?:about|regarding|subject(?: is)?|with subject) ([^,]+?)(?: body | message | and |$)", re.IGNORECASE)
_EMAIL_BODY_RE = re.compile(r"(?:body|message|say|with message) (.+)$", re.IGNORECASE)


def parse_email_intent(text: str) -> Optional[EmailIntent]:
    """Extract recipient, subject, and body from an email command."""

    lowered = text.strip()
    if not lowered:
        return None

    recipient_match = _EMAIL_RECIPIENT_RE.search(lowered)
    subject_match = _EMAIL_SUBJECT_RE.search(lowered)
    body_match = _EMAIL_BODY_RE.search(lowered)

    if not recipient_match or not subject_match:
        return None

    recipient = recipient_match.group(1).strip().strip("'\" ")
    subject = subject_match.group(1).strip().strip("'\" ")
    body = body_match.group(1).strip().strip("'\" ") if body_match else "Sent via Jarvis automation."

    if not recipient or not subject:
        return None

    return EmailIntent(recipient=recipient, subject=subject, body=body)
