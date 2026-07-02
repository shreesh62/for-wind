"""Memory Controller — unified access to all memory tiers.

Single interface for the rest of FRIDAY to interact with memory.
Handles routing to the appropriate tier, cross-tier consolidation,
and bridging to the existing legacy memory system.

Architecture:
    FridayMemory
    ├── WorkingMemory (volatile, current session)
    ├── EpisodicMemory (persistent, interaction history)
    ├── ProceduralMemory (persistent, learned patterns)
    └── Legacy bridge (existing vector_memory.py + memory_controller.py)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from friday.memory.working import WorkingMemory, ConversationTurn, ActiveGoal
from friday.memory.episodic import EpisodicMemory, Episode
from friday.memory.procedural import ProceduralMemory, ActionPattern, RepairOutcome
from friday.memory.semantic import SemanticMemory, Fact


@dataclass
class MemoryContext:
    """Complete memory context for LLM prompts or decision-making."""

    working_context: str = ""
    relevant_episodes: List[Episode] = None
    suggested_strategy: Optional[List[str]] = None
    user_preferences: Dict[str, Any] = None

    def __post_init__(self):
        if self.relevant_episodes is None:
            self.relevant_episodes = []
        if self.user_preferences is None:
            self.user_preferences = {}

    def to_prompt_string(self, max_length: int = 2000) -> str:
        """Render memory context as a string for LLM prompts."""
        parts = []

        if self.working_context:
            parts.append(self.working_context)

        if self.relevant_episodes:
            parts.append("\n[Relevant past interactions:]")
            for ep in self.relevant_episodes[:3]:
                parts.append(f"- {ep.user_text} → {ep.assistant_response[:80]}")

        if self.suggested_strategy:
            parts.append(f"\n[Suggested approach: {' → '.join(self.suggested_strategy[:5])}]")

        result = "\n".join(parts)
        return result[:max_length]


class FridayMemory:
    """Unified memory controller for all FRIDAY memory tiers.

    Usage:
        memory = FridayMemory()

        # Record interaction
        memory.record_turn("Open Chrome", "Opening Chrome now.", mode="friday")

        # Get context for next interaction
        context = memory.get_context("open whatsapp")

        # Record learned pattern
        memory.record_pattern(ActionPattern(...))

        # Get suggestions
        strategy = memory.suggest_action_strategy("click", "hash123")
    """

    def __init__(
        self,
        data_dir: str = "friday_data",
        legacy_memory=None,
        embedding_provider=None,
    ) -> None:
        """Initialize all memory tiers.

        Args:
            data_dir: Directory for persistent memory files
            legacy_memory: Existing MemoryController instance (bridge)
            embedding_provider: NVIDIA provider for semantic embeddings
        """
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory(f"{data_dir}/episodic_memory.json")
        self.procedural = ProceduralMemory(f"{data_dir}/procedural_memory.json")
        self.semantic = SemanticMemory(
            f"{data_dir}/semantic_memory.json",
            embedding_provider=embedding_provider,
        )
        self._legacy = legacy_memory

    def record_turn(
        self,
        user_text: str,
        assistant_response: str,
        mode: str = "jarvis",
        action_type: Optional[str] = None,
        action_success: Optional[bool] = None,
        complexity: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        """Record a complete interaction turn across all relevant tiers."""
        # Working memory (volatile)
        self.working.add_turn(user_text, assistant_response, mode=mode)

        # Episodic memory (persistent)
        episode = Episode(
            user_text=user_text,
            assistant_response=assistant_response,
            mode=mode,
            action_type=action_type,
            action_success=action_success,
            complexity_level=complexity,
            duration_ms=duration_ms,
        )
        self.episodic.record(episode)

        # Legacy bridge
        if self._legacy and hasattr(self._legacy, 'add_turn'):
            try:
                self._legacy.add_turn(user_text, assistant_response)
            except Exception:
                pass

    def record_pattern(self, pattern: ActionPattern) -> None:
        """Record a successful action pattern to procedural memory."""
        self.procedural.record_success(pattern)

    def record_repair(self, outcome: RepairOutcome) -> None:
        """Record a repair attempt outcome."""
        self.procedural.record_repair(outcome)

    def remember_fact(self, content: str, category: str = "general") -> None:
        """Store a durable fact in semantic memory."""
        self.semantic.add_fact(Fact(content=content, category=category))

    def recall_facts(self, query: str, top_k: int = 3) -> List[Fact]:
        """Retrieve relevant facts from semantic memory."""
        return self.semantic.search(query, top_k=top_k)

    def get_context(self, query: str = "") -> MemoryContext:
        """Build complete memory context for a request.

        Pulls from all tiers to provide rich context for
        decision-making and LLM prompts.
        """
        # Working memory context
        working_ctx = self.working.get_context_for_llm()

        # Relevant past episodes
        episodes = []
        if query:
            episodes = self.episodic.recall(query, top_k=3)

        # Relevant semantic facts
        facts = []
        if query:
            try:
                fact_objs = self.semantic.search(query, top_k=3)
                facts = [f.content for f in fact_objs]
            except Exception:
                facts = []

        return MemoryContext(
            working_context=working_ctx,
            relevant_episodes=episodes,
            suggested_strategy=None,
            user_preferences={"facts": facts} if facts else {},
        )

    def suggest_action_strategy(
        self, action_type: str, context_hash: str
    ) -> Optional[List[str]]:
        """Get a suggested strategy from procedural memory."""
        return self.procedural.suggest_strategy(action_type, context_hash)

    def suggest_repair(self, failure_type: str, action_type: str) -> Optional[str]:
        """Get a suggested repair strategy."""
        return self.procedural.suggest_repair(failure_type, action_type)

    def set_active_goal(self, text: str, steps: int = 0) -> None:
        """Set the current active goal in working memory."""
        self.working.set_goal(ActiveGoal(
            text=text,
            steps_total=steps,
        ))

    def update_goal_progress(self, completed: int) -> None:
        """Update goal progress."""
        if self.working.active_goal:
            self.working.active_goal.steps_completed = completed

    def complete_goal(self) -> None:
        """Mark current goal as completed."""
        if self.working.active_goal:
            self.working.active_goal.status = "completed"
            self.working.clear_goal()

    def get_statistics(self) -> Dict[str, Any]:
        """Get memory system statistics."""
        return {
            "working": {
                "turns": self.working.turn_count,
                "has_goal": self.working.active_goal is not None,
            },
            "episodic": {
                "total_episodes": self.episodic.total_episodes,
                "success_rate": self.episodic.get_success_rate(),
            },
            "procedural": self.procedural.get_statistics(),
            "semantic": {
                "total_facts": self.semantic.total_facts,
                "has_embeddings": self.semantic.has_embeddings,
            },
        }

    def reset_session(self) -> None:
        """Reset working memory (new session, keep persistent data)."""
        self.working.reset()
