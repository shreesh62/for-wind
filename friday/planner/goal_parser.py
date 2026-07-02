"""Goal Parser — converts natural language into structured Goal objects.

The parser extracts:
- Intent (what the user wants to achieve)
- Target (what app/resource/entity)
- Parameters (specifics like URLs, names, text)
- Constraints (timing, conditions)

Works at Level 2-3 complexity. Level 0-1 don't need planning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class GoalIntent(str, Enum):
    """High-level categories of user goals."""

    NAVIGATE = "navigate"       # Go to URL/page/app
    COMMUNICATE = "communicate" # Send message/email
    SEARCH = "search"           # Find information
    CREATE = "create"           # Create file/document/content
    AUTOMATE = "automate"       # Automated workflow
    MANAGE = "manage"           # Organize/move/delete files
    CONTROL = "control"         # Control media/system
    RESEARCH = "research"       # Multi-source research
    UNKNOWN = "unknown"


@dataclass
class GoalParameter:
    """A parameter extracted from the goal."""

    name: str
    value: str
    confidence: float = 1.0


@dataclass
class Goal:
    """Structured representation of a user's goal.

    A goal is what the user wants to achieve, broken down into
    intent, target, parameters, and sub-goals (for multi-step).
    """

    raw_text: str
    intent: GoalIntent
    target: str = ""
    parameters: List[GoalParameter] = field(default_factory=list)
    sub_goals: List["Goal"] = field(default_factory=list)
    constraints: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0

    @property
    def is_multi_step(self) -> bool:
        """Whether this goal has sub-goals."""
        return len(self.sub_goals) > 0

    @property
    def step_count(self) -> int:
        """Total number of steps (including sub-goals)."""
        if not self.sub_goals:
            return 1
        return sum(g.step_count for g in self.sub_goals)

    def get_param(self, name: str) -> Optional[str]:
        """Get a parameter value by name."""
        for p in self.parameters:
            if p.name == name:
                return p.value
        return None


# --- Pattern matching for goal extraction ---

_NAVIGATE_PATTERNS = [
    (r"(?:go to|open|navigate to|visit)\s+(.+)", "navigate"),
    (r"(?:launch|start|run)\s+(.+)", "launch"),
]

_COMMUNICATE_PATTERNS = [
    (r"(?:send|message|text|dm)\s+(.+?)(?:\s+(?:saying|that|with message)\s+(.+))?$", "send"),
    (r"(?:email|mail)\s+(.+?)(?:\s+(?:about|saying|with subject)\s+(.+))?$", "email"),
    (r"(?:call|ring)\s+(.+)", "call"),
]

_SEARCH_PATTERNS = [
    (r"(?:search|look up|find|google)\s+(?:for\s+)?(.+)", "search"),
]

_CREATE_PATTERNS = [
    (r"(?:create|make|build|generate)\s+(.+)", "create"),
    (r"(?:write|draft|compose)\s+(.+)", "write"),
]

_APP_KEYWORDS = {
    "chrome", "whatsapp", "instagram", "gmail", "spotify",
    "notepad", "vscode", "terminal", "explorer", "youtube",
    "amazon", "twitter", "discord", "telegram", "excel",
}


class GoalParser:
    """Parses natural language commands into structured Goal objects.

    Handles:
    - Single-step goals ("Open Chrome")
    - Multi-step goals ("Open WhatsApp and send Om hello")
    - Complex goals with parameters ("Search Amazon for laptops under 50k")

    Usage:
        parser = GoalParser()
        goal = parser.parse("Open WhatsApp and send Om hello")
        print(goal.intent)       # GoalIntent.COMMUNICATE
        print(goal.is_multi_step) # True
        print(goal.sub_goals[0].intent) # GoalIntent.NAVIGATE
    """

    def parse(self, text: str) -> Goal:
        """Parse a natural language command into a Goal.

        Args:
            text: User's command text

        Returns:
            Structured Goal object
        """
        text = text.strip()
        if not text:
            return Goal(raw_text=text, intent=GoalIntent.UNKNOWN)

        # Check for multi-step (connected by "and", "then", "after that")
        steps = self._split_steps(text)

        if len(steps) > 1:
            sub_goals = [self._parse_single(step) for step in steps]
            # Overall intent is the last meaningful step
            primary_intent = sub_goals[-1].intent if sub_goals else GoalIntent.UNKNOWN

            return Goal(
                raw_text=text,
                intent=primary_intent,
                sub_goals=sub_goals,
                confidence=min(g.confidence for g in sub_goals) * 0.9,
            )

        return self._parse_single(text)

    def _parse_single(self, text: str) -> Goal:
        """Parse a single-step command."""
        text_lower = text.lower().strip()

        # Try navigate patterns
        for pattern, _ in _NAVIGATE_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                target = match.group(1).strip()
                return Goal(
                    raw_text=text,
                    intent=GoalIntent.NAVIGATE,
                    target=target,
                    confidence=0.85,
                )

        # Try communicate patterns
        for pattern, action in _COMMUNICATE_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                recipient = match.group(1).strip()
                message = match.group(2).strip() if match.lastindex >= 2 and match.group(2) else ""
                params = [GoalParameter(name="recipient", value=recipient)]
                if message:
                    params.append(GoalParameter(name="message", value=message))
                return Goal(
                    raw_text=text,
                    intent=GoalIntent.COMMUNICATE,
                    target=recipient,
                    parameters=params,
                    confidence=0.8,
                )

        # Check for research/complex (BEFORE search patterns)
        if any(kw in text_lower for kw in ["research", "compare", "analyze", "summarize all"]):
            return Goal(
                raw_text=text,
                intent=GoalIntent.RESEARCH,
                target=text,
                confidence=0.7,
            )

        # Try search patterns
        for pattern, _ in _SEARCH_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                query = match.group(1).strip()
                return Goal(
                    raw_text=text,
                    intent=GoalIntent.SEARCH,
                    target=query,
                    parameters=[GoalParameter(name="query", value=query)],
                    confidence=0.8,
                )

        # Try create patterns
        for pattern, _ in _CREATE_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                target = match.group(1).strip()
                return Goal(
                    raw_text=text,
                    intent=GoalIntent.CREATE,
                    target=target,
                    confidence=0.75,
                )

        # Check for control (media/system)
        if any(kw in text_lower for kw in ["play", "pause", "stop", "volume", "mute"]):
            return Goal(
                raw_text=text,
                intent=GoalIntent.CONTROL,
                target=text,
                confidence=0.75,
            )

        # Fallback
        return Goal(
            raw_text=text,
            intent=GoalIntent.UNKNOWN,
            target=text,
            confidence=0.4,
        )

    def _split_steps(self, text: str) -> List[str]:
        """Split multi-step commands into individual steps."""
        # Split on connectors
        connectors = [
            r"\s+and then\s+",
            r"\s+then\s+",
            r"\s+after that\s+",
            r"\s+followed by\s+",
            r"\s+and\s+(?=(?:open|send|click|type|search|navigate|download|create|message|email))",
        ]

        parts = [text]
        for connector in connectors:
            new_parts = []
            for part in parts:
                split = re.split(connector, part, flags=re.IGNORECASE)
                new_parts.extend(s.strip() for s in split if s.strip())
            parts = new_parts

        return parts
