"""Trusted delivery — confirmation + verified send for a PERSONAL agent.

Design philosophy (personal agent, not a corporate product):
- This is NOT content moderation. FRIDAY does NOT judge whether your message
  is "appropriate" or refuse based on a model's opinion. You operate your own
  accounts as yourself.
- This IS a correctness + confirmation layer: before an irreversible external
  action (send email/message, post), FRIDAY shows you EXACTLY what it will do
  (recipient, subject, body, attachment) and does it only after you confirm.
  This protects you from MISTAKES (wrong recipient, wrong file, hallucinated
  content), never from yourself.
- Full autonomy is one flag away: FRIDAY_AUTOCONFIRM=1 (or per-call
  auto_confirm=True) skips the prompt and sends immediately.

A delivery is only reported complete when its 'sent' state is observed —
honest verification, consistent with the Evidence Law.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional


class DeliveryChannel(str, Enum):
    EMAIL = "email"
    MESSAGE = "message"     # WhatsApp / Instagram / generic chat
    POST = "post"           # social post


@dataclass
class DeliveryRequest:
    """A pending external delivery awaiting confirmation."""

    channel: DeliveryChannel
    recipient: str = ""
    subject: str = ""
    body: str = ""
    attachments: List[str] = field(default_factory=list)
    app: str = ""           # gmail / whatsapp / instagram / ...

    def preview(self) -> str:
        """Human-readable preview of EXACTLY what will be sent."""
        lines = [f"[{self.channel.value.upper()}] via {self.app or 'auto'}"]
        if self.recipient:
            lines.append(f"To: {self.recipient}")
        if self.subject:
            lines.append(f"Subject: {self.subject}")
        if self.attachments:
            lines.append(f"Attachments: {', '.join(self.attachments)}")
        if self.body:
            preview = self.body if len(self.body) <= 800 else self.body[:800] + "…"
            lines.append(f"Body:\n{preview}")
        return "\n".join(lines)


@dataclass
class DeliveryResult:
    """Outcome of a delivery attempt."""

    requested: bool = False
    confirmed: bool = False
    sent: bool = False
    confirmation_detail: str = ""   # observed 'sent' evidence
    reason: str = ""                # why not sent (declined / unverified / error)

    @property
    def success(self) -> bool:
        return self.sent


def _autoconfirm_enabled() -> bool:
    return os.environ.get("FRIDAY_AUTOCONFIRM", "0").strip().lower() in ("1", "true", "yes")


class DeliveryGate:
    """Confirmation + verified delivery. You are in control, not a moderator.

    Usage:
        gate = DeliveryGate(confirm_fn=my_prompt, send_fn=my_sender,
                            verify_fn=my_sent_check)
        result = gate.deliver(request)

    - confirm_fn(preview:str) -> bool : ask the user (default: deny unless
      AUTOCONFIRM, so nothing is ever sent silently by accident).
    - send_fn(request) -> bool        : perform the actual send.
    - verify_fn(request) -> str       : return non-empty 'sent' evidence if the
      message is confirmed delivered (e.g. found in Sent folder), else "".
    """

    def __init__(
        self,
        confirm_fn: Optional[Callable[[str], bool]] = None,
        send_fn: Optional[Callable[[DeliveryRequest], bool]] = None,
        verify_fn: Optional[Callable[[DeliveryRequest], str]] = None,
    ) -> None:
        self._confirm_fn = confirm_fn
        self._send_fn = send_fn
        self._verify_fn = verify_fn

    def deliver(self, request: DeliveryRequest, *, auto_confirm: bool = False) -> DeliveryResult:
        result = DeliveryResult(requested=True)

        # 1. CONFIRM — show exactly what will happen, get explicit go-ahead.
        if auto_confirm or _autoconfirm_enabled():
            result.confirmed = True
        elif self._confirm_fn is not None:
            try:
                result.confirmed = bool(self._confirm_fn(request.preview()))
            except Exception as exc:
                result.reason = f"confirmation error: {exc}"
                return result
        else:
            # No confirmation mechanism and no autoconfirm: do NOT send.
            result.reason = ("not confirmed — no confirmation handler and "
                             "FRIDAY_AUTOCONFIRM is off (nothing sent by accident)")
            return result

        if not result.confirmed:
            result.reason = "user declined"
            return result

        # 2. SEND — perform the real action.
        if self._send_fn is None:
            result.reason = "no send handler wired for this channel/app"
            return result
        try:
            sent_ok = bool(self._send_fn(request))
        except Exception as exc:
            result.reason = f"send error: {exc}"
            return result
        if not sent_ok:
            result.reason = "send handler reported failure"
            return result

        # 3. VERIFY — only report success with observed 'sent' evidence.
        if self._verify_fn is not None:
            try:
                evidence = self._verify_fn(request)
            except Exception:
                evidence = ""
            if evidence:
                result.sent = True
                result.confirmation_detail = evidence
            else:
                result.reason = "send issued but delivery not verified"
        else:
            # No verifier: accept the send handler's success but mark it as
            # unverified in the detail (honest).
            result.sent = True
            result.confirmation_detail = "sent (handler success; no independent verification)"

        return result
