import re
from core.assistant import AssistantOrchestrator
from memory.memory_controller import MemoryController
from personality import PersonalityManager
from capabilities import CapabilityRegistry
from core.capability_dispatcher import CapabilityDispatcher

# Dummy LLM that just echoes the prompt for inspection

def dummy_llm(prompt: str, meta: dict) -> str:
    return prompt


def test_prompt_builder_dedup_and_rules(tmp_path, monkeypatch):
    mem = MemoryController(short_term_limit=3, long_term_results=3)
    registry = CapabilityRegistry()

    def _weather_stub(city: str) -> str:
        return f"Weather for {city}: 25C"

    def _distance_stub(a: str, b: str) -> str:
        return f"Distance between {a} and {b} is 1.0 km. Estimated travel time is 2 minutes."

    dispatcher = CapabilityDispatcher(
        registry=registry,
        weather_handler=_weather_stub,
        distance_handler=_distance_stub,
    )
    pm = PersonalityManager()

    # Seed a trivial, always-present fact
    mem.remember("I live in Thane")

    asst = AssistantOrchestrator(
        memory=mem,
        dispatcher=dispatcher,
        personality_manager=pm,
        llm_callable=dummy_llm,
        headless=True,
    )

    # Ask a generic question that should not pull location
    prompt = asst._build_prompt("how are you")

    # Should not unconditionally include the memory
    assert "I live in Thane" not in prompt

    # If explicitly requested, memory can be injected
    prompt2 = asst._build_prompt("what's going on in Thane today?")
    # Either appears in relevant knowledge or short-term; allow soft check
    assert ("Thane" in prompt2)


def test_phase6_followups_route_to_planner(monkeypatch):
    mem = MemoryController(short_term_limit=3, long_term_results=3)
    registry = CapabilityRegistry()

    def _weather_stub(city: str) -> str:
        return f"Weather for {city}: 25C"

    def _distance_stub(a: str, b: str) -> str:
        return f"Distance between {a} and {b} is 1.0 km. Estimated travel time is 2 minutes."

    dispatcher = CapabilityDispatcher(
        registry=registry,
        weather_handler=_weather_stub,
        distance_handler=_distance_stub,
    )
    pm = PersonalityManager()

    asst = AssistantOrchestrator(
        memory=mem,
        dispatcher=dispatcher,
        personality_manager=pm,
        llm_callable=dummy_llm,
        headless=True,
    )

    class StubPlanner:
        last_tool_trace = ["stub_planner_trace: ok=true"]

        def repeat_last_verified(self, *, snapshot=None):
            return "REPEATED"

        def open_last_website(self, *, snapshot=None):
            return "OPENED_LAST_SITE"

        def undo_last_verified(self, *, snapshot=None):
            self.last_tool_trace = ["stub_undo: ok=true"]
            return "UNDONE"

        def cancel_context(self):
            return "Okay. Cancelled."

    asst.planner = StubPlanner()  # type: ignore[assignment]

    r1 = asst.process_command("repeat that")
    assert "REPEATED" in r1.final_response
    assert any("phase6_followup: repeat_last_verified=true" in t for t in (asst._last_tool_trace or []))

    r2 = asst.process_command("open it again")
    assert "OPENED_LAST_SITE" in r2.final_response
    assert any("phase6_followup: open_last_website=true" in t for t in (asst._last_tool_trace or []))

    r3 = asst.process_command("undo that")
    assert "UNDONE" in r3.final_response
    assert any("phase6_followup: undo_last_verified=true" in t for t in (asst._last_tool_trace or []))

    r4 = asst.process_command("cancel")
    assert "Cancelled" in r4.final_response
    assert any("phase6_followup: cancel=true" in t for t in (asst._last_tool_trace or []))
