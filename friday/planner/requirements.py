"""Requirements Discovery — the front door of the General Operator.

Per ADR-021: Before planning HOW to do something, FRIDAY must reason about
WHAT must be true for the goal to be complete. This is requirements thinking,
not workflow matching.

Goal: "Research France's position and email a position paper"
Requirements:
  - Information about France's position must be gathered
  - Sources must be official/credible
  - Facts must be extracted
  - Content must be synthesized into a paper
  - Document must be created and formatted
  - Document must be delivered via email
  - Delivery must be verified

Each requirement is then satisfied by composing capabilities. The same
requirements-discovery handles ANY goal because it reasons about completion
conditions, not task templates.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Requirement:
    """A single condition that must be true for the goal to be complete."""

    description: str          # "Information about X must be gathered"
    satisfied: bool = False
    evidence: str = ""        # What proves this requirement is met
    blocking: bool = True     # Must this be done before the goal is complete?


@dataclass
class RequirementSet:
    """The full set of requirements for a goal."""

    goal: str
    requirements: List[Requirement] = field(default_factory=list)
    reasoning: str = ""
    from_llm: bool = False

    @property
    def all_satisfied(self) -> bool:
        return all(r.satisfied for r in self.requirements if r.blocking)

    @property
    def unsatisfied(self) -> List[Requirement]:
        return [r for r in self.requirements if not r.satisfied and r.blocking]

    @property
    def completion_ratio(self) -> float:
        blocking = [r for r in self.requirements if r.blocking]
        if not blocking:
            return 1.0
        return sum(1 for r in blocking if r.satisfied) / len(blocking)


class RequirementsDiscovery:
    """Discovers what must be true for an arbitrary goal to be complete.

    This is NOT workflow matching. The LLM reasons about completion
    conditions for ANY goal. The output drives capability planning.

    Usage:
        discovery = RequirementsDiscovery(model_router=router)
        reqs = discovery.discover("Email a report about Q3 sales to my boss")
        # reqs.requirements = [
        #   "Q3 sales data must be gathered",
        #   "Data must be analyzed/summarized",
        #   "A report document must be created",
        #   "The report must be sent via email to the boss",
        #   "Email delivery must be confirmed"
        # ]
    """

    SYSTEM_PROMPT = (
        "You are the requirements-reasoning engine of a general computer operator AI. "
        "Given a user's goal, determine WHAT MUST BE TRUE for the goal to be considered complete. "
        "Do NOT think about applications, software, or buttons. "
        "Think about completion conditions and information/output requirements. "
        "Each requirement is a state that must hold when the goal is done.\n\n"
        "Think like this: 'For this goal to be complete, the following must be true...'\n\n"
        "Respond ONLY with a JSON array of requirement strings, ordered by dependency. "
        "Be precise and complete but not redundant. 3-8 requirements typically.\n\n"
        "Example goal: 'Research the best laptop under 80k and create a comparison report'\n"
        'Response: ["Information about laptops under 80k must be gathered from sources", '
        '"Specifications and prices must be extracted for comparison", '
        '"At least 2-3 options must be compared on key criteria", '
        '"A structured comparison report must be synthesized", '
        '"The report must be saved as a document file"]'
    )

    def __init__(self, model_router=None) -> None:
        self._router = model_router

    def discover(self, goal: str) -> RequirementSet:
        """Discover requirements for a goal (sync wrapper).

        Safe across contexts: if an event loop is already running (e.g. inside
        async code), run the coroutine in a separate thread; otherwise use
        asyncio.run directly. Avoids the blocking-shutdown deadlock the old
        context-manager pattern caused on timeout.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — safe to use asyncio.run directly.
            return asyncio.run(self.discover_async(goal))

        # A loop is running — offload to a worker thread that owns its own loop.
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(asyncio.run, self.discover_async(goal))
            return future.result(timeout=60)
        except Exception:
            return self._fallback(goal)
        finally:
            pool.shutdown(wait=False)

    async def discover_async(self, goal: str) -> RequirementSet:
        """Discover requirements using LLM reasoning."""
        if not self._router:
            return self._fallback(goal)

        try:
            from friday.models.router import ModelCapability
            response = await self._router.complete(
                f"Goal: {goal}",
                capability=ModelCapability.CLASSIFICATION,
                # Fast, accurate structured decomposition. gpt-oss-120b answers in
                # ~1-2s with clean JSON. (The former qwen3-next-80b now hangs to
                # timeout on the free NIM tier.)
                model="openai/gpt-oss-120b",
                max_tokens=350,
                temperature=0.2,
                system_prompt=self.SYSTEM_PROMPT,
            )
            reqs = self._parse(response.text)
            if reqs:
                reqs = self._augment_structural(goal, reqs)
                return RequirementSet(
                    goal=goal,
                    requirements=reqs,
                    reasoning=f"Discovered {len(reqs)} requirements",
                    from_llm=True,
                )
        except Exception:
            pass

        return self._fallback(goal)

    def _augment_structural(self, goal: str, reqs: List[Requirement]) -> List[Requirement]:
        """Guarantee goal-derived structural requirements the LLM may omit.

        If the goal explicitly asks to SAVE to a file or DELIVER/send, those are
        hard completion conditions. The LLM sometimes phrases requirements
        vaguely (all PRODUCE), which would let the operator falsely complete
        without a real file. We inject the missing structural requirement so the
        Evidence Law enforces it (a file requires a real file artifact; delivery
        requires confirmation).
        """
        from friday.verification.evidence_law import classify_requirement, RequirementKind

        g = goal.lower()
        kinds = {classify_requirement(r.description) for r in reqs}

        wants_file = any(kw in g for kw in
                         ["save", "file", "document", ".txt", ".md", ".docx",
                          ".csv", ".xlsx", "spreadsheet", "report", "write"])
        if wants_file and RequirementKind.FILE not in kinds:
            reqs.append(Requirement(
                description="The output must be saved to a file on disk",
                blocking=True,
            ))

        wants_deliver = any(kw in g for kw in
                            ["email", "send", "deliver", "message", "dm "])
        if wants_deliver and RequirementKind.DELIVER not in kinds:
            reqs.append(Requirement(
                description="The output must be delivered to the recipient",
                blocking=True,
            ))

        # M17: guarantee a PRODUCE requirement for synthesis / gather+save goals.
        reqs = self._ensure_produce_requirement(goal, reqs)

        return reqs

    def _parse(self, text: str) -> List[Requirement]:
        """Parse the LLM JSON array of requirement strings."""
        try:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start < 0 or end <= start:
                return []
            data = json.loads(text[start:end])
            return [
                Requirement(description=str(item).strip())
                for item in data
                if isinstance(item, str) and item.strip()
            ]
        except (json.JSONDecodeError, ValueError):
            return []

    def _fallback(self, goal: str) -> RequirementSet:
        """Minimal generic requirements when LLM unavailable.

        Even the fallback is requirement-shaped, not workflow-shaped.
        """
        reqs = [Requirement(description=f"The goal '{goal}' must be addressed")]

        goal_lower = goal.lower()
        if any(kw in goal_lower for kw in ["research", "find", "search", "look up"]):
            reqs.insert(0, Requirement(description="Relevant information must be gathered"))
        if any(kw in goal_lower for kw in
               ["write", "create", "generate", "report", "summary",
                # M17 synthesis verbs/nouns (data extension, not per-topic branching):
                "produce", "summariz", "document", "paper", "cite", "citation",
                "essay", "brief", "compose", "draft"]):
            reqs.append(Requirement(description="Content must be produced"))
        if any(kw in goal_lower for kw in ["save", "file", "document"]):
            reqs.append(Requirement(description="Output must be saved to a file"))
        if any(kw in goal_lower for kw in ["email", "send", "message"]):
            reqs.append(Requirement(description="Output must be delivered to the recipient"))

        # M17: guarantee a PRODUCE requirement for synthesis / gather+save goals.
        reqs = self._ensure_produce_requirement(goal, reqs)

        return RequirementSet(
            goal=goal,
            requirements=reqs,
            reasoning="Fallback requirements (LLM unavailable)",
            from_llm=False,
        )

    def _ensure_produce_requirement(self, goal: str, reqs: List[Requirement]) -> List[Requirement]:
        """M17: inject a PRODUCE requirement when a goal implies synthesis (a synthesis
        verb) or has a gather+save shape, and none exists yet."""
        from friday.verification.evidence_law import classify_requirement, RequirementKind
        g = goal.lower()
        if RequirementKind.PRODUCE in {classify_requirement(r.description) for r in reqs}:
            return reqs
        synthesis_verb = any(k in g for k in ["produce","summariz","document","paper","cite","citation","essay","brief"])
        implies_gather = any(k in g for k in ["research","find","search","look up","gather"])
        implies_save = any(k in g for k in ["save","file","document",".txt",".md",".docx",".csv",".xlsx","spreadsheet","report"])
        if synthesis_verb or (implies_gather and implies_save):
            reqs.append(Requirement(description="A written summary must be synthesized and composed", blocking=True))
        return reqs
