"""Tests for friday.tools — capability-based tool registry."""

import pytest

from friday.tools.registry import (
    Tool,
    ToolCapability,
    ToolRegistry,
    build_default_registry,
)


class TestToolRegistry:
    """Test environment-agnostic capability registry."""

    def test_register_and_find(self):
        registry = ToolRegistry()
        registry.register(Tool(
            name="test_tool",
            description="A test tool",
            capabilities=[ToolCapability.NAVIGATE_URL],
        ))

        results = registry.find_tools(ToolCapability.NAVIGATE_URL)
        assert len(results) == 1
        assert results[0].name == "test_tool"

    def test_find_returns_empty_for_unregistered(self):
        registry = ToolRegistry()
        assert registry.find_tools(ToolCapability.SEND_EMAIL) == []

    def test_priority_ordering(self):
        registry = ToolRegistry()
        registry.register(Tool(
            name="low_priority", description="",
            capabilities=[ToolCapability.CLICK_ELEMENT], priority=3,
        ))
        registry.register(Tool(
            name="high_priority", description="",
            capabilities=[ToolCapability.CLICK_ELEMENT], priority=9,
        ))

        results = registry.find_tools(ToolCapability.CLICK_ELEMENT)
        assert results[0].name == "high_priority"
        assert results[1].name == "low_priority"

    def test_environment_filter(self):
        registry = ToolRegistry()
        registry.register(Tool(
            name="browser_click", description="",
            capabilities=[ToolCapability.CLICK_ELEMENT],
            environment="browser",
        ))
        registry.register(Tool(
            name="desktop_click", description="",
            capabilities=[ToolCapability.CLICK_ELEMENT],
            environment="desktop",
        ))

        # Filter to browser only
        browser_tools = registry.find_tools(ToolCapability.CLICK_ELEMENT, environment="browser")
        assert len(browser_tools) == 1
        assert browser_tools[0].name == "browser_click"

        # No filter — returns both
        all_tools = registry.find_tools(ToolCapability.CLICK_ELEMENT)
        assert len(all_tools) == 2

    def test_tool_with_any_environment_always_matches(self):
        registry = ToolRegistry()
        registry.register(Tool(
            name="universal_memory", description="",
            capabilities=[ToolCapability.STORE_MEMORY],
            environment="any",
        ))

        # Should match any environment filter
        assert len(registry.find_tools(ToolCapability.STORE_MEMORY, environment="browser")) == 1
        assert len(registry.find_tools(ToolCapability.STORE_MEMORY, environment="desktop")) == 1

    def test_list_capabilities(self):
        registry = ToolRegistry()
        registry.register(Tool(name="a", description="", capabilities=[ToolCapability.READ_DOM]))
        registry.register(Tool(name="b", description="", capabilities=[ToolCapability.READ_DOM, ToolCapability.SEARCH_WEB]))

        cap_map = registry.list_capabilities()
        assert "read_dom" in cap_map
        assert len(cap_map["read_dom"]) == 2
        assert "search_web" in cap_map

    def test_unregister(self):
        registry = ToolRegistry()
        registry.register(Tool(name="temp", description="", capabilities=[ToolCapability.RUN_COMMAND]))
        assert registry.tool_count == 1
        registry.unregister("temp")
        assert registry.tool_count == 0


class TestDefaultRegistry:
    """Test the default tool registry has proper coverage."""

    def setup_method(self):
        self.registry = build_default_registry()

    def test_has_browser_tools(self):
        tools = self.registry.find_tools(ToolCapability.NAVIGATE_URL)
        assert len(tools) >= 1
        assert any("browser" in t.name for t in tools)

    def test_has_desktop_tools(self):
        tools = self.registry.find_tools(ToolCapability.OPEN_APPLICATION)
        assert len(tools) >= 1
        assert any("desktop" in t.name for t in tools)

    def test_has_file_tools(self):
        tools = self.registry.find_tools(ToolCapability.CREATE_FILE)
        assert len(tools) >= 1

    def test_has_memory_tools(self):
        tools = self.registry.find_tools(ToolCapability.STORE_MEMORY)
        assert len(tools) >= 1

    def test_has_communication_tools(self):
        tools = self.registry.find_tools(ToolCapability.SEND_MESSAGE)
        assert len(tools) >= 1

    def test_has_verification_tools(self):
        tools = self.registry.find_tools(ToolCapability.VERIFY_GOAL)
        assert len(tools) >= 1

    def test_multiple_environments_for_click(self):
        """Clicking should be available in both browser and desktop."""
        tools = self.registry.find_tools(ToolCapability.CLICK_ELEMENT)
        environments = {t.environment for t in tools}
        assert "browser" in environments
        assert "desktop" in environments

    def test_tool_count_reasonable(self):
        """Default registry should have 15+ tools."""
        assert self.registry.tool_count >= 15

    def test_planner_query_for_research_goal(self):
        """Planner can find tools for a research workflow."""
        # "Research laptops" needs: search + read + summarize + create file
        search_tools = self.registry.find_tools(ToolCapability.SEARCH_WEB)
        read_tools = self.registry.find_tools(ToolCapability.EXTRACT_WEB_CONTENT)
        summarize_tools = self.registry.find_tools(ToolCapability.SUMMARIZE)
        file_tools = self.registry.find_tools(ToolCapability.CREATE_FILE)

        assert len(search_tools) >= 1
        assert len(read_tools) >= 1
        assert len(summarize_tools) >= 1
        assert len(file_tools) >= 1

    def test_planner_query_for_messaging_goal(self):
        """Planner can find tools for messaging."""
        # "Send Om a message" needs: open_app/navigate + type + send
        nav_tools = self.registry.find_tools(ToolCapability.NAVIGATE_URL)
        type_tools = self.registry.find_tools(ToolCapability.TYPE_TEXT)
        msg_tools = self.registry.find_tools(ToolCapability.SEND_MESSAGE)

        assert len(nav_tools) >= 1
        assert len(type_tools) >= 1
        assert len(msg_tools) >= 1
