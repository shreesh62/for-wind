"""Calendar scheduling plugin leveraging automation services."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from core.capability_dispatcher import DispatchContext
from automation.services import AutomationServices


def _parse_event_details(command: str) -> tuple[str, Optional[str], Optional[str]]:
    command_lower = command.lower()
    title = "Meeting"
    date_text: Optional[str] = None
    start_time: Optional[str] = None

    if "on " in command_lower:
        try:
            date_fragment = command_lower.split("on ", 1)[1].split()[0]
            datetime.strptime(date_fragment, "%m/%d/%Y")
            date_text = date_fragment
        except Exception:
            pass

    if "tomorrow" in command_lower and not date_text:
        date_text = (datetime.now() + timedelta(days=1)).strftime("%m/%d/%Y")
    elif "today" in command_lower and not date_text:
        date_text = datetime.now().strftime("%m/%d/%Y")

    if " at " in command_lower:
        segment = command_lower.split(" at ", 1)[1].split()[0]
        start_time = segment

    if " called " in command_lower:
        title = command.split(" called ", 1)[1].strip()
    elif " titled " in command_lower:
        title = command.split(" titled ", 1)[1].strip()
    elif " named " in command_lower:
        title = command.split(" named ", 1)[1].strip()
    else:
        words = command.split()
        if len(words) > 3:
            title = " ".join(words[-4:])

    return title.title(), date_text, start_time


def handle_calendar_create_event(context: DispatchContext, capability: dict) -> str:
    title, date_text, start_time = _parse_event_details(context.command)
    automation = AutomationServices(headless=True)
    result = automation.create_calendar_event(title, date_text, start_time)
    return result.message
