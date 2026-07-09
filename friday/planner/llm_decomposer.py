"""LLM Decomposer — uses reasoning model to decompose goals into capabilities.

This is the brain of the General Operator. Instead of pattern-matching
goal types to pre-built step sequences, it THINKS about what the goal
requires and produces capability-based steps.

No task-specific pipelines. No ResearchPipeline, EmailPipeline, etc.
Just: Goal → LLM reasoning → Capability requirements → Tool selection.

The same decomposition handles ANY goal because the LLM reasons about
requirements, not templates.
"""

from __future__ import annotations

import asyncio
import json
import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from friday.tools.registry import ToolCapability, ToolRegistry


# The available capabilities the LLM can choose from
_CAPABILITY_DESCRIPTIONS = """
Available capabilities (use ONLY these names):
- OPEN_APPLICATION: Launch or switch to an application
- SWITCH_WINDOW: Bring a window to foreground
- NAVIGATE_URL: Open a URL in browser
- READ_SCREEN: Read what's visible on screen
- READ_DOM: Read browser page content (text, links, elements)
- READ_UI_CONTROLS: Read desktop app controls
- READ_FILE: Read a file's contents
- SEARCH_WEB: Search the internet for information
- EXTRACT_WEB_CONTENT: Extract specific content from a web page
- GENERATE_TEXT: Generate text/content using AI
- SUMMARIZE: Summarize information
- CREATE_FILE: Create a new file
- EDIT_FILE: Modify an existing file
- MOVE_FILE: Move/rename a file
- SEND_MESSAGE: Send a message (any platform)
- SEND_EMAIL: Send an email
- CLICK_ELEMENT: Click something on screen
- TYPE_TEXT: Type text into a field
- SCROLL: Scroll to see more content
- RUN_COMMAND: Run a system command
- DOWNLOAD_FILE: Download a file from the web
- VERIFY_RESULT: Verify an intermediate result
"""


@dataclass
class DecomposedStep:
    """A step produced by LLM decomposition."""

    capability: str  # ToolCapability value
    target: str
    description: str
    depends_on_previous: bool = True


@dataclass
class DecompositionResult:
    """Result of LLM goal decomposition."""

    goal: str
    steps: List[DecomposedStep] = field(default_factory=list)
    reasoning: str = ""
    from_llm: bool = False


class LLMDecomposer:
    """Uses a reasoning LLM to decompose arbitrary goals into capabilities.

    This is NOT pattern matching. The LLM actually thinks about:
    - What information is needed?
    - What actions produce the desired output?
    - What order makes sense?
    - What capabilities from the registry achieve each need?

    Usage:
        decomposer = LLMDecomposer(model_router=router)
        result = await decomposer.decompose(
            "Research gaming laptops under 80k and create a Word report"
        )
        # result.steps = [
        #   SEARCH_WEB "gaming laptops under 80000",
        #   READ_DOM "search results",
        #   NAVIGATE_URL "top result",
        #   EXTRACT_WEB_CONTENT "specs and prices",
        #   SEARCH_WEB "second laptop option",
        #   EXTRACT_WEB_CONTENT "comparison data",
        #   GENERATE_TEXT "comparison report content",
        #   CREATE_FILE "laptop_report.docx",
        #   VERIFY_RESULT "report created with content"
        # ]
    """

    SYSTEM_PROMPT = (
        "You are a task decomposition engine for a computer operator AI. "
        "Given a user's goal, break it down into a sequence of capability-based steps. "
        "Each step must use exactly ONE capability from the list below. "
        "Think about WHAT the goal actually requires, not what apps to open. "
        "Focus on the INFORMATION NEEDS and ACTIONS needed to complete the goal. "
        "Do NOT create unnecessary steps. Be efficient. "
        "The operator can search the web, read pages, generate text, create files, "
        "interact with apps, and verify results.\n\n"
        f"{_CAPABILITY_DESCRIPTIONS}\n\n"
        "Respond ONLY with a JSON array of steps. Each step: "
        '{"capability": "<NAME>", "target": "<what to act on>", "description": "<what this step does>"}\n'
        "Example for 'Send Om a birthday message on WhatsApp':\n"
        '[{"capability": "NAVIGATE_URL", "target": "web.whatsapp.com", "description": "Open WhatsApp"}, '
        '{"capability": "CLICK_ELEMENT", "target": "Om", "description": "Find and open chat with Om"}, '
        '{"capability": "TYPE_TEXT", "target": "Happy birthday Om!", "description": "Type birthday message"}, '
        '{"capability": "CLICK_ELEMENT", "target": "send button", "description": "Send the message"}, '
        '{"capability": "VERIFY_RESULT", "target": "message sent", "description": "Verify message was sent"}]'
    )

    def __init__(self, model_router=None) -> None:
        self._router = model_router

    async def decompose(self, goal: str, context: str = "") -> DecompositionResult:
        """Decompose a goal using LLM reasoning.

        Args:
            goal: The user's goal text
            context: Optional context (current state, previous results)

        Returns:
            DecompositionResult with capability-based steps
        """
        if not self._router:
            return self._fallback_decompose(goal)

        prompt = f"Goal: {goal}"
        if context:
            prompt += f"\nContext: {context}"

        try:
            from friday.models.router import ModelCapability
            response = await self._router.complete(
                prompt,
                capability=ModelCapability.REASONING,
                # Decomposition needs accurate capability labeling. gpt-oss-120b
                # answers in ~1-2s with clean JSON. (The former qwen3-next-80b now
                # hangs to timeout on the free NIM tier.)
                model="openai/gpt-oss-120b",
                max_tokens=600,
                temperature=0.2,
                system_prompt=self.SYSTEM_PROMPT,
            )

            steps = self._parse_response(response.text)
            if steps:
                return DecompositionResult(
                    goal=goal,
                    steps=steps,
                    reasoning=f"LLM decomposed into {len(steps)} steps",
                    from_llm=True,
                )
        except Exception:
            pass

        return self._fallback_decompose(goal)

    def decompose_sync(self, goal: str, context: str = "") -> DecompositionResult:
        """Synchronous wrapper for decompose."""
        try:
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.decompose(goal, context))
                return future.result(timeout=45)
        except RuntimeError:
            return asyncio.run(self.decompose(goal, context))

    def _parse_response(self, text: str) -> List[DecomposedStep]:
        """Parse LLM JSON response into steps."""
        try:
            # Find JSON array in response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start < 0 or end <= start:
                return []

            data = json.loads(text[start:end])
            steps = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                cap = item.get("capability", "").upper()
                # Validate capability exists
                try:
                    ToolCapability(cap.lower())
                except ValueError:
                    cap = "OPEN_APPLICATION"  # fallback

                steps.append(DecomposedStep(
                    capability=cap.lower(),
                    target=item.get("target", ""),
                    description=item.get("description", ""),
                ))

            return steps if steps else []
        except (json.JSONDecodeError, ValueError):
            return []

    def _fallback_decompose(self, goal: str) -> DecompositionResult:
        """Fallback when LLM is unavailable — minimal generic decomposition."""
        return DecompositionResult(
            goal=goal,
            steps=[
                DecomposedStep(
                    capability="search_web",
                    target=goal,
                    description=f"Search for information about: {goal}",
                ),
                DecomposedStep(
                    capability="extract_web_content",
                    target="search results",
                    description="Read and extract relevant information",
                ),
                DecomposedStep(
                    capability="verify_result",
                    target=goal,
                    description="Verify goal progress",
                ),
            ],
            reasoning="Fallback decomposition (LLM unavailable)",
            from_llm=False,
        )
