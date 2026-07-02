"""High-level memory controller orchestrating short- and long-term storage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timezone

from memory_core import get_relevant_memory_snippet
from vector_memory import (
    delete_from_memory as vector_delete,
    get_relevant_memory_snippets,
    log_interaction,
    save_to_memory as vector_save,
)

from .short_term_buffer import ShortTermMemory


_REMEMBER_PATTERN = re.compile(r"^\s*remember(?: that)?\b", flags=re.IGNORECASE)
_FORGET_PATTERN = re.compile(r"^\s*forget(?: about)?\b", flags=re.IGNORECASE)


@dataclass
class MemoryController:
    """Coordinates memory storage, retrieval, and conversational buffer."""

    short_term_limit: int = 8
    long_term_results: int = 3

    def __post_init__(self) -> None:
        self.short_term = ShortTermMemory(max_turns=self.short_term_limit)

    # ------------------------------------------------------------------
    # Conversation handling
    # ------------------------------------------------------------------
    def add_turn(self, user_text: str, assistant_text: str) -> None:
        """Record a dialogue turn in short-term memory and persistent logs."""

        self.short_term.add_turn(user_text, assistant_text)
        log_interaction(user_text, assistant_text)

    def get_short_term_context(self) -> str:
        """Return formatted recent conversation context for prompts."""

        turns = self.short_term.get_recent()
        if not turns:
            return ""
        return "\n".join([f"User: {u}\nJarvis: {a}" for u, a in turns])

    def summarize_recent_actions(self) -> str:
        """Summarize recent assistant actions for inclusion in prompts."""

        turns = list(self.short_term.get_recent())[-3:]
        if not turns:
            return ""
        summary = []
        for user, assistant in turns:
            summary.append(f"• User said: {user}")
            summary.append(f"  Jarvis replied: {assistant}")
        return "\n".join(summary)

    # ------------------------------------------------------------------
    # Long-term retrieval
    # ------------------------------------------------------------------
    def get_long_term_memories(self, query: str, top_k: Optional[int] = None) -> List[str]:
        """Fetch relevant memories with salience+recency rules and deduplication.

        Rules:
        - Skip trivial/short items.
        - Only inject low-salience if similarity score > 0.7 and recency < 30 days, unless explicitly requested.
        - Deduplicate against short-term buffer content and near-substrings.
        - Return top_k items ordered by score.
        """

        k = top_k or self.long_term_results
        ranked = list(get_relevant_memory_snippets(query, top_k=max(k * 4, k)))
        # Add scalar memory if available (legacy API)
        scalar_snippet = get_relevant_memory_snippet(query)
        if scalar_snippet:
            ranked.append({"text": scalar_snippet, "salience": "low", "ts": datetime.now(timezone.utc).isoformat(), "score": 0.6})

        def _is_trivial(s: str) -> bool:
            s2 = (s or "").strip().lower()
            if len(s2) < 12:
                return True
            trivial = {
                "ok", "okay", "thanks", "thank you", "hi", "hello", "done",
                "bye", "yes", "no",
            }
            return s2 in trivial

        def _recent_enough(ts_iso: str) -> bool:
            try:
                ts = datetime.fromisoformat(ts_iso)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_days = (datetime.now(timezone.utc) - ts).days
                return age_days < 30
            except Exception:
                return True

        # Short-term content for dedupe
        st = (self.get_short_term_context() or "").lower()

        filtered: List[str] = []
        seen = set()
        for item in ranked:
            text = (item.get("text") or "").strip()
            if not text or _is_trivial(text):
                continue
            # Skip if already present in short-term buffer
            if text.lower() in st:
                continue
            salience = (item.get("salience") or "low").lower()
            score = float(item.get("score") or 0.0)
            ts = item.get("ts") or ""

            # Enforce low-salience thresholds unless explicitly asked in query
            explicitly_requested = text.lower() in (query or "").lower()
            if salience == "low" and not explicitly_requested:
                if not (score >= 0.7 and _recent_enough(ts)):
                    continue

            key = text.lower()
            if key in seen:
                continue
            if any(key in u.lower() or u.lower() in key for u in filtered):
                continue
            seen.add(key)
            filtered.append(text)

        return filtered[:k]

    # ------------------------------------------------------------------
    # Seeding helpers
    # ------------------------------------------------------------------
    def ensure_vision_memory(self) -> None:
        """Seed the Final Product Vision once for planning context."""
        probe = get_relevant_memory_snippet("Final Product Vision for JARVIS")
        if probe:
            return
        vision = (
            "Final Product Vision for JARVIS: Always-on desktop assistant. Listens to wake word, "
            "understands voice and typed commands. Maintains short-term and vector long-term memory. "
            "Uses capability registry; no hallucinations. Chooses best path: LLM answer, real-time "
            "services (weather, maps), or automations (browser control, type, click, screenshots). "
            "Attaches to real Chrome via DevTools (no new windows unless requested). Interprets screen "
            "with DOM/DevTools + desktop awareness (focus, screenshots, OCR). Robust automations with "
            "recovery, retries, confirmations. Small authenticated remote interface for commands and "
            "results. Packaged desktop app; privacy-first, local by default. Fast and responsive with "
            "streaming audio and async orchestration."
        )
        vector_save(vision)

    # ------------------------------------------------------------------
    # Memory directives
    # ------------------------------------------------------------------
    def handle_memory_directive(self, user_text: str) -> Optional[str]:
        """Process remember/forget commands, returning response if handled."""

        remember_payload = self._extract_payload(_REMEMBER_PATTERN, user_text)
        if remember_payload:
            self.remember(remember_payload)
            return "Acknowledged. I’ll remember that."

        forget_payload = self._extract_payload(_FORGET_PATTERN, user_text)
        if forget_payload:
            removed = self.forget(forget_payload)
            if removed:
                return f"I’ve erased information about {forget_payload}."
            return f"I couldn’t locate anything about {forget_payload}."

        return None

    def remember(self, text: str) -> Optional[str]:
        """Persist a memory snippet if content is non-empty."""

        clean = text.strip()
        if not clean:
            return None
        vector_save(clean)
        return clean

    def forget(self, text: str) -> bool:
        """Remove a memory snippet if it matches stored content."""

        clean = text.strip()
        if not clean:
            return False
        return vector_delete(clean)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_payload(pattern: re.Pattern[str], text: str) -> Optional[str]:
        match = pattern.match(text)
        if not match:
            return None
        payload = text[match.end() :].strip()
        return payload or None

    def clear_short_term(self) -> None:
        """Clear rolling short-term buffer."""

        self.short_term.clear()
