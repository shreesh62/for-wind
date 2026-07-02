"""Unit tests for Universal Action Layer primitive registry integration.

Feature: universal-action-layer (Task 11.2)

These tests verify that `register_primitives` wires the universal primitives
into the ToolRegistry correctly:
  - every universal primitive is registered and discoverable by capability
  - tool names use the "universal." prefix
  - handlers map to the correct primitive functions
  - universal primitives win over environment-specific tools (priority 10)
  - tool metadata (environment, priority, capability list) is correct
  - registration is idempotent (re-registering replaces, never duplicates)

This file is complementary to `test_primitives_properties.py`'s
`test_property_19_registry_discoverability` (which proves the handler/function
mapping). Here we focus on per-capability coverage, idempotency, metadata, and
priority precedence over the default registry tools.

SAFETY: No real I/O. register_primitives only stores function references; the
handlers are never invoked. FRIDAY_DRY_RUN=1 is enforced by the session
conftest.
"""

from __future__ import annotations

import pytest

from friday.actions.primitives import (
    click,
    navigate,
    observe,
    register_primitives,
    scroll,
    switch_window,
    type_text,
    verify,
)
from friday.tools.registry import (
    Tool,
    ToolCapability,
    ToolRegistry,
    build_default_registry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_registry() -> ToolRegistry:
    """A bare registry with only the universal primitives registered."""
    registry = ToolRegistry()
    register_primitives(registry)
    return registry


@pytest.fixture
def full_registry() -> ToolRegistry:
    """The default registry plus the universal primitives layered on top.

    This mirrors production wiring where environment-specific tools and the
    universal primitives coexist, so we can assert precedence ordering.
    """
    registry = build_default_registry()
    register_primitives(registry)
    return registry


# The complete set of universal primitives that register_primitives wires up.
# (capability, expected tool name, expected handler function)
EXPECTED_REGISTRATIONS = [
    (ToolCapability.CLICK_ELEMENT, "universal.click", click),
    (ToolCapability.TYPE_TEXT, "universal.type_text", type_text),
    (ToolCapability.SCROLL, "universal.scroll", scroll),
    (ToolCapability.SWITCH_WINDOW, "universal.switch_window", switch_window),
    (ToolCapability.VERIFY_RESULT, "universal.verify", verify),
    (ToolCapability.READ_SCREEN, "universal.observe", observe),
    (ToolCapability.NAVIGATE_URL, "universal.navigate", navigate),
]

UNIVERSAL_TOOL_NAMES = [name for _, name, _ in EXPECTED_REGISTRATIONS]


# ---------------------------------------------------------------------------
# Registration completeness
# ---------------------------------------------------------------------------

def test_register_primitives_registers_all_expected_tools(empty_registry):
    """Every expected universal tool is present after registration."""
    for name in UNIVERSAL_TOOL_NAMES:
        tool = empty_registry.find_by_name(name)
        assert tool is not None, f"expected tool '{name}' to be registered"


def test_register_primitives_registers_exactly_expected_count(empty_registry):
    """register_primitives adds exactly the expected universal tools and no
    extras into a fresh registry."""
    all_names = sorted(t.name for t in empty_registry.list_all())
    assert all_names == sorted(UNIVERSAL_TOOL_NAMES)


@pytest.mark.parametrize("name", UNIVERSAL_TOOL_NAMES)
def test_all_universal_tool_names_use_prefix(empty_registry, name):
    """All registered universal tools use the 'universal.' name prefix."""
    tool = empty_registry.find_by_name(name)
    assert tool is not None
    assert tool.name.startswith("universal.")


# ---------------------------------------------------------------------------
# Per-capability discoverability + handler mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "capability,expected_name,expected_handler",
    EXPECTED_REGISTRATIONS,
    ids=[name for _, name, _ in EXPECTED_REGISTRATIONS],
)
def test_capability_resolves_to_universal_primitive(
    empty_registry, capability, expected_name, expected_handler
):
    """find_tools(capability) returns the universal primitive whose handler is
    the matching primitive function."""
    tools = empty_registry.find_tools(capability)
    assert tools, f"no tool found for capability {capability}"

    names = [t.name for t in tools]
    assert expected_name in names, f"{expected_name} not among {names}"

    tool = empty_registry.find_by_name(expected_name)
    assert tool.handler is expected_handler
    assert capability in tool.capabilities


def test_find_tools_click_element_returns_universal_click(empty_registry):
    tools = empty_registry.find_tools(ToolCapability.CLICK_ELEMENT)
    assert tools[0].name == "universal.click"
    assert tools[0].handler is click


def test_find_tools_type_text_returns_universal_type_text(empty_registry):
    tools = empty_registry.find_tools(ToolCapability.TYPE_TEXT)
    assert tools[0].name == "universal.type_text"
    assert tools[0].handler is type_text


def test_find_tools_switch_window_returns_universal_switch_window(empty_registry):
    tools = empty_registry.find_tools(ToolCapability.SWITCH_WINDOW)
    assert tools[0].name == "universal.switch_window"
    assert tools[0].handler is switch_window


def test_find_tools_verify_result_returns_universal_verify(empty_registry):
    tools = empty_registry.find_tools(ToolCapability.VERIFY_RESULT)
    assert tools[0].name == "universal.verify"
    assert tools[0].handler is verify


# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", UNIVERSAL_TOOL_NAMES)
def test_universal_tools_are_environment_any(empty_registry, name):
    """Universal primitives declare environment 'any' so they resolve in any
    perceived environment."""
    tool = empty_registry.find_by_name(name)
    assert tool.environment == "any"


@pytest.mark.parametrize("name", UNIVERSAL_TOOL_NAMES)
def test_universal_tools_have_priority_ten(empty_registry, name):
    """Universal primitives use priority 10 so they are preferred over the
    environment-specific tools (priority <= 9)."""
    tool = empty_registry.find_by_name(name)
    assert tool.priority == 10


@pytest.mark.parametrize("name", UNIVERSAL_TOOL_NAMES)
def test_universal_tools_have_description_and_capabilities(empty_registry, name):
    """Each universal tool carries a non-empty description and at least one
    declared capability."""
    tool = empty_registry.find_by_name(name)
    assert tool.description
    assert len(tool.capabilities) >= 1


@pytest.mark.parametrize("name", UNIVERSAL_TOOL_NAMES)
def test_universal_tool_handlers_are_callable(empty_registry, name):
    """Every registered universal tool exposes a callable handler."""
    tool = empty_registry.find_by_name(name)
    assert callable(tool.handler)


# ---------------------------------------------------------------------------
# Priority precedence over environment-specific tools
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "capability,expected_name",
    [
        (ToolCapability.CLICK_ELEMENT, "universal.click"),
        (ToolCapability.TYPE_TEXT, "universal.type_text"),
        (ToolCapability.SWITCH_WINDOW, "universal.switch_window"),
        (ToolCapability.NAVIGATE_URL, "universal.navigate"),
    ],
)
def test_universal_primitive_outranks_environment_tools(
    full_registry, capability, expected_name
):
    """When universal primitives coexist with environment-specific tools, the
    universal primitive is returned first (highest priority)."""
    tools = full_registry.find_tools(capability)
    assert tools, f"no tool found for {capability}"
    assert tools[0].name == expected_name
    # And there is genuinely a competing environment-specific tool present.
    assert len(tools) > 1


def test_environment_specific_tools_still_present(full_registry):
    """Layering universal primitives does not remove the environment-specific
    tools; both remain discoverable for the same capability."""
    click_tools = {t.name for t in full_registry.find_tools(ToolCapability.CLICK_ELEMENT)}
    assert "universal.click" in click_tools
    assert "browser.click" in click_tools
    assert "desktop.click" in click_tools


def test_find_tools_results_sorted_by_priority_descending(full_registry):
    """find_tools returns tools ordered by priority, highest first."""
    tools = full_registry.find_tools(ToolCapability.CLICK_ELEMENT)
    priorities = [t.priority for t in tools]
    assert priorities == sorted(priorities, reverse=True)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_register_primitives_is_idempotent(empty_registry):
    """Re-registering the primitives replaces entries in place rather than
    creating duplicates (registry keys by tool name)."""
    count_before = empty_registry.tool_count
    register_primitives(empty_registry)
    register_primitives(empty_registry)
    assert empty_registry.tool_count == count_before


def test_idempotent_registration_preserves_handler_mapping(empty_registry):
    """After repeated registration, handlers still map to the correct
    primitive functions."""
    register_primitives(empty_registry)
    for _, name, handler in EXPECTED_REGISTRATIONS:
        tool = empty_registry.find_by_name(name)
        assert tool.handler is handler


def test_capability_query_returns_single_universal_after_reregister(empty_registry):
    """Re-registering does not produce duplicate universal tools for a
    capability."""
    register_primitives(empty_registry)
    click_universal = [
        t for t in empty_registry.find_tools(ToolCapability.CLICK_ELEMENT)
        if t.name == "universal.click"
    ]
    assert len(click_universal) == 1


# ---------------------------------------------------------------------------
# list_capabilities mapping
# ---------------------------------------------------------------------------

def test_list_capabilities_maps_universal_tools(empty_registry):
    """list_capabilities reflects each universal tool under its capability."""
    cap_map = empty_registry.list_capabilities()
    assert "universal.click" in cap_map[ToolCapability.CLICK_ELEMENT.value]
    assert "universal.type_text" in cap_map[ToolCapability.TYPE_TEXT.value]
    assert "universal.switch_window" in cap_map[ToolCapability.SWITCH_WINDOW.value]
    assert "universal.verify" in cap_map[ToolCapability.VERIFY_RESULT.value]


def test_register_into_provided_registry_instance():
    """register_primitives mutates the registry passed to it and returns None."""
    registry = ToolRegistry()
    result = register_primitives(registry)
    assert result is None
    assert registry.tool_count == len(EXPECTED_REGISTRATIONS)
