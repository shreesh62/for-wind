"""Property + example tests for M17 — Long-Horizon Synthesis (planner).

Feature: m17-long-horizon-synthesis

These tests exercise the deterministic fallback planner
`OperatorPlanner._generic_capabilities` (LLM-unavailable path, `model_router=None`).
No live network or model calls are made; the planner is a pure function of goal
text + inferred capabilities.

Properties covered: P1, P2, P3, P4, P7, P8 (see design.md).
"""

from __future__ import annotations

from typing import List

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.planner.operator_planner import OperatorPlanner
from friday.tools.registry import build_default_registry, ToolCapability


GATHER_CAPS = (ToolCapability.SEARCH_WEB, ToolCapability.EXTRACT_WEB_CONTENT)


def _caps(goal_text: str) -> List[ToolCapability]:
    """Run the deterministic fallback planner and return its capability list."""
    planner = OperatorPlanner(registry=build_default_registry(), model_router=None)
    goal = planner._parser.parse(goal_text)
    return [c[0] for c in planner._generic_capabilities(goal, goal_text)]


# --------------------------------------------------------------------------
# Strategy building blocks — curated so tokens never accidentally collide
# with a planner keyword we are not testing.
# --------------------------------------------------------------------------

# Safe topics: contain NO planner keyword (gather / content / file / nav / send).
SAFE_TOPICS = [
    "jazz", "volcanoes", "the ocean", "coffee beans", "black holes",
    "mountain ranges", "tigers", "the solar system", "bicycles", "ancient rome",
]

# Gather phrases: trigger needs_info only.
GATHER_PHRASES = ["research", "find information on", "search for", "look up"]

# Save phrases: trigger needs_file only (NO content / gather keyword).
SAVE_PHRASES = [
    "save it to notes.txt", "save to a file", "save it as output.md",
    "put it in data.csv", "save to a .docx", "store it in excel",
]

# Synthesis verbs/nouns (M17 additions). Word forms carry the stem.
SYNTHESIS_VERBS = [
    "produce", "summarize", "summarizing", "document", "paper",
    "cite", "citation", "essay", "brief",
]

# Legacy content keywords (Requirement 2.2).
LEGACY_CONTENT = [
    "write", "create", "generate", "summary", "report", "compose", "draft",
    "spreadsheet", "table", "list", "compare", "comparison",
]

topics = st.sampled_from(SAFE_TOPICS)
gather_phrases = st.sampled_from(GATHER_PHRASES)
save_phrases = st.sampled_from(SAVE_PHRASES)
synthesis_verbs = st.sampled_from(SYNTHESIS_VERBS)
legacy_content = st.sampled_from(LEGACY_CONTENT)


# --------------------------------------------------------------------------
# Property 1: Gather + save forces an ordered synthesis step
# --------------------------------------------------------------------------
# Feature: m17-long-horizon-synthesis, Property 1: Gather + save forces an ordered synthesis step
@settings(max_examples=100)
@given(gather=gather_phrases, topic=topics, save=save_phrases)
def test_p1_gather_plus_save_forces_ordered_synthesis(gather, topic, save):
    """Validates: Requirements 1.1, 1.2"""
    goal = f"{gather} {topic}, then {save}"
    caps = _caps(goal)

    assert ToolCapability.GENERATE_TEXT in caps, f"no synthesis step for {goal!r}: {caps}"
    assert ToolCapability.CREATE_FILE in caps
    assert any(c in caps for c in GATHER_CAPS)

    gen_idx = caps.index(ToolCapability.GENERATE_TEXT)
    last_gather_idx = max(i for i, c in enumerate(caps) if c in GATHER_CAPS)
    first_file_idx = caps.index(ToolCapability.CREATE_FILE)

    assert gen_idx > last_gather_idx, f"synthesis not after gather: {caps}"
    assert gen_idx < first_file_idx, f"synthesis not before save: {caps}"


# --------------------------------------------------------------------------
# Property 2: Synthesis verbs classify as needing content
# --------------------------------------------------------------------------
# Feature: m17-long-horizon-synthesis, Property 2: Synthesis verbs classify as needing content
@settings(max_examples=100)
@given(verb=synthesis_verbs, topic=topics)
def test_p2_synthesis_verbs_need_content(verb, topic):
    """Validates: Requirements 2.1"""
    goal = f"{verb} an overview of {topic}"
    caps = _caps(goal)
    assert ToolCapability.GENERATE_TEXT in caps, f"no synthesis step for {goal!r}: {caps}"


# --------------------------------------------------------------------------
# Property 3: Legacy content keywords still classify as needing content
# --------------------------------------------------------------------------
# Feature: m17-long-horizon-synthesis, Property 3: Legacy content keywords still classify as needing content
@settings(max_examples=100)
@given(kw=legacy_content, topic=topics)
def test_p3_legacy_content_keywords_need_content(kw, topic):
    """Validates: Requirements 2.2"""
    goal = f"{kw} an overview of {topic}"
    caps = _caps(goal)
    assert ToolCapability.GENERATE_TEXT in caps, f"no synthesis step for {goal!r}: {caps}"


# --------------------------------------------------------------------------
# Property 4: No spurious synthesis without triggers
# --------------------------------------------------------------------------
def _pure_gather(gather, topic):
    return f"{gather} {topic}"


def _pure_file(topic, save):
    return f"save {topic} to notes.txt"


def _neutral(topic):
    return topic


no_synthesis_goals = st.one_of(
    st.builds(_pure_gather, gather_phrases, topics),
    st.builds(_pure_file, topics, save_phrases),
    st.builds(_neutral, topics),
)


# Feature: m17-long-horizon-synthesis, Property 4: No spurious synthesis without triggers
@settings(max_examples=100)
@given(goal=no_synthesis_goals)
def test_p4_no_spurious_synthesis(goal):
    """Validates: Requirements 1.3, 1.4, 2.3"""
    caps = _caps(goal)
    assert ToolCapability.GENERATE_TEXT not in caps, f"spurious synthesis for {goal!r}: {caps}"


# --------------------------------------------------------------------------
# Property 7: Planning decision is deterministic and pure
# --------------------------------------------------------------------------
any_goal = st.one_of(
    st.builds(lambda g, t, s: f"{g} {t}, then {s}", gather_phrases, topics, save_phrases),
    st.builds(lambda v, t: f"{v} an overview of {t}", synthesis_verbs, topics),
    st.builds(lambda k, t: f"{k} an overview of {t}", legacy_content, topics),
    no_synthesis_goals,
)


# Feature: m17-long-horizon-synthesis, Property 7: Planning decision is deterministic and pure
@settings(max_examples=100)
@given(goal=any_goal)
def test_p7_deterministic_and_pure(goal):
    """Validates: Requirements 6.1, 6.4"""
    first = _caps(goal)
    second = _caps(goal)
    assert first == second, f"non-deterministic caps for {goal!r}: {first} != {second}"


# --------------------------------------------------------------------------
# Property 8: No regression on representative plan shapes
# --------------------------------------------------------------------------
# Feature: m17-long-horizon-synthesis, Property 8: No regression on representative plan shapes
def test_p8_pure_research_is_gather_only():
    """Validates: Requirements 5.4, 5.5"""
    caps = _caps("research the history of jazz")
    assert any(c in caps for c in GATHER_CAPS)
    assert ToolCapability.GENERATE_TEXT not in caps
    assert ToolCapability.CREATE_FILE not in caps


def test_p8_pure_file_is_create_file_only():
    """Validates: Requirements 5.4, 5.5"""
    caps = _caps("save my notes to notes.txt")
    assert ToolCapability.CREATE_FILE in caps
    assert ToolCapability.GENERATE_TEXT not in caps
    assert ToolCapability.SEARCH_WEB not in caps


def test_p8_research_plus_report_includes_synthesis():
    """Validates: Requirements 5.4, 5.5"""
    caps = _caps("research laptops and write a report")
    assert any(c in caps for c in GATHER_CAPS)
    assert ToolCapability.GENERATE_TEXT in caps


def test_p8_gather_save_document_includes_ordered_synthesis():
    """Validates: Requirements 5.4, 5.5"""
    caps = _caps("research a topic and save a document summarizing it with citations")
    assert ToolCapability.GENERATE_TEXT in caps
    gen_idx = caps.index(ToolCapability.GENERATE_TEXT)
    last_gather_idx = max(i for i, c in enumerate(caps) if c in GATHER_CAPS)
    first_file_idx = caps.index(ToolCapability.CREATE_FILE)
    assert last_gather_idx < gen_idx < first_file_idx
