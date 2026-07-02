from capabilities import CapabilityRegistry


def test_priority_reload_vs_generic_navigate():
    reg = CapabilityRegistry()
    # Reload should not be captured by generic web_navigate; planner handles it
    key, _ = reg.match_intent("reload page")
    # Should not match web_navigate; fallback to None or qa_general
    assert key != "web_navigate"


def test_priority_app_launch_vs_generic_navigate():
    reg = CapabilityRegistry()
    key, _ = reg.match_intent("open spotify")
    # Should prefer app_launch over generic web_navigate
    assert key == "app_launch"


def test_priority_browser_summary_vs_qa():
    reg = CapabilityRegistry()
    key, _ = reg.match_intent("what is on the browser tab")
    # Should match browser_summarize, not qa_general
    assert key == "browser_summarize"


def test_priority_weather_vs_qa():
    reg = CapabilityRegistry()
    key, _ = reg.match_intent("what is the weather in Tokyo")
    # Should match weather_check, not qa_general
    assert key == "weather_check"


def test_priority_screenshot_vs_qa():
    reg = CapabilityRegistry()
    key, _ = reg.match_intent("take a screenshot")
    # Should match desktop_screenshot, not qa_general
    assert key == "desktop_screenshot"
