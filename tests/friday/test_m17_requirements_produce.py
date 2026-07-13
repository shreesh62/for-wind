"""Property + example tests for M17 — PRODUCE requirement emission.

Feature: m17-long-horizon-synthesis

Exercises `RequirementsDiscovery` (fallback path, `model_router=None`) and the
`_augment_structural` augmentation. No live network or model calls.

Properties covered: P5 (see design.md).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.planner.requirements import Requirement, RequirementsDiscovery
from friday.verification.evidence_law import classify_requirement, RequirementKind


BENCHMARK_GOAL = (
    "Complete a multi-stage goal: research a topic, then produce and save a "
    "document summarizing it with citations."
)

INJECTED_DESCRIPTION = "A written summary must be synthesized and composed"

SAFE_TOPICS = [
    "jazz", "volcanoes", "the ocean", "coffee beans", "black holes",
    "mountain ranges", "tigers", "the solar system", "bicycles", "ancient rome",
]
GATHER_PHRASES = ["research", "find information on", "search for", "look up"]
SAVE_PHRASES = [
    "save it to notes.txt", "save to a file", "save it as output.md",
    "put it in data.csv", "save to a .docx",
]
SYNTHESIS_VERBS = [
    "produce", "summarize", "summarizing", "document", "paper",
    "cite", "citation", "essay", "brief",
]

topics = st.sampled_from(SAFE_TOPICS)


def _has_produce(reqs) -> bool:
    return any(classify_requirement(r.description) == RequirementKind.PRODUCE for r in reqs)


# Goals that must yield a PRODUCE requirement: synthesis-verb goals OR gather+save goals.
synthesis_goals = st.builds(
    lambda v, t: f"{v} an overview of {t}",
    st.sampled_from(SYNTHESIS_VERBS), topics,
)
gather_save_goals = st.builds(
    lambda g, t, s: f"{g} {t}, then {s}",
    st.sampled_from(GATHER_PHRASES), topics, st.sampled_from(SAVE_PHRASES),
)
produce_goals = st.one_of(synthesis_goals, gather_save_goals)


# --------------------------------------------------------------------------
# Property 5: Requirements discovery emits a PRODUCE requirement
# --------------------------------------------------------------------------
# Feature: m17-long-horizon-synthesis, Property 5: Requirements discovery emits a PRODUCE requirement
@settings(max_examples=100)
@given(goal=produce_goals)
def test_p5_fallback_emits_produce_requirement(goal):
    """Validates: Requirements 3.1, 3.2"""
    discovery = RequirementsDiscovery(model_router=None)
    result = discovery.discover(goal)
    assert _has_produce(result.requirements), (
        f"no PRODUCE requirement on fallback path for {goal!r}: "
        f"{[r.description for r in result.requirements]}"
    )


# Feature: m17-long-horizon-synthesis, Property 5: Requirements discovery emits a PRODUCE requirement
@settings(max_examples=100)
@given(goal=produce_goals)
def test_p5_augment_structural_emits_produce_requirement(goal):
    """Validates: Requirements 3.1, 3.2"""
    discovery = RequirementsDiscovery(model_router=None)
    # A neutral base set that classifies GENERIC (no PRODUCE yet).
    base = [Requirement(description="An action must be taken")]
    augmented = discovery._augment_structural(goal, base)
    assert _has_produce(augmented), (
        f"no PRODUCE requirement after augmentation for {goal!r}: "
        f"{[r.description for r in augmented]}"
    )


# --------------------------------------------------------------------------
# Example tests — the exact benchmark goal
# --------------------------------------------------------------------------
def test_benchmark_goal_fallback_has_produce_requirement():
    """Validates: Requirements 3.1, 3.2"""
    discovery = RequirementsDiscovery(model_router=None)
    result = discovery.discover(BENCHMARK_GOAL)
    assert result.from_llm is False
    assert _has_produce(result.requirements), (
        f"benchmark goal produced no PRODUCE requirement: "
        f"{[r.description for r in result.requirements]}"
    )


def test_injected_description_classifies_produce_not_gather_file_deliver():
    """Validates: Requirements 3.1, 3.2 — token-order trap avoided."""
    kind = classify_requirement(INJECTED_DESCRIPTION)
    assert kind == RequirementKind.PRODUCE
    assert kind not in (
        RequirementKind.GATHER, RequirementKind.FILE, RequirementKind.DELIVER,
    )
