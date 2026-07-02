from capabilities import CapabilityRegistry
from core.capability_dispatcher import CapabilityDispatcher
from core.assistant import AssistantOrchestrator
from memory.memory_controller import MemoryController
from personality import PersonalityManager


def _weather_stub(city: str) -> str:
    return f"Weather for {city}: 25C"


def _distance_stub(a: str, b: str) -> str:
    return f"Distance between {a} and {b} is 1.0 km. Estimated travel time is 2 minutes."


def _llm(prompt: str, meta: dict) -> str:
    return "LLM fallback"


def build_assistant():
    registry = CapabilityRegistry()
    dispatcher = CapabilityDispatcher(
        registry=registry,
        weather_handler=_weather_stub,
        distance_handler=_distance_stub,
    )
    mem = MemoryController(short_term_limit=4, long_term_results=3)
    pm = PersonalityManager()
    return AssistantOrchestrator(
        memory=mem,
        dispatcher=dispatcher,
        personality_manager=pm,
        llm_callable=_llm,
        headless=True,
    )


def test_planned_capability_declines_cleanly():
    asst = build_assistant()
    # This should match the 'open_browser' planned capability
    result = asst.process_command("open a browser website")
    assert "isn’t enabled yet" in result.final_response or "isn't enabled yet" in result.final_response
    assert result.handled is False


def test_available_capability_proceeds():
    asst = build_assistant()
    result = asst.process_command("what's the weather in Thane")
    assert "Weather for Thane" in result.final_response
