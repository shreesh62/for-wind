import types

from automation.planner import AutomationPlanner
from automation.services import AutomationResponse


class DummyAutomation:
    def youtube_open_and_click_first(self):
        return AutomationResponse(success=False, message="YouTube action failed: network error")

    def open_website(self, target: str, browser=None):
        return AutomationResponse(success=False, message="Couldn't open site due to error")


def test_planner_recovery_message_youtube():
    planner = AutomationPlanner(automation=DummyAutomation(), awareness_state=None)
    out = planner.execute("open youtube and click first video")
    assert out and "retry" in out.lower()


def test_planner_recovery_message_open_site():
    planner = AutomationPlanner(automation=DummyAutomation(), awareness_state=None)
    out = planner.execute("open example.com")
    assert out and "retry" in out.lower()
