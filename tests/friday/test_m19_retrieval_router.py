"""M19 — Retrieval Router tests (routing / rank / provenance / isolation).

Feature: m19-retrieval-router

The Retrieval Router is one general mechanism over the uniform
``retrieve(query, top_k) -> List[MemoryEntry]`` surface: callers describe WHAT they
want (a query, optionally a tier filter) and the router fans out to registered
sources, normalizes to provenance-carrying ``RetrievedItem``s, merges, rank-scores,
de-duplicates, and returns a single capped list.

Property tests (Hypothesis, >=100 examples) cover Correctness Properties 1-6 from
design.md plus the controller factory (Task 4.1). Real ``JSONFileStore`` /
``FailureMemory`` / ``FridayMemory`` instances are always confined to pytest's
``tmp_path`` — no ``friday_data/`` files are written.
"""

from __future__ import annotations

import json
import uuid
from typing import List

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from friday.memory.controller import FridayMemory, build_retrieval_router
from friday.memory.episodic import Episode
from friday.memory.failure_memory import FailureMemory
from friday.memory.interfaces import MemoryEntry, MemoryTier
from friday.memory.retrieval_router import RetrievalRouter, RetrievedItem


# ----------------------------------------------------------------- test doubles


class FakeSource:
    """In-memory source exposing the uniform retrieve(query, top_k) surface.

    Returns a preset list of ``MemoryEntry`` (ignoring the query text), sliced to
    ``top_k`` — enough for controlled routing/ranking property tests.
    """

    def __init__(self, entries: List[MemoryEntry]) -> None:
        self._entries = list(entries)

    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        return list(self._entries[: max(0, top_k)])


class RaisingSource:
    """A source whose retrieve always raises — models a misbehaving backend."""

    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryEntry]:
        raise RuntimeError("source is down")


TIER_POOL = [
    MemoryTier.WORKING,
    MemoryTier.EPISODIC,
    MemoryTier.PROCEDURAL,
    MemoryTier.SEMANTIC,
    MemoryTier.USER,
    MemoryTier.FAILURE,
]


def _entry(content: str, tier: MemoryTier, entry_id: str = "") -> MemoryEntry:
    return MemoryEntry(content=content, tier=tier, entry_id=entry_id)


# =============================================================== registration


def test_register_rejects_invalid_source():
    # Feature: m19-retrieval-router: fail fast at wiring time (Req 1.2).
    router = RetrievalRouter()
    with pytest.raises(TypeError):
        router.register_source("bad", MemoryTier.EPISODIC, object())


def test_register_replaces_name_and_reports_count_and_tiers():
    # Feature: m19-retrieval-router: name-replacement + count + distinct tiers
    # (Req 1.3, 1.4).
    router = RetrievalRouter()
    router.register_source("s", MemoryTier.EPISODIC, FakeSource([]))
    router.register_source("s", MemoryTier.SEMANTIC, FakeSource([]))  # replace
    assert router.source_count == 1
    assert router.tiers() == [MemoryTier.SEMANTIC]


def test_unregister_returns_bool_and_decrements():
    # Feature: m19-retrieval-router: unregister by name (Req 1.3).
    router = RetrievalRouter()
    router.register_source("s", MemoryTier.EPISODIC, FakeSource([]))
    assert router.unregister("s") is True
    assert router.unregister("s") is False
    assert router.source_count == 0


def test_weight_clamped_non_negative():
    # Feature: m19-retrieval-router: a negative weight clamps to 0 (Req 1.1).
    router = RetrievalRouter()
    router.register_source(
        "s", MemoryTier.EPISODIC, FakeSource([_entry("c", MemoryTier.EPISODIC, "1")]),
        weight=-3.0,
    )
    res = router.route("q")
    assert res and all(it.score == 0.0 for it in res)


def test_retrieved_item_to_dict_json_roundtrip():
    # Feature: m19-retrieval-router: RetrievedItem is JSON-projectable (Req 4.3).
    item = RetrievedItem(
        content="c", tier="episodic", score=0.123456789, source="s",
        entry_id="1", timestamp=1.0, metadata={"k": "v"},
    )
    back = json.loads(json.dumps(item.to_dict()))
    assert back["content"] == "c"
    assert back["source"] == "s"
    assert back["tier"] == "episodic"
    assert back["score"] == round(0.123456789, 6)


# =================================================================== Property 1


@st.composite
def _source_plan(draw):
    n_sources = draw(st.integers(min_value=1, max_value=5))
    plan = []
    for _ in range(n_sources):
        tier = draw(st.sampled_from(TIER_POOL))
        n_entries = draw(st.integers(min_value=0, max_value=4))
        plan.append((tier, n_entries))
    return plan


@settings(max_examples=150)
@given(plan=_source_plan(), filter_size=st.integers(min_value=0, max_value=len(TIER_POOL)))
def test_p1_routing_and_tier_filter(plan, filter_size):
    # Feature: m19-retrieval-router, Property 1: unfiltered route may return any
    # registered tier; a tier filter returns ONLY in-filter tiers, never an
    # out-of-filter tier. Validates: Requirements 2.1, 2.2, 6.3
    router = RetrievalRouter()
    registered_tiers = set()
    for idx, (tier, n_entries) in enumerate(plan):
        entries = [
            _entry(f"c-{idx}-{j}", tier, f"e-{idx}-{j}") for j in range(n_entries)
        ]
        router.register_source(f"src{idx}", tier, FakeSource(entries))
        registered_tiers.add(tier)

    # Unfiltered: every returned item's tier is one of the registered tiers.
    unfiltered = router.route("q", top_k=50, per_source_k=50)
    registered_values = {t.value for t in registered_tiers}
    for it in unfiltered:
        assert it.tier in registered_values

    # Filtered: deterministic subset of the tier pool.
    tier_filter = set(sorted(TIER_POOL, key=lambda t: t.value)[:filter_size])
    filtered = router.route("q", tiers=tier_filter, top_k=50, per_source_k=50)
    allowed = {t.value for t in tier_filter}
    for it in filtered:
        assert it.tier in allowed
    if not tier_filter:
        assert filtered == []


# =================================================================== Property 2


@settings(max_examples=150)
@given(
    n=st.integers(min_value=1, max_value=6),
    w1=st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    w2=st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_p2_weighted_rank_ordering(n, w1, w2):
    # Feature: m19-retrieval-router, Property 2: for two sources returning results
    # at equal positions, the higher-weighted source's item sorts at least as high;
    # the returned scores are non-increasing; length <= top_k.
    # Validates: Requirements 3.1, 3.2, 3.3, 3.4
    w_hi, w_lo = (w1, w2) if w1 >= w2 else (w2, w1)
    hi = FakeSource([_entry(f"hi{i}", MemoryTier.EPISODIC, f"hi{i}") for i in range(n)])
    lo = FakeSource([_entry(f"lo{i}", MemoryTier.SEMANTIC, f"lo{i}") for i in range(n)])
    router = RetrievalRouter()
    router.register_source("HI", MemoryTier.EPISODIC, hi, weight=w_hi)
    router.register_source("LO", MemoryTier.SEMANTIC, lo, weight=w_lo)

    top_k = 2 * n  # keep everything so nothing is dropped by the cap
    res = router.route("q", top_k=top_k, per_source_k=n)

    # Non-increasing in score, and capped.
    scores = [it.score for it in res]
    assert scores == sorted(scores, reverse=True)
    assert len(res) <= top_k

    # Equal-position comparison: higher weight >= lower weight at each rank.
    by_key = {(it.source, it.entry_id): it for it in res}
    for i in range(n):
        hi_item = by_key[("HI", f"hi{i}")]
        lo_item = by_key[("LO", f"lo{i}")]
        assert hi_item.score >= lo_item.score - 1e-9


# =================================================================== Property 3


@st.composite
def _dup_plan(draw):
    n = draw(st.integers(min_value=1, max_value=12))
    out = []
    for _ in range(n):
        eid = draw(st.sampled_from(["", "id-x", "id-y", "id-z"]))
        content = draw(st.sampled_from(["alpha", "beta", "gamma"]))
        tier = draw(st.sampled_from(
            [MemoryTier.EPISODIC, MemoryTier.SEMANTIC, MemoryTier.PROCEDURAL]
        ))
        out.append((eid, content, tier))
    return out


@settings(max_examples=150)
@given(plan=_dup_plan())
def test_p3_provenance_dedup_and_json(plan):
    # Feature: m19-retrieval-router, Property 3: every item carries a registered
    # source + a tier; duplicates (entry_id, else tier+content) appear at most once;
    # to_dict() survives json.dumps. Validates: Requirements 4.1, 4.2, 4.3
    mid = len(plan) // 2
    first, second = plan[:mid], plan[mid:]
    router = RetrievalRouter()
    router.register_source(
        "s1", MemoryTier.EPISODIC,
        FakeSource([_entry(c, t, e) for (e, c, t) in first]),
    )
    router.register_source(
        "s2", MemoryTier.SEMANTIC,
        FakeSource([_entry(c, t, e) for (e, c, t) in second]),
    )
    res = router.route("q", top_k=100, per_source_k=100)

    names = {"s1", "s2"}
    valid_tiers = {
        MemoryTier.EPISODIC.value, MemoryTier.SEMANTIC.value, MemoryTier.PROCEDURAL.value,
    }
    keys = []
    for it in res:
        assert it.source in names            # provenance: registered source name
        assert it.tier and it.tier in valid_tiers  # provenance: tier present + valid
        json.dumps(it.to_dict())             # JSON-projectable (must not raise)
        keys.append(it.entry_id or f"{it.tier}:{it.content}")
    # De-duplication: each dedup key appears at most once.
    assert len(keys) == len(set(keys))


# =================================================================== Property 4


@settings(max_examples=100)
@given(n=st.integers(min_value=0, max_value=5))
def test_p4_failing_source_isolated(n):
    # Feature: m19-retrieval-router, Property 4: a raising source is skipped, route
    # never raises, healthy results are returned, and the failure is recorded in
    # last_errors. Validates: Requirements 5.1, 5.2
    healthy = FakeSource([_entry(f"h{i}", MemoryTier.EPISODIC, f"h{i}") for i in range(n)])
    router = RetrievalRouter()
    router.register_source("healthy", MemoryTier.EPISODIC, healthy)
    router.register_source("bad", MemoryTier.SEMANTIC, RaisingSource())

    res = router.route("q", top_k=10, per_source_k=10)  # must not raise
    assert all(it.source == "healthy" for it in res)
    assert len(res) == n
    assert "bad" in router.last_errors


def test_p4_all_sources_failing_returns_empty_without_raising():
    # Feature: m19-retrieval-router, Property 4: every source failing still yields a
    # (empty) list, never an exception. Validates: Requirements 5.1, 5.2
    router = RetrievalRouter()
    router.register_source("bad1", MemoryTier.EPISODIC, RaisingSource())
    router.register_source("bad2", MemoryTier.SEMANTIC, RaisingSource())
    assert router.route("q") == []
    assert set(router.last_errors) == {"bad1", "bad2"}


# =================================================================== Property 5


def test_p5_no_sources_returns_empty():
    # Feature: m19-retrieval-router, Property 5: no registered sources -> [].
    # Validates: Requirements 2.3
    assert RetrievalRouter().route("q") == []


def test_p5_tier_filter_matching_none_returns_empty():
    # Feature: m19-retrieval-router, Property 5: a filter matching no source -> [].
    # Validates: Requirements 2.3
    router = RetrievalRouter()
    router.register_source(
        "e", MemoryTier.EPISODIC, FakeSource([_entry("c", MemoryTier.EPISODIC, "1")])
    )
    assert router.route("q", tiers={MemoryTier.FAILURE}) == []


@settings(max_examples=120)
@given(
    top_k=st.integers(min_value=-5, max_value=15),
    per_source_k=st.integers(min_value=-5, max_value=15),
    n=st.integers(min_value=0, max_value=8),
)
def test_p5_top_k_and_per_source_k_bounds(top_k, per_source_k, n):
    # Feature: m19-retrieval-router, Property 5: negative/zero top_k & per_source_k
    # respected; result length <= max(0, top_k). Validates: Requirements 2.3, 2.4
    entries = [_entry(f"c{i}", MemoryTier.EPISODIC, f"c{i}") for i in range(n)]
    router = RetrievalRouter()
    router.register_source("e", MemoryTier.EPISODIC, FakeSource(entries))
    res = router.route("q", top_k=top_k, per_source_k=per_source_k)
    assert len(res) <= max(0, top_k)
    assert len(res) <= n
    if top_k <= 0 or per_source_k <= 0:
        assert res == []


# =================================================================== Property 6


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(keyword=st.sampled_from(["tidal", "solar", "wind", "hydro", "nuclear"]))
def test_p6_failure_memory_participation(tmp_path, keyword):
    # Feature: m19-retrieval-router, Property 6: a real FailureMemory registered under
    # FAILURE contributes FAILURE items to an unfiltered route; a {FAILURE} filter
    # returns only those. Validates: Requirements 6.1, 6.2, 6.3
    fm = FailureMemory(store_path=str(tmp_path / f"fm_{uuid.uuid4().hex}.json"))
    fm.record_failure(
        requirement=f"{keyword} energy planning failed",
        domain="verification", capability="research", environment="web",
    )
    router = RetrievalRouter()
    router.register_source("failure", MemoryTier.FAILURE, fm)
    router.register_source(
        "episodic", MemoryTier.EPISODIC,
        FakeSource([_entry(f"note about {keyword}", MemoryTier.EPISODIC, "ep1")]),
    )

    # Unfiltered: a FAILURE-tier item is interleaved into the ranked result set.
    unfiltered = router.route(keyword, top_k=10, per_source_k=10)
    assert any(it.tier == MemoryTier.FAILURE.value for it in unfiltered)

    # {FAILURE} filter: only failure-tier results, all from the failure source.
    only_failure = router.route(keyword, tiers={MemoryTier.FAILURE}, top_k=10)
    assert only_failure  # the seeded failure matches the query
    assert all(it.tier == MemoryTier.FAILURE.value for it in only_failure)
    assert all(it.source == "failure" for it in only_failure)


# ============================================================ Factory (Task 4.1)


def test_factory_registers_tiers_and_route_has_provenance(tmp_path):
    # Feature: m19-retrieval-router: build_retrieval_router over a real FridayMemory
    # registers episodic/semantic/procedural sources; seeded items are retrievable
    # through route with correct provenance; failure_memory adds a FAILURE source.
    # Validates: Requirements 7.1
    mem = FridayMemory(data_dir=str(tmp_path / "fm_data"))
    mem.episodic.record(Episode(user_text="open chrome browser", assistant_response="done"))
    mem.remember_fact("the sky is blue today", category="general")

    router = build_retrieval_router(mem)
    tiers = set(router.tiers())
    assert {MemoryTier.EPISODIC, MemoryTier.SEMANTIC, MemoryTier.PROCEDURAL} <= tiers
    assert router.source_count == 3

    # Seeded episode retrievable with episodic provenance.
    epi_res = router.route("chrome", top_k=10)
    assert any(
        it.source == "episodic" and it.tier == MemoryTier.EPISODIC.value for it in epi_res
    )

    # Seeded fact retrievable with semantic provenance.
    fact_res = router.route("sky", top_k=10)
    assert any(
        it.source == "semantic" and it.tier == MemoryTier.SEMANTIC.value for it in fact_res
    )

    # Passing a failure_memory adds the FAILURE source.
    fm = FailureMemory(store_path=str(tmp_path / "fail.json"))
    router_with_failure = build_retrieval_router(mem, failure_memory=fm)
    assert router_with_failure.source_count == 4
    assert MemoryTier.FAILURE in set(router_with_failure.tiers())
