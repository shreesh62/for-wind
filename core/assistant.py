"""Assistant orchestrator coordinating memory, automation, and dialogue."""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, TYPE_CHECKING

from automation.services import AutomationServices
from automation.planner import AutomationPlanner
from core.capability_dispatcher import CapabilityDispatcher
from core.intent_parser import parse_email_intent
from memory.memory_controller import MemoryController
from personality import PersonalityManager
from core.reasoner import ReasoningOutcome, reason_about_command
from services import maps_service
from awareness.snapshot import redact_snapshot_for_prompt

if TYPE_CHECKING:
    from awareness.state_cache import StateCache


_SCREEN_QUERY_PATTERN = re.compile(
    r"(?:what(?:'s| is)|describe|summarize|show|tell me).*?(?:on|in)?\s*(?:the\s*)?screen",
    re.IGNORECASE,
)

_EXPLICIT_WORD_BUDGET_PATTERN = re.compile(r"\b(?:in\s*)?(\d{2,4})\s*words\b", re.IGNORECASE)

_REPEAT_ACTION_PATTERN = re.compile(
    r"\b(?:repeat(?:\s+(?:that|it|last(?:\s+action)?))?|do\s+that\s+again|do\s+it\s+again|run\s+that\s+again)\b",
    re.IGNORECASE,
)
_OPEN_PRONOUN_PATTERN = re.compile(
    r"\b(?:open|launch|start|go\s+to|visit|take\s+me\s+to)\s+(?:it|that)(?:\s+again)?\b",
    re.IGNORECASE,
)

_CANCEL_PATTERN = re.compile(r"\b(?:cancel|stop|never\s+mind|forget\s+it)\b", re.IGNORECASE)
_UNDO_PATTERN = re.compile(r"\b(?:undo|undo\s+that|go\s+back|reverse\s+that)\b", re.IGNORECASE)

_SHORT_RESPONSE_CUES = (
    "short",
    "brief",
    "quick",
    "tldr",
    "too long",
    "summary only",
    "one line",
    "one sentence",
    "summarize",
)

_LONG_RESPONSE_CUES = (
    "detailed",
    "in detail",
    "deep dive",
    "step by step",
    "step-by-step",
    "steps",
    "walk me through",
    "walk through",
    "guide me",
    "guide",
    "tutorial",
    "how do i",
    "how to",
    "why",
    "explain",
    "thorough",
    "elaborate",
    "full explanation",
    "full detail",
    "long answer",
    "complete explanation",
    "explain fully",
    "go deeper",
    "expand",
    "tell me more",
    "more details",
    "more detail",
    "comprehensive",
    "full breakdown",
)


@dataclass
class CommandResult:
    """Outcome returned after processing a user command."""

    final_response: str
    handled: bool = True


class AssistantOrchestrator:
    """High-level orchestrator that interprets commands and routes actions."""

    def __init__(
        self,
        *,
        memory: MemoryController,
        dispatcher: CapabilityDispatcher,
        personality_manager: PersonalityManager,
        llm_callable: Callable[[str, Dict[str, str]], str],
        fixed_responses: Optional[Dict[str, str]] = None,
        headless: bool = True,
        automation: AutomationServices | None = None,
        awareness_state: "StateCache | None" = None,
    ) -> None:
        self.memory = memory
        self.personality_manager = personality_manager
        self.llm_callable = llm_callable
        self.fixed_responses = fixed_responses or {}
        self.automation = automation or AutomationServices(headless=headless)
        self.awareness_state = awareness_state
        self.dispatcher = dispatcher
        self.planner = AutomationPlanner(
            self.automation,
            awareness_state=awareness_state,
            registry=self.dispatcher.registry,
        )
        
        # Initialize CognitiveLoop when COGNITIVE_MODE=1
        self._cognitive_loop = None
        if os.getenv("COGNITIVE_MODE") == "1":
            try:
                from automation.cognitive_loop import CognitiveLoop
                self._cognitive_loop = CognitiveLoop(
                    automation_services=self.automation,
                    awareness_state=awareness_state,
                )
                print("🧠 Cognitive loop initialized")
            except Exception as e:
                raise RuntimeError(
                    f"COGNITIVE_MODE=1 but CognitiveLoop failed to initialize: {e}"
                )
        
        self._last_tool_trace: list[str] = []
        self._last_snapshot: dict | None = None
        self._last_snapshot_redacted: str = "(unavailable)"
        self._snapshot_trace_line: str = "perception_snapshot: (unavailable)"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def process_command(self, command: str) -> CommandResult:
        command_lower = command.lower().strip()
        normalized_command = AutomationPlanner._normalize_command(command)
        normalized_lower = normalized_command.lower().strip()

        self._word_budget = self._decide_word_budget(command)

        snapshot: dict | None = None
        if self.awareness_state is not None:
            try:
                snapshot = self.awareness_state.get_snapshot()
            except Exception:
                snapshot = None
        self._last_snapshot = snapshot if isinstance(snapshot, dict) else None
        try:
            self._last_snapshot_redacted = redact_snapshot_for_prompt(self._last_snapshot or {})
        except Exception:
            self._last_snapshot_redacted = "(unavailable)"

        compact_parts: list[str] = []
        try:
            redacted_lines = [l.strip() for l in self._last_snapshot_redacted.splitlines() if l.strip()]
            if redacted_lines:
                compact_parts.append(redacted_lines[0])
            if len(redacted_lines) >= 4:
                compact_parts.append(redacted_lines[3])
        except Exception:
            compact_parts = []
        compact = " | ".join(compact_parts) if compact_parts else "(unavailable)"
        self._snapshot_trace_line = f"perception_snapshot: {compact}"
        self._last_tool_trace = [self._snapshot_trace_line]

        # Fixed responses
        if command_lower in self.fixed_responses:
            response = self.fixed_responses[command_lower]
            final = self._apply_personality(response)
            self.memory.add_turn(command, final)
            return CommandResult(final_response=final)

        # Memory directives (remember / forget)
        directive_response = self.memory.handle_memory_directive(command)
        if directive_response:
            final = self._apply_personality(directive_response)
            self.memory.add_turn(command, final)
            return CommandResult(final_response=final)

        # Follow-up: distance ambiguity disambiguation (e.g., "choose option 2")
        try:
            followup = maps_service.handle_distance_followup(command)
        except Exception:
            followup = None
        if followup:
            try:
                self._last_tool_trace = [self._snapshot_trace_line, "maps_distance_followup: handled=True"]
            except Exception:
                self._last_tool_trace = [self._snapshot_trace_line]
            final = self._apply_personality(followup)
            self.memory.add_turn(command, final)
            return CommandResult(final_response=final)

        # Reason about route before execution
        cap_key, _ = self.dispatcher.registry.match_intent(normalized_lower)
        if cap_key and not self.dispatcher.registry.is_available(cap_key):
            message = self.dispatcher.registry.explain_unavailable(cap_key)
            try:
                self._last_tool_trace = [self._snapshot_trace_line, f"capability_gate: {cap_key}=unavailable"]
            except Exception:
                self._last_tool_trace = [self._snapshot_trace_line]
            final = self._apply_personality(message)
            self.memory.add_turn(command, final)
            return CommandResult(final_response=final, handled=False)

        outcome: ReasoningOutcome = reason_about_command(
            normalized_command,
            self.dispatcher.registry,
            awareness_state=self.awareness_state,
        )

        if _CANCEL_PATTERN.search(command) or _CANCEL_PATTERN.search(normalized_command):
            msg = None
            try:
                msg = self.planner.cancel_context()
            except Exception:
                msg = "Okay. Cancelled."
            try:
                self._last_tool_trace = [
                    self._snapshot_trace_line,
                    "phase6_followup: cancel=true",
                ]
            except Exception:
                self._last_tool_trace = [self._snapshot_trace_line]
            final = self._apply_personality(msg)
            self.memory.add_turn(command, final)
            return CommandResult(final_response=final)

        if _UNDO_PATTERN.search(command) or _UNDO_PATTERN.search(normalized_command):
            msg = self.planner.undo_last_verified(snapshot=self._last_snapshot)
            try:
                self._last_tool_trace = [
                    self._snapshot_trace_line,
                    "phase6_followup: undo_last_verified=true",
                    *list(getattr(self.planner, "last_tool_trace", []) or []),
                ]
            except Exception:
                self._last_tool_trace = [self._snapshot_trace_line]
            final = self._apply_personality(msg or "I couldn't undo that yet.")
            self.memory.add_turn(command, final)
            return CommandResult(final_response=final)

        if _REPEAT_ACTION_PATTERN.search(command) or _REPEAT_ACTION_PATTERN.search(normalized_command):
            msg = self.planner.repeat_last_verified(snapshot=self._last_snapshot)
            try:
                self._last_tool_trace = [
                    self._snapshot_trace_line,
                    "phase6_followup: repeat_last_verified=true",
                    *list(getattr(self.planner, "last_tool_trace", []) or []),
                ]
            except Exception:
                self._last_tool_trace = [self._snapshot_trace_line]
            final = self._apply_personality(msg or "I couldn't repeat that action yet.")
            self.memory.add_turn(command, final)
            return CommandResult(final_response=final)

        if _OPEN_PRONOUN_PATTERN.search(command) or _OPEN_PRONOUN_PATTERN.search(normalized_command):
            msg = self.planner.open_last_website(snapshot=self._last_snapshot)
            try:
                self._last_tool_trace = [
                    self._snapshot_trace_line,
                    "phase6_followup: open_last_website=true",
                    *list(getattr(self.planner, "last_tool_trace", []) or []),
                ]
            except Exception:
                self._last_tool_trace = [self._snapshot_trace_line]
            final = self._apply_personality(msg or "I couldn't open that website yet.")
            self.memory.add_turn(command, final)
            return CommandResult(final_response=final)

        # PHASE 7: COGNITIVE LOOP AS SINGLE SOURCE OF TRUTH.
        # Placed AFTER the explicit Phase-6 follow-up handlers (cancel / undo /
        # repeat / "open it again") so those conversational continuations route to
        # their handlers first. Under COGNITIVE_MODE=1 the cognitive loop would
        # otherwise intercept any follow-up classified as "automation" (the M18
        # audit's reproducible defect: "open it again" returned "I cannot perceive
        # the current state" instead of routing to open_last_website).
        cognitive_mode = os.getenv("COGNITIVE_MODE", "0") == "1"

        if cognitive_mode and outcome.route == "automation":
            # HARD REQUIREMENT: CognitiveLoop must be initialized
            if not self._cognitive_loop:
                raise RuntimeError("COGNITIVE_MODE=1 but CognitiveLoop is not initialized")

            # Execute through cognitive loop - NO FALLBACK, NO TRY/EXCEPT
            result = self._cognitive_loop.execute_goal(normalized_command)
            self._last_tool_trace.append("cognitive_loop: executed")

            if result:
                final = self._apply_personality(result)
                self.memory.add_turn(command, final)
                return CommandResult(final_response=final)

            # Result is None - cognitive loop couldn't handle it
            final = "Cognitive execution returned no result."
            self.memory.add_turn(command, final)
            return CommandResult(final_response=final, handled=False)

        if _SCREEN_QUERY_PATTERN.search(command) is not None:
            ocr_line = None
            try:
                should_ocr = True
                try:
                    if self.awareness_state is not None:
                        ts = self.awareness_state.ocr_last_updated()
                        if isinstance(ts, (int, float)) and (time.time() - float(ts)) < 2.5:
                            should_ocr = False
                except Exception:
                    should_ocr = True

                if should_ocr:
                    resp = self.automation.ocr_screen()
                    ocr_line = f"ocr_screen: success={resp.success}"
                else:
                    ocr_line = "ocr_screen: skipped_recent=true"
            except Exception as exc:
                ocr_line = f"ocr_screen: error={exc}"

            if self.awareness_state is not None:
                # Give UIA monitor a brief moment to populate the window context.
                try:
                    deadline = time.time() + 1.6
                    while time.time() < deadline:
                        win = None
                        try:
                            win = self.awareness_state.get_window()
                        except Exception:
                            win = None
                        if win and (getattr(win, "title", None) or getattr(win, "app_exe", None)):
                            break
                        time.sleep(0.12)
                except Exception:
                    pass
                try:
                    snapshot = self.awareness_state.get_snapshot()
                except Exception:
                    snapshot = None
                self._last_snapshot = snapshot if isinstance(snapshot, dict) else None
                try:
                    self._last_snapshot_redacted = redact_snapshot_for_prompt(
                        self._last_snapshot or {},
                        max_elements=12,
                        max_ocr_chars=650,
                    )
                except Exception:
                    self._last_snapshot_redacted = "(unavailable)"

                compact_parts = []
                try:
                    redacted_lines = [l.strip() for l in self._last_snapshot_redacted.splitlines() if l.strip()]
                    if redacted_lines:
                        compact_parts.append(redacted_lines[0])
                    if len(redacted_lines) >= 4:
                        compact_parts.append(redacted_lines[3])
                except Exception:
                    compact_parts = []
                compact = " | ".join(compact_parts) if compact_parts else "(unavailable)"
                self._snapshot_trace_line = f"perception_snapshot: {compact}"

            try:
                self._last_tool_trace = [self._snapshot_trace_line]
                if ocr_line:
                    self._last_tool_trace.append(ocr_line)
            except Exception:
                self._last_tool_trace = [self._snapshot_trace_line]

            prompt = self._build_prompt(command)
            response = self.llm_callable(
                prompt,
                {
                    "persona": self.personality_manager.persona,
                    "reasoning": "User asked about what is on the screen; use the Perception Snapshot (including OCR/UIA) to answer.",
                },
            )
            final = self._apply_personality(response)
            self.memory.add_turn(command, final)
            return CommandResult(final_response=final)

        if outcome.route == "capability":
            chosen = outcome.capability or cap_key
            response = self.dispatcher.dispatch(chosen, command, normalized_lower)
            try:
                self._last_tool_trace = [
                    self._snapshot_trace_line,
                    *list(getattr(self.dispatcher, "last_tool_trace", []) or []),
                ]
            except Exception:
                self._last_tool_trace = [self._snapshot_trace_line]

            if response:
                final = self._apply_personality(response)
                self.memory.add_turn(command, final)
                return CommandResult(final_response=final)

        if outcome.route == "llm":
            prompt = self._build_prompt(command)
            response = self.llm_callable(
                prompt,
                {
                    "persona": self.personality_manager.persona,
                    "reasoning": outcome.justification,
                },
            )
            final_response = self._apply_personality(response)
            self.memory.add_turn(command, final_response)
            return CommandResult(final_response=final_response)

        # Intent classification
        intent = self.dispatcher.registry.classify(normalized_lower)
        if intent.intent_type == "email":
            response = self._handle_email(intent.entities.get("query", ""))
            final = self._apply_personality(response)
            self.memory.add_turn(command, final)
            return CommandResult(final_response=final)

        # Capability lookup + dispatch
        cap_key, _ = self.dispatcher.registry.match_intent(normalized_lower)
        response = self.dispatcher.dispatch(cap_key, command, normalized_lower)

        try:
            self._last_tool_trace = [
                self._snapshot_trace_line,
                *list(getattr(self.dispatcher, "last_tool_trace", []) or []),
            ]
        except Exception:
            self._last_tool_trace = [self._snapshot_trace_line]

        # LLM fallback
        if not response:
            prompt = self._build_prompt(command)
            response = self.llm_callable(prompt, {"persona": self.personality_manager.persona})

        final_response = self._apply_personality(response)
        try:
            budget = getattr(self, "_word_budget", None)
            if isinstance(budget, int) and budget > 0:
                final_response = self._enforce_word_budget(final_response, budget)
        except Exception:
            pass
        self.memory.add_turn(command, final_response)
        return CommandResult(final_response=final_response)

    def _enforce_word_budget(self, text: str, budget: int) -> str:
        txt = (text or "").strip()
        if not txt:
            return txt

        words = txt.split()
        if len(words) <= budget:
            return txt

        suffix = 'Say "more" if you want a longer explanation.'
        suffix_words = suffix.split()
        keep = max(5, budget - len(suffix_words))

        trimmed = " ".join(words[:keep])
        last_punct = max(trimmed.rfind("."), trimmed.rfind("!"), trimmed.rfind("?"))
        if last_punct >= 0 and last_punct > max(0, len(trimmed) - 180):
            trimmed = trimmed[: last_punct + 1]
        else:
            if not trimmed.endswith((".", "!", "?")):
                trimmed = trimmed + "."

        out = f"{trimmed} {suffix}".strip()
        out_words = out.split()
        if len(out_words) > budget:
            out = " ".join(out_words[:budget])
            if not out.endswith((".", "!", "?")):
                out += "."
        return out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_prompt(self, command: str) -> str:
        from core.llm_sanitizer import sanitize_for_llm
        
        # SECURITY: Sanitize all inputs before building prompt
        sanitized = sanitize_for_llm(
            text=command,
            snapshot=self._last_snapshot_redacted,
            tool_trace=self._last_tool_trace,
            memory=None  # Will sanitize memory separately
        )
        
        # a) System instructions
        parts = [
            "You are JARVIS — calm, precise, and highly intelligent.",
            "You belong to Shreesh and live on his computer. Be formal, confident, concise.",
            "Important: Use only real, verified capabilities. Do not guess or hallucinate.",
            "Prefer tools/automations when available; otherwise answer directly.",
            (
                "Critical: You MUST NOT claim you performed an external action (opened a website, clicked, typed, sent a message, took a screenshot, etc.) "
                "unless it appears in the 'Tool results (authoritative)' section below. "
                "If no tool result is present for an action, speak in future tense (e.g., 'I can...', 'I will...') or ask for permission/clarification."
            ),
        ]

        # b) Short buffer (configured by MemoryController.short_term_limit)
        short_term = self.memory.get_short_term_context()
        if short_term:
            from core.llm_sanitizer import strip_credentials_from_memory
            short_term = strip_credentials_from_memory(short_term)
            parts.append("\nRecent conversation:")
            parts.append(short_term)

        # c) Top-K relevant long-term memory (already salience/recency filtered)
        long_term = self.memory.get_long_term_memories(command, top_k=self.memory.long_term_results)
        if short_term and long_term:
            st_lower = short_term.lower()
            long_term = [s for s in long_term if s.lower() not in st_lower]
        if long_term:
            from core.llm_sanitizer import strip_credentials_from_memory
            long_term = [strip_credentials_from_memory(s) for s in long_term]
            parts.append("\nRelevant past knowledge:")
            parts.append("\n".join([f"- {s}" for s in long_term]))

        # Optional: recent actions summary
        recent_actions = self.memory.summarize_recent_actions()
        if recent_actions:
            from core.llm_sanitizer import strip_credentials_from_text
            recent_actions = strip_credentials_from_text(recent_actions)
            parts.append("\nRecent system actions:")
            parts.append(recent_actions)

        parts.append("\n## Perception Snapshot (authoritative)")
        parts.append(sanitized["snapshot"] or "(unavailable)")

        budget = getattr(self, "_word_budget", None)
        if isinstance(budget, int) and budget > 0:
            parts.append("\n## Response Budget (authoritative)")
            parts.append(
                (
                    f"You MUST respond in <= {budget} words. "
                    "Write complete sentences and do NOT end mid-sentence or with trailing ellipses. "
                    "Do NOT paste long raw OCR text; instead, paraphrase what it suggests and quote at most a few short UI labels if needed. "
                    "If the answer would exceed the limit, prioritize the most important points and end with: "
                    "'Say \"more\" if you want a longer explanation.'"
                )
            )

        tool_trace = sanitized["tool_trace"] or []
        tool_trace = [t for t in tool_trace if isinstance(t, str) and t.strip()]
        parts.append("\nTool results (authoritative):")
        if tool_trace:
            parts.append("\n".join([f"- {t}" for t in tool_trace]))
        else:
            parts.append("- (none)")

        # d) Current user command + guardrails (sanitized)
        parts.append(f"\nUser said: {sanitized['text']}")
        parts.append(
            "Guidelines: Be decisive. Use tools when needed. Never invent numeric facts; if numbers are required, they must come from a tool and cite the tool."
        )
        parts.append("Do not start your response with 'To summarize:' or similar filler.")
        return "\n".join(parts)

    def _decide_word_budget(self, command: str) -> int:
        try:
            default_budget = int(os.getenv("JARVIS_WORD_BUDGET_DEFAULT", "130"))
            short_budget = int(os.getenv("JARVIS_WORD_BUDGET_SHORT", "80"))
            long_budget = int(os.getenv("JARVIS_WORD_BUDGET_LONG", "420"))
        except Exception:
            default_budget, short_budget, long_budget = 130, 80, 420

        cmd = (command or "").strip()
        lower = cmd.lower()

        try:
            m = _EXPLICIT_WORD_BUDGET_PATTERN.search(cmd)
            if m:
                n = int(m.group(1))
                return max(30, min(2000, n))
        except Exception:
            pass

        if any(cue in lower for cue in _SHORT_RESPONSE_CUES):
            return short_budget

        if any(cue in lower for cue in _LONG_RESPONSE_CUES):
            return long_budget

        try:
            if len(lower) >= 70:
                how_why = any(tok in lower for tok in ("how ", "how?", "why ", "why?", "explain", "steps", "step "))
                multi_clause = lower.count(" and ") >= 2 or lower.count(" then ") >= 1
                if how_why or multi_clause:
                    return long_budget
        except Exception:
            pass

        if _SCREEN_QUERY_PATTERN.search(cmd) is not None:
            return min(default_budget, 150)

        return default_budget

    def _apply_personality(self, response: str) -> str:
        return self.personality_manager.apply(response)

    def _handle_email(self, query: str) -> str:
        intent = parse_email_intent(query)
        if not intent:
            return "I couldn't extract the recipient and subject for that email."

        result = self.automation.gmail_template.compose_email()
        if not result.success:
            return f"I couldn't open Gmail compose: {result.message}"

        return "Gmail compose window prepared."
