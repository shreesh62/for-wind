"""Request Classifier — determines intent complexity and target mode.

Classifies every user request into:
1. Mode: JARVIS (assistant) or FRIDAY (agent)
2. Complexity Level: 0-3

This runs BEFORE any heavy processing to ensure fast routing.
Simple questions never touch the agent pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum, Enum
from typing import List, Optional, Set


class RequestMode(str, Enum):
    """Which mode handles this request."""

    JARVIS = "jarvis"   # Assistant mode — fast, conversational
    FRIDAY = "friday"   # Agent mode — perception, planning, execution
    HYBRID = "hybrid"   # Starts JARVIS, may escalate to FRIDAY


class ComplexityLevel(IntEnum):
    """How complex is this request to fulfill."""

    SIMPLE_QUESTION = 0   # Jarvis: direct answer, no action
    SIMPLE_ACTION = 1     # Friday: single action + verify
    MULTI_STEP = 2        # Friday: mini plan + sequential execution
    COMPLEX_GOAL = 3      # Friday: full agent loop


@dataclass
class ClassificationResult:
    """Result of classifying a user request."""

    mode: RequestMode
    complexity: ComplexityLevel
    confidence: float  # 0-1
    reasoning: str = ""
    detected_intents: List[str] = None
    wake_word_override: Optional[str] = None  # "jarvis" or "friday"

    def __post_init__(self):
        if self.detected_intents is None:
            self.detected_intents = []


# --- Keyword sets for classification ---

# Action verbs that require FRIDAY
_ACTION_VERBS: Set[str] = {
    "open", "close", "click", "type", "search", "navigate",
    "send", "message", "email", "download", "upload", "install",
    "create", "delete", "move", "copy", "rename", "save",
    "play", "pause", "stop", "scroll", "focus", "switch",
    "launch", "run", "start", "minimize", "maximize",
    "screenshot", "capture", "record",
}

# Multi-step indicators
_MULTI_STEP_INDICATORS: Set[str] = {
    "and then", "after that", "next", "also", "then",
    "followed by", "once done", "when finished",
}

# Complex goal indicators
_COMPLEX_INDICATORS: Set[str] = {
    "research", "compare", "analyze and", "build a spreadsheet",
    "summarize all", "download all", "find the best",
    "create a report", "automate", "set up",
    "workflow", "pipeline", "process all",
}

# Question patterns (JARVIS mode)
_QUESTION_PATTERNS: List[str] = [
    r"^(what|who|where|when|why|how|which|can you explain|explain|tell me|describe)\b",
    r"^(is|are|was|were|do|does|did|will|would|could|should|shall)\b",
    r"\?$",
    r"^(help me understand|clarify|define|summarize)\b",
    r"^(compare|contrast|difference between)\b.*\?",
]

# App targets that indicate action
_APP_TARGETS: Set[str] = {
    "chrome", "whatsapp", "instagram", "gmail", "spotify",
    "notepad", "vscode", "terminal", "explorer", "settings",
    "youtube", "amazon", "twitter", "discord", "telegram",
    "excel", "word", "powerpoint", "outlook",
}


class RequestClassifier:
    """Classifies user requests into mode + complexity.

    Fast heuristic classifier that runs before any LLM call.
    Should add < 1ms latency. Uses keyword matching and patterns.

    Usage:
        classifier = RequestClassifier()
        result = classifier.classify("Explain how Python decorators work")
        # result.mode == RequestMode.JARVIS
        # result.complexity == ComplexityLevel.SIMPLE_QUESTION

        result = classifier.classify("Open WhatsApp and send Om hello")
        # result.mode == RequestMode.FRIDAY
        # result.complexity == ComplexityLevel.MULTI_STEP
    """

    def classify(
        self,
        text: str,
        wake_word: Optional[str] = None,
    ) -> ClassificationResult:
        """Classify a user request.

        Args:
            text: The user's request text
            wake_word: If detected, "jarvis" or "friday" — overrides mode

        Returns:
            ClassificationResult with mode, complexity, and reasoning
        """
        text_lower = text.strip().lower()
        words = set(text_lower.split())

        # Wake word override
        if wake_word:
            if wake_word.lower() == "friday":
                return self._classify_as_friday(text_lower, words, wake_word)
            elif wake_word.lower() == "jarvis":
                return self._classify_as_jarvis(text_lower, words, wake_word)

        # Check if it's clearly a question (Level 0 → JARVIS)
        if self._is_question(text_lower):
            return ClassificationResult(
                mode=RequestMode.JARVIS,
                complexity=ComplexityLevel.SIMPLE_QUESTION,
                confidence=0.85,
                reasoning="Detected question pattern",
            )

        # Check for action verbs
        has_action = bool(words & _ACTION_VERBS)

        # Check for app targets
        has_target = bool(words & _APP_TARGETS)

        # Check for multi-step indicators
        has_multi = any(indicator in text_lower for indicator in _MULTI_STEP_INDICATORS)

        # Check for complex goal indicators
        has_complex = any(indicator in text_lower for indicator in _COMPLEX_INDICATORS)

        # Determine complexity
        if has_complex:
            return ClassificationResult(
                mode=RequestMode.FRIDAY,
                complexity=ComplexityLevel.COMPLEX_GOAL,
                confidence=0.8,
                reasoning="Complex goal indicators detected",
                detected_intents=self._extract_intents(text_lower, words),
            )

        if has_multi or (has_action and "and" in words):
            return ClassificationResult(
                mode=RequestMode.FRIDAY,
                complexity=ComplexityLevel.MULTI_STEP,
                confidence=0.8,
                reasoning="Multi-step action with connectors",
                detected_intents=self._extract_intents(text_lower, words),
            )

        if has_action and has_target:
            return ClassificationResult(
                mode=RequestMode.FRIDAY,
                complexity=ComplexityLevel.SIMPLE_ACTION,
                confidence=0.85,
                reasoning="Action verb + app target",
                detected_intents=self._extract_intents(text_lower, words),
            )

        if has_action:
            return ClassificationResult(
                mode=RequestMode.FRIDAY,
                complexity=ComplexityLevel.SIMPLE_ACTION,
                confidence=0.7,
                reasoning="Action verb detected",
                detected_intents=self._extract_intents(text_lower, words),
            )

        # Default: JARVIS (conversational)
        return ClassificationResult(
            mode=RequestMode.JARVIS,
            complexity=ComplexityLevel.SIMPLE_QUESTION,
            confidence=0.6,
            reasoning="No action indicators; defaulting to assistant mode",
        )

    def _classify_as_friday(
        self, text_lower: str, words: set, wake_word: str
    ) -> ClassificationResult:
        """Classify with FRIDAY wake word override."""
        has_multi = any(ind in text_lower for ind in _MULTI_STEP_INDICATORS)
        has_complex = any(ind in text_lower for ind in _COMPLEX_INDICATORS)

        if has_complex:
            level = ComplexityLevel.COMPLEX_GOAL
        elif has_multi or "and" in words:
            level = ComplexityLevel.MULTI_STEP
        else:
            level = ComplexityLevel.SIMPLE_ACTION

        return ClassificationResult(
            mode=RequestMode.FRIDAY,
            complexity=level,
            confidence=0.95,
            reasoning="FRIDAY wake word override",
            detected_intents=self._extract_intents(text_lower, words),
            wake_word_override=wake_word,
        )

    def _classify_as_jarvis(
        self, text_lower: str, words: set, wake_word: str
    ) -> ClassificationResult:
        """Classify with JARVIS wake word override."""
        return ClassificationResult(
            mode=RequestMode.JARVIS,
            complexity=ComplexityLevel.SIMPLE_QUESTION,
            confidence=0.95,
            reasoning="JARVIS wake word override",
            wake_word_override=wake_word,
        )

    def _is_question(self, text: str) -> bool:
        """Determine if text is a question."""
        for pattern in _QUESTION_PATTERNS:
            if re.search(pattern, text):
                return True
        return False

    def _extract_intents(self, text: str, words: set) -> List[str]:
        """Extract detected action intents."""
        intents = []
        for verb in _ACTION_VERBS:
            if verb in words:
                intents.append(verb)
        return intents[:5]  # Cap at 5
