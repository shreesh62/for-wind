"""Tool Registry — environment-agnostic capability registration.

The planner queries the registry to find which tools can achieve a capability.
Tools are NOT organized by application. They're organized by what they DO.

The planner asks: "I need to READ_WEB_CONTENT. What tools can do that?"
Registry answers: BrowserTool.read_page, ResearchTool.scrape

The planner asks: "I need to CREATE_DOCUMENT. What tools can do that?"
Registry answers: DocumentTool.create, FileTool.write

This makes FRIDAY application-agnostic. It reasons about capabilities,
then the tools handle which environment to use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class ToolCapability(str, Enum):
    """What a tool CAN DO (not what app it uses)."""

    # Navigation / Environment
    OPEN_APPLICATION = "open_application"
    SWITCH_WINDOW = "switch_window"
    NAVIGATE_URL = "navigate_url"

    # Reading / Observation
    READ_SCREEN = "read_screen"
    READ_DOM = "read_dom"
    READ_UI_CONTROLS = "read_ui_controls"
    READ_FILE = "read_file"

    # Web
    SEARCH_WEB = "search_web"
    EXTRACT_WEB_CONTENT = "extract_web_content"

    # Text / Content
    GENERATE_TEXT = "generate_text"
    SUMMARIZE = "summarize"

    # Files / Documents
    CREATE_FILE = "create_file"
    EDIT_FILE = "edit_file"
    MOVE_FILE = "move_file"
    DELETE_FILE = "delete_file"
    CREATE_DOCUMENT = "create_document"

    # Communication
    SEND_MESSAGE = "send_message"
    SEND_EMAIL = "send_email"

    # Interaction
    CLICK_ELEMENT = "click_element"
    TYPE_TEXT = "type_text"
    SCROLL = "scroll"

    # System
    RUN_COMMAND = "run_command"
    CHECK_PROCESS = "check_process"

    # Knowledge
    STORE_MEMORY = "store_memory"
    RECALL_MEMORY = "recall_memory"

    # Verification
    VERIFY_RESULT = "verify_result"
    VERIFY_GOAL = "verify_goal"

    # Download / Upload
    DOWNLOAD_FILE = "download_file"
    UPLOAD_FILE = "upload_file"


@dataclass
class Tool:
    """A registered tool with its capabilities and handler.

    Tools are the building blocks the planner composes.
    Each tool declares what capabilities it provides.
    """

    name: str
    description: str
    capabilities: List[ToolCapability]
    handler: Optional[Callable] = None  # async callable(params) -> ActionResult
    environment: str = "any"  # browser, desktop, filesystem, system, any
    requires: List[str] = field(default_factory=list)  # what must be true to use this
    priority: int = 5  # Higher = preferred when multiple tools have same capability

    @property
    def capability_names(self) -> List[str]:
        return [c.value for c in self.capabilities]


class ToolRegistry:
    """Registry of all available tools, queryable by capability.

    The planner uses this to find tools for each step of a goal.
    Environment-aware: a tool may require browser to be open, or a file to exist.

    Usage:
        registry = ToolRegistry()
        registry.register(browser_navigate_tool)
        registry.register(desktop_open_tool)

        # Planner asks: what can navigate to a URL?
        tools = registry.find_tools(ToolCapability.NAVIGATE_URL)
        # Returns: [browser_navigate, desktop_open_url]

        # Planner asks: what can read web content?
        tools = registry.find_tools(ToolCapability.READ_DOM)
        # Returns: [browser_read_page]
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool."""
        self._tools.pop(name, None)

    def find_tools(
        self,
        capability: ToolCapability,
        environment: Optional[str] = None,
    ) -> List[Tool]:
        """Find tools that provide a capability.

        Args:
            capability: What the tool needs to do
            environment: Limit to a specific environment (optional)

        Returns:
            Tools sorted by priority (highest first)
        """
        matches = []
        for tool in self._tools.values():
            if capability in tool.capabilities:
                if environment and tool.environment not in (environment, "any"):
                    continue
                matches.append(tool)
        matches.sort(key=lambda t: t.priority, reverse=True)
        return matches

    def find_by_name(self, name: str) -> Optional[Tool]:
        """Find a tool by name."""
        return self._tools.get(name)

    def list_all(self) -> List[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_capabilities(self) -> Dict[str, List[str]]:
        """Map each capability to the tools that provide it."""
        cap_map: Dict[str, List[str]] = {}
        for tool in self._tools.values():
            for cap in tool.capabilities:
                cap_map.setdefault(cap.value, []).append(tool.name)
        return cap_map

    @property
    def tool_count(self) -> int:
        return len(self._tools)


def build_default_registry() -> ToolRegistry:
    """Build the default tool registry with all FRIDAY capabilities.

    This registers the standard tool set. The planner uses this to
    determine what's possible.
    """
    registry = ToolRegistry()

    # -- Browser Tools --
    registry.register(Tool(
        name="browser.navigate",
        description="Navigate the browser to a URL",
        capabilities=[ToolCapability.NAVIGATE_URL, ToolCapability.OPEN_APPLICATION],
        environment="browser",
        priority=8,
    ))
    registry.register(Tool(
        name="browser.click",
        description="Click an element in the browser (DOM-first)",
        capabilities=[ToolCapability.CLICK_ELEMENT],
        environment="browser",
        priority=8,
    ))
    registry.register(Tool(
        name="browser.type",
        description="Type text into a browser input field",
        capabilities=[ToolCapability.TYPE_TEXT],
        environment="browser",
        priority=8,
    ))
    registry.register(Tool(
        name="browser.read_page",
        description="Read the visible text content of the current page",
        capabilities=[ToolCapability.READ_DOM, ToolCapability.EXTRACT_WEB_CONTENT],
        environment="browser",
        priority=9,
    ))
    registry.register(Tool(
        name="browser.search",
        description="Search the web using a search engine",
        capabilities=[ToolCapability.SEARCH_WEB],
        environment="browser",
        priority=8,
    ))

    # -- Desktop Tools --
    registry.register(Tool(
        name="desktop.open_app",
        description="Launch a desktop application",
        capabilities=[ToolCapability.OPEN_APPLICATION],
        environment="desktop",
        priority=7,
    ))
    registry.register(Tool(
        name="desktop.focus_window",
        description="Bring a window to the foreground",
        capabilities=[ToolCapability.SWITCH_WINDOW],
        environment="desktop",
        priority=8,
    ))
    registry.register(Tool(
        name="desktop.click",
        description="Click a UI element on the desktop (UIA-first)",
        capabilities=[ToolCapability.CLICK_ELEMENT],
        environment="desktop",
        priority=6,
    ))
    registry.register(Tool(
        name="desktop.type",
        description="Type text into the focused application",
        capabilities=[ToolCapability.TYPE_TEXT],
        environment="desktop",
        priority=6,
    ))
    registry.register(Tool(
        name="desktop.read_ui",
        description="Read visible UI controls and text from desktop app",
        capabilities=[ToolCapability.READ_UI_CONTROLS, ToolCapability.READ_SCREEN],
        environment="desktop",
        priority=7,
    ))

    # -- File Tools --
    registry.register(Tool(
        name="file.create",
        description="Create a new file with content",
        capabilities=[ToolCapability.CREATE_FILE, ToolCapability.CREATE_DOCUMENT],
        environment="filesystem",
        priority=9,
    ))
    registry.register(Tool(
        name="file.read",
        description="Read the contents of a file",
        capabilities=[ToolCapability.READ_FILE],
        environment="filesystem",
        priority=9,
    ))
    registry.register(Tool(
        name="file.write",
        description="Write/overwrite content to a file",
        capabilities=[ToolCapability.EDIT_FILE],
        environment="filesystem",
        priority=9,
    ))
    registry.register(Tool(
        name="file.move",
        description="Move or rename a file",
        capabilities=[ToolCapability.MOVE_FILE],
        environment="filesystem",
        priority=9,
    ))
    registry.register(Tool(
        name="file.delete",
        description="Delete a file",
        capabilities=[ToolCapability.DELETE_FILE],
        environment="filesystem",
        priority=9,
    ))

    # -- Memory Tools --
    registry.register(Tool(
        name="memory.store",
        description="Store a fact or interaction in memory",
        capabilities=[ToolCapability.STORE_MEMORY],
        environment="any",
        priority=9,
    ))
    registry.register(Tool(
        name="memory.recall",
        description="Recall relevant memories by query",
        capabilities=[ToolCapability.RECALL_MEMORY],
        environment="any",
        priority=9,
    ))

    # -- Research / Knowledge Tools --
    registry.register(Tool(
        name="research.web_search",
        description="Search the web for information",
        capabilities=[ToolCapability.SEARCH_WEB, ToolCapability.EXTRACT_WEB_CONTENT],
        environment="browser",
        priority=7,
    ))
    registry.register(Tool(
        name="research.summarize",
        description="Summarize content using a language model",
        capabilities=[ToolCapability.SUMMARIZE, ToolCapability.GENERATE_TEXT],
        environment="any",
        priority=8,
    ))

    # -- Communication Tools --
    registry.register(Tool(
        name="communication.send_message",
        description="Send a message via messaging apps (WhatsApp, Instagram, etc.)",
        capabilities=[ToolCapability.SEND_MESSAGE],
        environment="browser",
        priority=7,
    ))
    registry.register(Tool(
        name="communication.send_email",
        description="Send an email",
        capabilities=[ToolCapability.SEND_EMAIL],
        environment="browser",
        priority=7,
    ))

    # -- System Tools --
    registry.register(Tool(
        name="system.run_command",
        description="Run a system/shell command",
        capabilities=[ToolCapability.RUN_COMMAND],
        environment="system",
        priority=6,
    ))
    registry.register(Tool(
        name="system.check_process",
        description="Check if a process is running",
        capabilities=[ToolCapability.CHECK_PROCESS],
        environment="system",
        priority=7,
    ))

    # -- Verification Tools --
    registry.register(Tool(
        name="verification.check_result",
        description="Verify an action outcome via perception",
        capabilities=[ToolCapability.VERIFY_RESULT],
        environment="any",
        priority=10,
    ))
    registry.register(Tool(
        name="verification.check_goal",
        description="Verify whether the overall goal is completed",
        capabilities=[ToolCapability.VERIFY_GOAL],
        environment="any",
        priority=10,
    ))

    return registry
