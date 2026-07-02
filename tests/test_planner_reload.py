from automation.planner import AutomationPlanner
from automation.services import AutomationResponse


class DummyAutomation:
    def reload_active_tab(self):
        return AutomationResponse(success=True, message="Reloaded the active tab.")


def test_planner_handles_reload_phrase_variants():
    planner = AutomationPlanner(automation=DummyAutomation(), awareness_state=None)
    for cmd in [
        "reload",
        "reload page",
        "refresh tab",
        "refresh the browser",
        "reload site",
    ]:
        out = planner.execute(cmd)
        assert out and "reloaded" in out.lower()
