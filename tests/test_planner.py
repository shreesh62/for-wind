from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from automation.planner import AutomationPlanner


@dataclass
class StubAutomationResult:
    success: bool
    message: str
    verification: dict = field(default_factory=lambda: {"ok": True, "method": "stub", "reason": "test stub"})


class StubAutomationServices:
    def __init__(self) -> None:
        self.amazon_calls: list[str] = []
        self.whatsapp_calls: list[tuple[str, str]] = []
        self.screenshot_calls: int = 0
        self.focus_calls: list[tuple[str | None, str | None]] = []
        self.type_calls: list[str] = []
        self.browser_summary_calls: int = 0
        self.website_calls: list[tuple[str, str | None]] = []
        self.scroll_calls: list[int] = []
        self.hotkey_calls: list[tuple[str, ...]] = []

    def search_amazon(self, query: str) -> StubAutomationResult:  # type: ignore[override]
        self.amazon_calls.append(query)
        return StubAutomationResult(True, f"Searching Amazon for: {query}")

    def send_whatsapp(self, contact: str, message: str) -> StubAutomationResult:  # type: ignore[override]
        self.whatsapp_calls.append((contact, message))
        return StubAutomationResult(True, f"WhatsApp message sent to {contact}: {message}")

    def take_screenshot(self) -> StubAutomationResult:  # type: ignore[override]
        self.screenshot_calls += 1
        return StubAutomationResult(True, "Captured a screenshot.")

    def focus_window(self, *, title: str | None = None, exe: str | None = None) -> StubAutomationResult:  # type: ignore[override]
        self.focus_calls.append((title, exe))
        target = title or exe or "unknown"
        return StubAutomationResult(True, f"Focused window: {target}")

    def type_text(self, text: str, *, interval: float = 0.0) -> StubAutomationResult:  # type: ignore[override]
        self.type_calls.append(text)
        return StubAutomationResult(True, f"Typed: {text}")

    def describe_active_tab(self, *, include_dom: bool = False) -> StubAutomationResult:  # type: ignore[override]
        self.browser_summary_calls += 1
        return StubAutomationResult(True, "Active tab is example.com")

    def open_website(self, target: str, browser=None):  # type: ignore[override]
        b = browser if isinstance(browser, str) or browser is None else str(browser)
        self.website_calls.append((target, b))
        return StubAutomationResult(True, f"Opened {target}")

    def scroll(self, amount: int):  # type: ignore[override]
        self.scroll_calls.append(int(amount))
        return StubAutomationResult(True, f"Scrolled {amount}")

    def press_hotkey(self, *keys: str):  # type: ignore[override]
        tup = tuple(str(k) for k in keys)
        self.hotkey_calls.append(tup)
        return StubAutomationResult(True, f"Pressed hotkey: {'+'.join(tup)}")


class StubStateCache:
    def __init__(self, title: str | None = None, app: str | None = None) -> None:
        self._title = title
        self._app = app

    def get_window(self):
        if self._title is None and self._app is None:
            return None
        return type(
            "WindowContext",
            (),
            {
                "title": self._title,
                "app_exe": self._app,
                "elements": [],
            },
        )()


@pytest.fixture()
def automation_services() -> StubAutomationServices:
    return StubAutomationServices()


def test_amazon_command_routes_to_search(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    response = planner.execute("search gaming mouse on Amazon")

    assert automation_services.amazon_calls == ["search gaming mouse on Amazon"]
    assert response == "Searching Amazon for: search gaming mouse on Amazon"


def test_whatsapp_command_requires_contact_and_message(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    response = planner.execute("send whatsapp message")

    assert response == "Please specify who to message and what to say on WhatsApp."
    assert automation_services.whatsapp_calls == []


def test_whatsapp_command_parses_contact_and_message(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    response = planner.execute("send a WhatsApp message to Riya saying I'm on my way")

    assert automation_services.whatsapp_calls == [("Riya", "I'm on my way")]
    assert response == "WhatsApp message sent to Riya: I'm on my way"


def test_screen_description_uses_awareness_state(automation_services: StubAutomationServices) -> None:
    state = StubStateCache(title="Amazon.in", app="chrome.exe")
    planner = AutomationPlanner(automation_services, awareness_state=state)

    response = planner.execute("what's on screen right now")

    assert "Amazon.in" in response
    assert "chrome.exe" in response


def test_take_screenshot_command(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    response = planner.execute("please take a screenshot")

    assert response == "Captured a screenshot."
    assert automation_services.screenshot_calls == 1


def test_focus_window_command(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    response = planner.execute("focus the chrome window")

    assert response == "Focused window: chrome"
    assert automation_services.focus_calls == [("chrome", None)]


def test_focus_window_without_target_prompts_user(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    response = planner.execute("focus the window")

    assert response == "Please tell me which window to focus."
    assert automation_services.focus_calls == []


def test_type_text_command(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    response = planner.execute("type 'Hello there'")

    assert response == "Typed: Hello there"
    assert automation_services.type_calls == ["Hello there"]


def test_browser_summary_command(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    response = planner.execute("summarize the browser tab")

    assert response == "Active tab is example.com"
    assert automation_services.browser_summary_calls == 1


def test_repeat_last_verified_replays_command(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    first = planner.execute("type hello")
    again = planner.repeat_last_verified()

    assert first == "Typed: hello"
    assert again == "Typed: hello"
    assert automation_services.type_calls == ["hello", "hello"]


def test_open_last_website_replays_verified_site(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    opened = planner.execute("open github")
    again = planner.open_last_website()

    assert opened == "Opened github"
    assert again == "Opened github"
    assert automation_services.website_calls == [("github", None), ("github", None)]


def test_undo_scroll_reverses_direction(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    out = planner.execute("scroll down 300")
    undo = planner.undo_last_verified()

    assert out == "Scrolled -300"
    assert undo == "Scrolled 300"
    assert automation_services.scroll_calls == [-300, 300]


def test_undo_type_text_uses_ctrl_z(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    out = planner.execute("type hello")
    undo = planner.undo_last_verified()

    assert out == "Typed: hello"
    assert undo and "Pressed hotkey" in undo
    assert automation_services.hotkey_calls == [("ctrl", "z")]


def test_cancel_stops_chained_commands(automation_services: StubAutomationServices) -> None:
    planner = AutomationPlanner(automation_services)

    out = planner.execute("scroll down 300 then cancel then scroll down 300")

    assert out == "Okay. Cancelled."
    assert automation_services.scroll_calls == [-300]
