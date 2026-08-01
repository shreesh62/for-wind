"""M19 (A2.7) — deterministic retrieval-router quality benchmark.

Measures the Retrieval Router's routing quality hermetically: a fixed set of
synthetic scenarios is routed through a *real* ``RetrievalRouter`` (each scenario
registers its own in-memory synthetic multi-tier sources), and the planted
"relevant" item is checked for coverage, correct-tier attribution, de-duplication,
and rank. This exposes the routing-quality metrics the audit asks every capability
to surface (coverage / correct-tier-rate / dedup-rate / mean-rank).

Deterministic + hermetic: NO LLM, NO network, NO wall-clock dependence. Synthetic
sources live entirely in memory (no disk I/O). Identical runs yield identical
metrics.

POLICY: This benchmark is domain-general (Axiom 15 — no application/browser/site
identity, only generic topics). It is NOT part of the 5-domain competence
scorecard and is NEVER written into the committed competence baseline (mirrors the
M23 web-independence / M24 recovery-rate suite policy).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from friday.memory.interfaces import MemoryEntry, MemoryTier
from friday.memory.retrieval_router import RetrievalRouter, RetrievedItem

# Sentinel rank for a scenario whose planted relevant item never appears in the
# routed results. Chosen large so it visibly dominates any real 1-based position
# without depending on wall-clock or run order (keeps the mean deterministic).
MISSING_RANK: int = 1_000_000


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> frozenset:
    """Deterministic lowercase alphanumeric tokenization (no locale/time)."""
    return frozenset(_TOKEN_RE.findall(text.lower()))


# --------------------------------------------------------------------------- specs


@dataclass(frozen=True)
class PlantedEntry:
    """One synthetic memory entry planted in a source for a scenario."""

    entry_id: str
    content: str
    tier: str                 # MemoryTier value (e.g. "episodic", "failure")
    timestamp: float = 0.0     # fixed (never wall-clock) — determinism


@dataclass(frozen=True)
class SyntheticSourceSpec:
    """A named, tiered synthetic source and the entries planted in it."""

    name: str
    tier: str                          # MemoryTier value the source is registered under
    entries: Tuple[PlantedEntry, ...]
    weight: float = 1.0


@dataclass(frozen=True)
class RetrievalScenario:
    """A synthetic routing scenario with a single planted relevant target.

    A ``query`` is routed across ``sources`` (each with entries planted across
    tiers). Exactly one planted entry — identified by ``relevant_entry_id`` and
    living in ``relevant_tier`` — is the item the router is expected to retrieve
    and attribute to the correct tier.
    """

    scenario_id: str
    query: str
    sources: Tuple[SyntheticSourceSpec, ...]
    relevant_entry_id: str
    relevant_tier: str
    top_k: int = 10
    per_source_k: int = 10


# ------------------------------------------------------------------- fake source


class _SyntheticSource:
    """In-memory source honoring ``retrieve(query, top_k) -> List[MemoryEntry]``.

    Relevance is a deterministic keyword-overlap score against the query; entries
    with zero overlap are omitted (a source contributes only what matches). Ties
    break by planted order, so results are fully reproducible with no randomness,
    disk, or clock involvement.
    """

    def __init__(self, entries: Tuple[PlantedEntry, ...]) -> None:
        self._entries = entries

    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        q = _tokens(query)
        scored: List[Tuple[int, int, PlantedEntry]] = []
        for idx, e in enumerate(self._entries):
            overlap = len(q & _tokens(e.content))
            if overlap > 0:
                scored.append((overlap, idx, e))
        # Higher overlap first; stable tie-break by planted order (deterministic).
        scored.sort(key=lambda t: (-t[0], t[1]))
        out: List[MemoryEntry] = []
        for overlap, _idx, e in scored[: max(0, top_k)]:
            out.append(
                MemoryEntry(
                    content=e.content,
                    tier=MemoryTier(e.tier),
                    timestamp=e.timestamp,
                    relevance_score=float(overlap),
                    entry_id=e.entry_id,
                )
            )
        return out


# ----------------------------------------------------------------------- metrics


@dataclass
class RetrievalMetrics:
    """Aggregate routing-quality outcome of a benchmark run (JSON-projectable)."""

    total_scenarios: int = 0
    covered: int = 0               # relevant item present in routed results
    correct_tier: int = 0          # relevant item attributed to its planted tier
    dedup_clean: int = 0           # scenarios whose output had no duplicate keys
    ranks: List[int] = field(default_factory=list)  # 1-based rank of relevant item
    by_tier: Dict[str, int] = field(default_factory=dict)  # relevant-item tier distribution

    @property
    def coverage(self) -> float:
        """Fraction of scenarios where the relevant item was retrieved, in [0,1]."""
        if self.total_scenarios <= 0:
            return 0.0
        return max(0.0, min(1.0, self.covered / self.total_scenarios))

    @property
    def correct_tier_rate(self) -> float:
        """Fraction of scenarios where the relevant item had the right tier, in [0,1]."""
        if self.total_scenarios <= 0:
            return 0.0
        return max(0.0, min(1.0, self.correct_tier / self.total_scenarios))

    @property
    def dedup_rate(self) -> float:
        """Fraction of scenarios whose routed output had no duplicate keys, in [0,1]."""
        if self.total_scenarios <= 0:
            return 0.0
        return max(0.0, min(1.0, self.dedup_clean / self.total_scenarios))

    @property
    def mean_rank(self) -> float:
        """Mean 1-based rank of the planted relevant item across scenarios.

        Scenarios where the relevant item is missing contribute ``MISSING_RANK``
        (a large sentinel), so a lower mean reflects better routing.
        """
        if not self.ranks:
            return 0.0
        return sum(self.ranks) / len(self.ranks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_scenarios": self.total_scenarios,
            "covered": self.covered,
            "correct_tier": self.correct_tier,
            "dedup_clean": self.dedup_clean,
            "coverage": round(self.coverage, 4),
            "correct_tier_rate": round(self.correct_tier_rate, 4),
            "dedup_rate": round(self.dedup_rate, 4),
            "mean_rank": round(self.mean_rank, 4),
            "missing_rank_sentinel": MISSING_RANK,
            "ranks": list(self.ranks),
            "by_tier": dict(self.by_tier),
        }

    def to_markdown(self) -> str:
        lines = [
            "# Retrieval Router Benchmark",
            "",
            f"- Scenarios: {self.total_scenarios}",
            f"- Coverage: {self.covered}/{self.total_scenarios} ({self.coverage:.4f})",
            (
                f"- Correct-tier attributions: {self.correct_tier}/{self.total_scenarios} "
                f"({self.correct_tier_rate:.4f})"
            ),
            (
                f"- Dedup-clean outputs: {self.dedup_clean}/{self.total_scenarios} "
                f"({self.dedup_rate:.4f})"
            ),
            f"- Mean rank of relevant item: {self.mean_rank:.4f} "
            f"(missing = {MISSING_RANK})",
            "",
            "| Relevant-item tier | count |",
            "|---|---|",
        ]
        for tier, count in sorted(self.by_tier.items()):
            lines.append(f"| {tier} | {count} |")
        return "\n".join(lines)


# --------------------------------------------------------------------- scenarios


def default_retrieval_scenarios() -> Tuple[RetrievalScenario, ...]:
    """A fixed, domain-general scenario set (generic topics only — Axiom 15).

    Every scenario registers multiple tiered synthetic sources and plants exactly
    one relevant target. Several scenarios deliberately plant a duplicate entry_id
    across two sources so the router's de-duplication is exercised.
    """
    return (
        # 1) Relevant item in the semantic tier; noise in episodic; a failure note.
        RetrievalScenario(
            scenario_id="photosynthesis",
            query="how plants convert sunlight into energy",
            sources=(
                SyntheticSourceSpec(
                    "semantic-facts", MemoryTier.SEMANTIC.value,
                    (
                        PlantedEntry("sem-photo", "plants convert sunlight into chemical energy", "semantic"),
                        PlantedEntry("sem-water", "the water cycle moves moisture through the air", "semantic"),
                    ),
                ),
                SyntheticSourceSpec(
                    "episodic-log", MemoryTier.EPISODIC.value,
                    (
                        PlantedEntry("epi-walk", "went for a long walk in the afternoon", "episodic"),
                    ),
                ),
                SyntheticSourceSpec(
                    "failure-notes", MemoryTier.FAILURE.value,
                    (
                        PlantedEntry("fail-net", "a network timeout interrupted a prior task", "failure"),
                    ),
                ),
            ),
            relevant_entry_id="sem-photo",
            relevant_tier="semantic",
        ),
        # 2) Relevant item in the failure tier; unfiltered route must surface it.
        RetrievalScenario(
            scenario_id="repeated-failure",
            query="saving a file failed with permission denied",
            sources=(
                SyntheticSourceSpec(
                    "failure-notes", MemoryTier.FAILURE.value,
                    (
                        PlantedEntry("fail-perm", "saving a file failed with permission denied error", "failure"),
                        PlantedEntry("fail-dns", "a lookup failed to resolve a name", "failure"),
                    ),
                ),
                SyntheticSourceSpec(
                    "semantic-facts", MemoryTier.SEMANTIC.value,
                    (
                        PlantedEntry("sem-file", "a file is a named collection of stored bytes", "semantic"),
                    ),
                ),
            ),
            relevant_entry_id="fail-perm",
            relevant_tier="failure",
        ),
        # 3) Relevant item in the procedural tier; duplicate entry_id across two
        #    sources exercises de-duplication.
        RetrievalScenario(
            scenario_id="bread-recipe",
            query="steps to bake a simple loaf of bread",
            sources=(
                SyntheticSourceSpec(
                    "procedural-howto", MemoryTier.PROCEDURAL.value,
                    (
                        PlantedEntry("proc-bread", "steps to bake a simple loaf of bread: mix, knead, rise, bake", "procedural"),
                    ),
                ),
                SyntheticSourceSpec(
                    "procedural-mirror", MemoryTier.PROCEDURAL.value,
                    (
                        # Same entry_id as above → must be de-duplicated in output.
                        PlantedEntry("proc-bread", "steps to bake a simple loaf of bread: mix, knead, rise, bake", "procedural"),
                        PlantedEntry("proc-soup", "steps to make a simple soup from vegetables", "procedural"),
                    ),
                ),
            ),
            relevant_entry_id="proc-bread",
            relevant_tier="procedural",
        ),
        # 4) Relevant item in the episodic tier; a weighted semantic source competes.
        RetrievalScenario(
            scenario_id="meeting-notes",
            query="notes from the planning meeting about the schedule",
            sources=(
                SyntheticSourceSpec(
                    "episodic-log", MemoryTier.EPISODIC.value,
                    (
                        PlantedEntry("epi-meeting", "notes from the planning meeting about the schedule", "episodic"),
                        PlantedEntry("epi-lunch", "had lunch after the meeting", "episodic"),
                    ),
                    weight=2.0,
                ),
                SyntheticSourceSpec(
                    "semantic-facts", MemoryTier.SEMANTIC.value,
                    (
                        PlantedEntry("sem-schedule", "a schedule is a plan for timing of tasks", "semantic"),
                    ),
                ),
            ),
            relevant_entry_id="epi-meeting",
            relevant_tier="episodic",
        ),
        # 5) Relevant item in the semantic tier with interleaved failure + episodic.
        RetrievalScenario(
            scenario_id="prime-numbers",
            query="what makes a number a prime number",
            sources=(
                SyntheticSourceSpec(
                    "semantic-facts", MemoryTier.SEMANTIC.value,
                    (
                        PlantedEntry("sem-prime", "a prime number is divisible only by one and itself", "semantic"),
                        PlantedEntry("sem-even", "an even number is divisible by two", "semantic"),
                    ),
                ),
                SyntheticSourceSpec(
                    "failure-notes", MemoryTier.FAILURE.value,
                    (
                        PlantedEntry("fail-parse", "a prior parse of a number string failed", "failure"),
                    ),
                ),
                SyntheticSourceSpec(
                    "episodic-log", MemoryTier.EPISODIC.value,
                    (
                        PlantedEntry("epi-count", "counted a number of items yesterday", "episodic"),
                    ),
                ),
            ),
            relevant_entry_id="sem-prime",
            relevant_tier="semantic",
        ),
        # 6) Relevant item in the failure tier under a FAILURE-only tier filter.
        RetrievalScenario(
            scenario_id="failure-filter",
            query="an upload was rejected because the size limit was exceeded",
            sources=(
                SyntheticSourceSpec(
                    "failure-notes", MemoryTier.FAILURE.value,
                    (
                        PlantedEntry("fail-size", "an upload was rejected because the size limit was exceeded", "failure"),
                    ),
                ),
                SyntheticSourceSpec(
                    "semantic-facts", MemoryTier.SEMANTIC.value,
                    (
                        # Shares terms with the query but must be excluded by the filter.
                        PlantedEntry("sem-upload", "an upload transfers data to a remote store", "semantic"),
                    ),
                ),
            ),
            relevant_entry_id="fail-size",
            relevant_tier="failure",
            # Only the failure tier is queried.
        ),
    )


# Scenarios that must be routed with a tier filter (kept as data, not code branches).
_TIER_FILTERED: Dict[str, Tuple[MemoryTier, ...]] = {
    "failure-filter": (MemoryTier.FAILURE,),
}


# ---------------------------------------------------------------------- benchmark


class RetrievalBenchmark:
    """Runs retrieval scenarios through a real ``RetrievalRouter`` and scores them."""

    def __init__(
        self, scenarios: Optional[Tuple[RetrievalScenario, ...]] = None
    ) -> None:
        self._scenarios = (
            scenarios if scenarios is not None else default_retrieval_scenarios()
        )

    def run(self) -> RetrievalMetrics:
        """Route every scenario and aggregate routing-quality metrics."""
        metrics = RetrievalMetrics()

        for sc in self._scenarios:
            metrics.total_scenarios += 1
            metrics.by_tier[sc.relevant_tier] = (
                metrics.by_tier.get(sc.relevant_tier, 0) + 1
            )

            router = RetrievalRouter()
            for spec in sc.sources:
                router.register_source(
                    spec.name,
                    MemoryTier(spec.tier),
                    _SyntheticSource(spec.entries),
                    weight=spec.weight,
                )

            tier_filter = _TIER_FILTERED.get(sc.scenario_id)
            results = router.route(
                sc.query,
                tiers=tier_filter,
                top_k=sc.top_k,
                per_source_k=sc.per_source_k,
            )

            self._score_scenario(sc, results, metrics)

        return metrics

    @staticmethod
    def _score_scenario(
        sc: RetrievalScenario,
        results: List[RetrievedItem],
        metrics: RetrievalMetrics,
    ) -> None:
        # De-dup cleanliness: the router must not emit duplicate keys.
        keys = [it.entry_id or f"{it.tier}:{it.content}" for it in results]
        if len(keys) == len(set(keys)):
            metrics.dedup_clean += 1

        # Locate the planted relevant item (1-based rank) by entry_id.
        rank = MISSING_RANK
        matched: Optional[RetrievedItem] = None
        for position, it in enumerate(results, start=1):
            if it.entry_id == sc.relevant_entry_id:
                rank = position
                matched = it
                break

        metrics.ranks.append(rank)
        if matched is not None:
            metrics.covered += 1
            if matched.tier == sc.relevant_tier:
                metrics.correct_tier += 1
