"""Ch 14/52 — MemoryRuntime: kernel bridge for the existing FridayMemory.

Reflection proposes candidates; Memory DECIDES. Only VERIFIED experience is
integrated (Ch 14.22). Memory NEVER overrides reality (Ch 14.16). The 7 memory
modules are wrapped, never rewritten.

This runtime satisfies the RuntimeContract so the CognitiveKernel can
`register_runtime` it, subscribes to `memory.candidate` kernel events, decides
accept/reject/merge/forget, and delegates all storage to the existing
`FridayMemory` (`record_turn`/`record_pattern`/`remember_fact`). If FridayMemory
cannot be constructed (e.g. filesystem unavailable under DRY_RUN) it degrades to
an in-memory no-op shim and reports a `degraded` health status while continuing
to publish decisions. FridayMemory is imported lazily so importing this module
never triggers disk I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from friday.events.event import Event, make_event
from friday.kernel.contracts.runtime import RuntimeContract


class MemoryDecision(str, Enum):
    """Ch 14 — the four outcomes Memory can choose for a candidate."""

    ACCEPT = "accept"
    REJECT = "reject"
    MERGE = "merge"
    FORGET = "forget"


@dataclass(frozen=True)
class CandidateVerdict:
    """The decision Memory made about one candidate (audit-grade, pure)."""

    decision: MemoryDecision
    reason: str
    tier: str = ""          # working/episodic/procedural/semantic when accepted/merged
    entry_ref: str = ""


# Map candidate "kind" → the long-term memory tier it is routed into.
_KIND_TO_TIER: Dict[str, str] = {
    "turn": "episodic",
    "pattern": "procedural",
    "fact": "semantic",
}


class _NoOpMemory:
    """In-memory no-op stand-in for FridayMemory used in degraded mode.

    Provides the subset of the FridayMemory surface the runtime touches so a
    missing/unavailable backing store never crashes the kernel tick loop.
    """

    def record_turn(self, *args: Any, **kwargs: Any) -> None:
        return None

    def record_pattern(self, *args: Any, **kwargs: Any) -> None:
        return None

    def remember_fact(self, *args: Any, **kwargs: Any) -> None:
        return None

    def get_context(self, query: str = "") -> Any:
        class _EmptyContext:
            def to_prompt_string(self, *a: Any, **k: Any) -> str:
                return ""

        return _EmptyContext()

    def suggest_action_strategy(self, *args: Any, **kwargs: Any) -> Optional[List[str]]:
        return None

    def reset_session(self) -> None:
        return None


class MemoryRuntime(RuntimeContract):
    """Wraps FridayMemory behind the kernel RuntimeContract."""

    def __init__(
        self,
        memory: Optional[Any] = None,
        *,
        decay_interval_ticks: int = 500,
    ) -> None:
        # Injected memory (e.g. a fake in tests) or None to lazily construct.
        self._memory = memory
        self._kernel: Any = None
        self._decay_interval = decay_interval_ticks
        self._verdicts: List[CandidateVerdict] = []
        self._seen_hashes: Set[str] = set()
        self._degraded: bool = False
        self._integrated_count: int = 0

    # --- RuntimeContract ---------------------------------------------------
    @property
    def name(self) -> str:
        return "memory"

    def initialize(self, kernel: Any) -> None:
        self._kernel = kernel
        try:
            kernel.subscribe("memory.candidate", self._on_candidate)
        except Exception:  # noqa: BLE001
            pass

        # Lazily construct the real FridayMemory only if one was not injected.
        # On ANY failure, fall back to an in-memory no-op shim and mark degraded
        # (Req 2.9). Import lazily so importing this module never does disk I/O.
        if self._memory is None:
            try:
                from friday.memory.controller import FridayMemory

                self._memory = FridayMemory()
            except Exception:  # noqa: BLE001
                self._memory = _NoOpMemory()
                self._degraded = True

    def tick(self, logical_time: int) -> None:
        """Periodic forgetting/decay (Ch 14) — never touches reality.

        On the configured decay interval this performs a safe no-op decay
        marker. It deliberately does NOT wipe working memory or touch any World
        Model observation. Never raises into the kernel tick loop.
        """
        try:
            if self._decay_interval > 0 and logical_time > 0:
                if logical_time % self._decay_interval == 0:
                    # Safe decay hook: only invoke an explicit forget hook if the
                    # wrapped memory provides one. Do NOT call reset_session()
                    # (that would wipe working memory). Default: no-op marker.
                    forget = getattr(self._memory, "forget_expired", None)
                    if callable(forget):
                        forget()
        except Exception:  # noqa: BLE001
            # Decay must never crash the tick loop.
            pass

    def observe(self) -> List[Dict[str, Any]]:
        return []

    def receive(self, event: Event) -> None:
        """Kernel routes all events here; only memory.candidate is acted on."""
        try:
            if getattr(event, "event_type", "") == "memory.candidate":
                self._on_candidate(event)
        except Exception:  # noqa: BLE001
            pass

    def publish(self, event: Event) -> None:
        if self._kernel is not None:
            self._kernel.publish_event(event)

    def checkpoint(self) -> Dict[str, Any]:
        """JSON-serializable stats only (no live memory handles)."""
        return {
            "name": "memory",
            "integrated": self._integrated_count,
            "degraded": self._degraded,
            "seen": len(self._seen_hashes),
        }

    def restore(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        self._integrated_count = int(state.get("integrated", 0) or 0)
        self._degraded = bool(state.get("degraded", False))
        seen = state.get("seen", 0)
        # `seen` is stored as a count; nothing to repopulate deterministically,
        # so restore defensively without inventing hash values.
        if isinstance(seen, (list, tuple, set)):
            self._seen_hashes = set(seen)

    def shutdown(self) -> None:
        return None

    def health(self) -> Dict[str, Any]:
        return {
            "status": "degraded" if self._degraded else "ok",
            "integrated": self._integrated_count,
        }

    # --- decision core (pure, testable) ------------------------------------
    def decide(
        self,
        candidate: Dict[str, Any],
        *,
        contradicting_observation: bool = False,
    ) -> CandidateVerdict:
        """Decide accept/reject/merge/forget for one candidate.

        Hard gates (both reject):
        - candidate["verified"] is not True   → REJECT (Req 2.1)
        - contradicting_observation is True   → REJECT (Req 2.2, reality wins)
        Otherwise choose MERGE if a similar entry exists, else ACCEPT (Req 2.3).
        """
        if candidate.get("verified") is not True:
            return CandidateVerdict(
                decision=MemoryDecision.REJECT,
                reason="unverified experience",
            )

        if contradicting_observation is True:
            return CandidateVerdict(
                decision=MemoryDecision.REJECT,
                reason="reality outranks memory",
            )

        kind = candidate.get("kind", "")
        tier = _KIND_TO_TIER.get(kind, "")

        context_hash = candidate.get("context_hash", "")
        if context_hash and context_hash in self._seen_hashes:
            return CandidateVerdict(
                decision=MemoryDecision.MERGE,
                reason="similar entry exists",
                tier=tier,
            )

        return CandidateVerdict(
            decision=MemoryDecision.ACCEPT,
            reason="verified experience",
            tier=tier,
        )

    def _on_candidate(self, event: Event) -> None:
        """Decide, delegate storage to FridayMemory, publish the outcome."""
        try:
            payload = dict(getattr(event, "payload", {}) or {})
            verdict = self.decide(
                payload,
                contradicting_observation=bool(
                    payload.get("contradicting_observation", False)
                ),
            )
            self._verdicts.append(verdict)

            if verdict.decision in (MemoryDecision.ACCEPT, MemoryDecision.MERGE):
                self._integrate(payload, verdict)
                context_hash = payload.get("context_hash", "")
                if context_hash:
                    self._seen_hashes.add(context_hash)
                self.publish(
                    make_event(
                        event_type="memory.integrated",
                        source=self.name,
                        logical_time=getattr(event, "logical_time", 0),
                        payload={
                            "decision": verdict.decision.value,
                            "tier": verdict.tier,
                            "reason": verdict.reason,
                        },
                        parent_id=getattr(event, "id", None),
                    )
                )
            else:
                self.publish(
                    make_event(
                        event_type="memory.rejected",
                        source=self.name,
                        logical_time=getattr(event, "logical_time", 0),
                        payload={"reason": verdict.reason},
                        parent_id=getattr(event, "id", None),
                    )
                )
        except Exception:  # noqa: BLE001
            # A candidate must never crash the kernel tick loop.
            pass

    def _integrate(self, candidate: Dict[str, Any], verdict: CandidateVerdict) -> None:
        """Route to FridayMemory.record_turn/record_pattern/remember_fact by kind.

        Each delegation is wrapped so a degraded/unavailable memory never
        crashes. The 7 memory tiers are wrapped, never reimplemented.
        """
        kind = candidate.get("kind", "")
        content = candidate.get("content", "")

        try:
            if kind == "turn":
                self._memory.record_turn(
                    user_text=content,
                    assistant_response="",
                    mode="friday",
                )
            elif kind == "pattern":
                recorder = getattr(self._memory, "record_pattern", None)
                if callable(recorder):
                    pattern = self._build_action_pattern(candidate)
                    if pattern is not None:
                        recorder(pattern)
                    else:
                        # Best-effort fallback when we cannot build a pattern.
                        self._memory.remember_fact(content, category="reflection")
                else:
                    self._memory.remember_fact(content, category="reflection")
            elif kind == "fact":
                self._memory.remember_fact(content, category="reflection")
            else:
                # Unknown kind — store as a fact so the learning is not lost.
                self._memory.remember_fact(content, category="reflection")
        except Exception:  # noqa: BLE001
            # Degraded memory must not crash integration.
            pass

        self._integrated_count += 1

    @staticmethod
    def _build_action_pattern(candidate: Dict[str, Any]) -> Optional[Any]:
        """Best-effort construction of an ActionPattern from a candidate.

        Imported lazily to avoid import-time coupling; returns None on any
        failure so the caller can fall back to a fact.
        """
        try:
            from friday.memory.procedural import ActionPattern

            return ActionPattern(
                action_type=candidate.get("capability", "") or "pattern",
                target_description=candidate.get("content", ""),
                context_hash=candidate.get("context_hash", ""),
                steps=[candidate.get("content", "")],
            )
        except Exception:  # noqa: BLE001
            return None
