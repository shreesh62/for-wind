"""Memory layer — multi-tier memory system inspired by Memory OS.

Tiers:
- Working Memory: Current task context (volatile, fast)
- Episodic Memory: Interaction history (persistent)
- Procedural Memory: Learned action patterns (persistent)
- Semantic Memory: Facts and knowledge (future)
- User Memory: Preferences and profiles (future)

Design:
- Memory as a service (framework-agnostic interfaces)
- Local-first (JSON → SQLite → MongoDB Atlas via Student Pack)
- Support future synchronization across harnesses
- Bounded growth with consolidation
"""

from friday.memory.controller import FridayMemory, MemoryContext
from friday.memory.working import WorkingMemory, ConversationTurn, ActiveGoal
from friday.memory.episodic import EpisodicMemory, Episode
from friday.memory.procedural import ProceduralMemory, ActionPattern, RepairOutcome
from friday.memory.semantic import SemanticMemory, Fact
from friday.memory.interfaces import MemoryEntry, MemoryStore, MemoryTier
from friday.memory.runtime import MemoryRuntime, MemoryDecision, CandidateVerdict

__all__ = [
    "FridayMemory",
    "MemoryContext",
    "MemoryRuntime",
    "MemoryDecision",
    "CandidateVerdict",
    "WorkingMemory",
    "ConversationTurn",
    "ActiveGoal",
    "EpisodicMemory",
    "Episode",
    "ProceduralMemory",
    "ActionPattern",
    "RepairOutcome",
    "SemanticMemory",
    "Fact",
    "MemoryEntry",
    "MemoryStore",
    "MemoryTier",
]
