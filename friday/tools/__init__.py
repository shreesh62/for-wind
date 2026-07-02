"""Tool ecosystem — environment-agnostic capabilities for the General Operator.

FRIDAY is a General Purpose Computer Operator. Tools are reusable capabilities
the planner composes to achieve goals. The USER never chooses tools.
The PLANNER chooses tools based on goal + current WorldState.

Tool Categories:
- BrowserTool: navigate, click, read, type, search (DOM-first)
- DesktopTool: open_app, focus, click, type, read UI controls
- FileTool: create, read, write, move, delete files
- DocumentTool: create/edit documents (Word, Excel, etc.)
- MemoryTool: store, recall, search knowledge
- ResearchTool: web search, extract, summarize
- CommunicationTool: send message, send email
- SystemTool: run command, check processes, system state
- VerificationTool: verify goal completion

Design:
- Tools are registered by capability, not by application.
- The planner selects tools based on what the goal requires.
- Tools operate on environments (browser, desktop, filesystem) — apps are just environments.
"""

from friday.tools.registry import ToolRegistry, Tool, ToolCapability

__all__ = ["ToolRegistry", "Tool", "ToolCapability"]
