"""Request Router — the top-level entry point for all user requests.

Routes requests to JARVIS mode (fast assistant) or FRIDAY mode (agent)
based on classification. Ensures the system feels fast by default.

Architecture:
    User → RequestRouter → Classifier → Mode Handler
                                           ├─ JARVIS: LLM → Response (fast)
                                           └─ FRIDAY: Engine → Perceive → Plan → Act → Verify
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from friday.router.classifier import (
    ClassificationResult,
    ComplexityLevel,
    RequestClassifier,
    RequestMode,
)


@dataclass
class RouteResult:
    """Result of routing a request."""

    mode: RequestMode
    complexity: ComplexityLevel
    response: str = ""
    action_result: Optional[Any] = None  # ActionResult for FRIDAY mode
    classification: Optional[ClassificationResult] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_action(self) -> bool:
        """Whether this involved an action (FRIDAY mode)."""
        return self.mode == RequestMode.FRIDAY

    @property
    def is_conversation(self) -> bool:
        """Whether this was pure conversation (JARVIS mode)."""
        return self.mode == RequestMode.JARVIS


class RequestRouter:
    """Routes user requests to the appropriate mode handler.

    Usage:
        router = RequestRouter(
            jarvis_handler=lambda text, ctx: llm_respond(text),
            friday_handler=lambda text, ctx, level: engine.execute(text),
        )

        result = router.route("What is Python?")
        # → JARVIS handles it instantly

        result = router.route("Open Chrome and search for laptops")
        # → FRIDAY handles with perception + verification
    """

    def __init__(
        self,
        jarvis_handler: Optional[Callable] = None,
        friday_handler: Optional[Callable] = None,
        classifier: Optional[RequestClassifier] = None,
    ) -> None:
        """Initialize the router.

        Args:
            jarvis_handler: fn(text, context) → str response
            friday_handler: fn(text, context, complexity) → ActionResult/str
            classifier: Custom classifier (defaults to built-in)
        """
        self._classifier = classifier or RequestClassifier()
        self._jarvis_handler = jarvis_handler
        self._friday_handler = friday_handler

    @property
    def classifier(self) -> RequestClassifier:
        """Access the request classifier."""
        return self._classifier

    def route(
        self,
        text: str,
        wake_word: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> RouteResult:
        """Route a user request to the appropriate mode.

        Args:
            text: User's request text
            wake_word: Detected wake word ("jarvis" or "friday")
            context: Optional context (memory, state, session info)

        Returns:
            RouteResult with response and metadata
        """
        ctx = context or {}

        # Classify the request
        classification = self._classifier.classify(text, wake_word=wake_word)

        # Route based on mode
        if classification.mode == RequestMode.JARVIS:
            return self._handle_jarvis(text, ctx, classification)
        elif classification.mode == RequestMode.FRIDAY:
            return self._handle_friday(text, ctx, classification)
        else:
            # HYBRID: start with JARVIS, may escalate
            return self._handle_hybrid(text, ctx, classification)

    def _handle_jarvis(
        self,
        text: str,
        context: Dict,
        classification: ClassificationResult,
    ) -> RouteResult:
        """Handle in JARVIS assistant mode — fast, conversational."""
        response = ""
        if self._jarvis_handler:
            try:
                response = self._jarvis_handler(text, context)
            except Exception as exc:
                response = f"I encountered an error: {exc}"

        return RouteResult(
            mode=RequestMode.JARVIS,
            complexity=classification.complexity,
            response=response,
            classification=classification,
            metadata={"reasoning": classification.reasoning},
        )

    def _handle_friday(
        self,
        text: str,
        context: Dict,
        classification: ClassificationResult,
    ) -> RouteResult:
        """Handle in FRIDAY agent mode — perceive, plan, act, verify."""
        response = ""
        action_result = None

        if self._friday_handler:
            try:
                result = self._friday_handler(text, context, classification.complexity)
                if isinstance(result, str):
                    response = result
                else:
                    action_result = result
                    response = getattr(result, 'message', str(result))
            except Exception as exc:
                response = f"Action failed: {exc}"

        return RouteResult(
            mode=RequestMode.FRIDAY,
            complexity=classification.complexity,
            response=response,
            action_result=action_result,
            classification=classification,
            metadata={
                "reasoning": classification.reasoning,
                "intents": classification.detected_intents,
            },
        )

    def _handle_hybrid(
        self,
        text: str,
        context: Dict,
        classification: ClassificationResult,
    ) -> RouteResult:
        """Handle hybrid mode — JARVIS first, may escalate to FRIDAY."""
        # For now, treat hybrid as JARVIS (can escalate later)
        return self._handle_jarvis(text, context, classification)
