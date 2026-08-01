"""M21 (slice 2) — Seven-Tier Memory Completion tests (Capability + Preference).

Feature: m21-memory-seven-tiers

Completes the FAS §A2.11.1 seven-tier memory model by adding the Capability and
Preference tiers additively, mirroring the proven ``FailureMemory`` template
(bounded ``JSONFileStore``, kernel-driven, defensive handlers, uniform
``retrieve(query, top_k)`` surface, opt-in wiring). The ``CompetenceModel`` remains
the sole competence authority — the Capability tier is a memory VIEW only.

Property tests (Hypothesis, >=100 examples) cover Correctness Properties 1-6 from
design.md. This module covers Task 5 (Properties 1, 2, 3, 4, 6) AND Task 6.1
(Property 5 — router participation). Every store/memory is confined to pytest's
``tmp_path`` so NO ``friday_data/`` files are written.
"""

from __future__ import annotations

import inspect
import re
import uuid
from typing import Any, Dict, List, Optional

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from friday.events.event import make_event
from friday.memory import capability_memory as capability_module
from friday.memory import preference_memory as preference_module
from friday.memory.capability_memory import CapabilityMemory, CapabilityRecord
from friday.memory.controller import FridayMemory, build_retrieval_router
from friday.memory.interfaces import MemoryEntry, MemoryTier
from friday.memory.preference_memory import PreferenceMemory, PreferenceRecord


# ----------------------------------------------------------------- test doubles


class FakeKernel:
    """Minimal event bus double exposing subscribe / publish_event / health.

    ``attach`` calls ``kernel.subscribe(event_type, handler)``; publishing an event
    dispatches it synchronously to every handler registered for its ``event_type``.
    """

    def __init__(self) -> None:
        self._subs: Dict[str, List[Any]] = {}
        self._logical_time = 0

    def subscribe(self, event_type: str, handler: Any) -> None:
        self._subs.setdefault(event_type, []).append(handler)

    def publish_event(self, event: Any) -> None:
        for handler in list(self._subs.get(event.event_type, [])):
            handler(event)

    def publish(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self._logical_time += 1
        event = make_event(
            event_type=event_type,
            source="test",
            logical_time=self._logical_time,
            payload=payload or {},
        )
        self.publish_event(event)

    def health(self) -> Dict[str, Any]:
        return {"ok": True, "subscriptions": {k: len(v) for k, v in self._subs.items()}}


# The seven canonical FAS §A2.11.1 tiers, each expected to map to a MemoryTier value.
CANONICAL_TIERS = [
    "working",
    "episodic",
    "procedural",
    "semantic",
    "capability",
    "failure",
    "preference",
]

# Shared query terms used across capability/preference so router routing can match.
TERMS = ["solar", "tidal", "wind", "hydro", "nuclear", "geothermal"]


def _cm(tmp_path, name: str = "cap", max_entries: int = 2000) -> CapabilityMemory:
    return CapabilityMemory(
        store_path=str(tmp_path / f"{name}_{uuid.uuid4().hex}.json"),
        max_entries=max_entries,
    )


def _pm(tmp_path, name: str = "pref", max_entries: int = 1000) -> PreferenceMemory:
    return PreferenceMemory(
        store_path=str(tmp_path / f"{name}_{uuid.uuid4().hex}.json"),
        max_entries=max_entries,
    )


def _friday_imports(module) -> List[str]:
    """Return the ``friday.<...>`` targets imported by a module's source."""
    src = inspect.getsource(module)
    return re.findall(r"^\s*(?:import|from)\s+(friday\.[\w.]+)", src, re.MULTILINE)


# =================================================================== Property 1


@settings(max_examples=150)
@given(name=st.sampled_from(CANONICAL_TIERS))
def test_p1_seven_tier_ids_complete(name):
    # Feature: m21-memory-seven-tiers, Property 1: MemoryTier includes CAPABILITY and
    # PREFERENCE; each of the seven canonical FAS tiers maps to a MemoryTier value;
    # existing members are unchanged. Validates: Requirements 1.1, 1.2
    # New members present with their canonical values.
    assert MemoryTier.CAPABILITY.value == "capability"
    assert MemoryTier.PREFERENCE.value == "preference"

    # Existing members unchanged (additive-only change).
    assert MemoryTier.WORKING.value == "working"
    assert MemoryTier.EPISODIC.value == "episodic"
    assert MemoryTier.PROCEDURAL.value == "procedural"
    assert MemoryTier.SEMANTIC.value == "semantic"
    assert MemoryTier.USER.value == "user"
    assert MemoryTier.FAILURE.value == "failure"

    # Each canonical tier is representable by a MemoryTier value (round-trips).
    tier = MemoryTier(name)
    assert isinstance(tier, MemoryTier)
    assert tier.value == name


# =================================================================== Property 2


@settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    capability=st.sampled_from(["research", "click", "navigate", "summarize"]),
    environment=st.sampled_from(["web", "desktop", "mobile", ""]),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    attempts=st.integers(min_value=0, max_value=50),
    confidence2=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_p2_capability_record_recall_upsert_and_memory_not_authority(
    tmp_path, capability, environment, confidence, attempts, confidence2
):
    # Feature: m21-memory-seven-tiers, Property 2: a capability outcome is recorded and
    # recallable by (capability, environment); a second record for the same key upserts
    # (one record, newest confidence); competence.updated events on the bus record/upsert;
    # malformed events never raise and record nothing; the tier exposes no competence
    # authority and imports no friday.competence.
    # Validates: Requirements 2.1, 2.2, 2.3, 2.4
    cm = _cm(tmp_path)

    # Direct record + recall.
    cm.record_capability(
        capability=capability, environment=environment,
        confidence=confidence, attempts=attempts,
    )
    recalled = cm.recall(capability=capability, environment=environment)
    assert len(recalled) == 1
    assert recalled[0].capability == capability
    assert recalled[0].environment == environment
    assert abs(recalled[0].confidence - confidence) < 1e-9

    # Upsert: a second record for the SAME (capability, environment) supersedes.
    cm.record_capability(
        capability=capability, environment=environment,
        confidence=confidence2, attempts=attempts + 1,
    )
    recalled = cm.recall(capability=capability, environment=environment)
    assert len(recalled) == 1  # no unbounded duplicates
    assert abs(recalled[0].confidence - confidence2) < 1e-9

    # Bus-driven: competence.updated records a capability memory, re-publish upserts.
    cm2 = _cm(tmp_path, "bus")
    kernel = FakeKernel()
    cm2.attach(kernel)
    kernel.publish("competence.updated", {
        "capability": capability, "environment": environment,
        "confidence": confidence, "attempts": attempts,
    })
    recalled = cm2.recall(capability=capability, environment=environment)
    assert len(recalled) == 1
    kernel.publish("competence.updated", {
        "capability": capability, "environment": environment,
        "confidence": confidence2, "attempts": attempts + 1,
    })
    recalled = cm2.recall(capability=capability, environment=environment)
    assert len(recalled) == 1  # upsert, not append
    assert abs(recalled[0].confidence - confidence2) < 1e-9

    # Malformed / empty events never raise and record nothing.
    baseline = cm2._store.count()
    kernel.publish("competence.updated", {})                       # empty payload
    kernel.publish("competence.updated", {"environment": "web"})   # missing capability
    kernel.publish("competence.updated", {"capability": ""})       # empty capability
    cm2._on_competence(object())                                   # no payload attr
    cm2._on_competence(None)                                       # None event
    assert cm2._store.count() == baseline

    # Memory-not-authority: no competence-authority surface, no friday.competence import.
    assert not hasattr(cm, "is_permitted")
    assert not hasattr(cm, "effective_confidence")
    assert all(not imp.startswith("friday.competence") for imp in _friday_imports(capability_module))


# =================================================================== Property 3


@settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    key=st.sampled_from(["theme", "language", "verbosity", "voice"]),
    value1=st.sampled_from(["dark", "light", "en", "verbose", True, False, 0, 1, None, 3.5]),
    value2=st.sampled_from(["dark", "light", "en", "verbose", True, False, 0, 1, None, 3.5]),
)
def test_p3_preference_upsert_get_all_and_malformed_safe(tmp_path, key, value1, value2):
    # Feature: m21-memory-seven-tiers, Property 3: record_preference stores a preference;
    # a newer value for the same key supersedes (get returns newest, exactly one entry in
    # all()); JSON-safe values (incl. False/0/None) preserved exactly; the _on_preference
    # handler with malformed/empty/missing-value payloads never raises and records nothing.
    # Validates: Requirements 3.1, 3.2, 3.3
    pm = _pm(tmp_path)

    pm.record_preference(key, value1)
    got = pm.get(key)
    assert got is not None
    assert got.value == value1
    assert type(got.value) is type(value1)  # False/0/None/floats preserved exactly

    # Upsert: newer value for the same key supersedes; exactly one entry for that key.
    pm.record_preference(key, value2)
    got = pm.get(key)
    assert got is not None
    assert got.value == value2
    assert type(got.value) is type(value2)
    assert sum(1 for rec in pm.all() if rec.key == key) == 1

    # Defensive handler: malformed/empty/missing-value payloads never raise, record nothing.
    baseline = pm._store.count()
    pm._on_preference(object())                            # no payload attr
    pm._on_preference(None)                                # None event
    kernel = FakeKernel()
    kernel.publish("preference.noop", {})                  # (nothing subscribed) empty
    pm._on_preference(make_event("preference.updated", "t", 1, {}))            # empty payload
    pm._on_preference(make_event("preference.updated", "t", 2, {"key": key}))  # missing value
    pm._on_preference(make_event("preference.updated", "t", 3, {"value": 1}))  # missing key
    assert pm._store.count() == baseline


# =================================================================== Property 4


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=2000)
@given(
    max_entries=st.integers(min_value=1, max_value=8),
    n=st.integers(min_value=10, max_value=30),
    term=st.sampled_from(TERMS),
)
def test_p4_bounded_storage_and_uniform_retrieve(tmp_path, max_entries, n, term):
    # Feature: m21-memory-seven-tiers, Property 4: both tiers' backing stores never exceed
    # max_entries (oldest evicted); retrieve(query, top_k) returns MemoryEntry list carrying
    # the correct tier for a matching query. Validates: Requirements 2.4, 3.3, 4.1
    cm = _cm(tmp_path, "bound", max_entries=max_entries)
    pm = _pm(tmp_path, "bound", max_entries=max_entries)

    for i in range(n):
        cm.record_capability(capability=f"cap-{i}", environment=f"env-{i}", confidence=0.5)
        pm.record_preference(key=f"key-{i}", value=f"val-{i}")

    assert cm._store.count() <= max_entries
    assert pm._store.count() <= max_entries

    # Uniform retrieve: a matching query returns MemoryEntry objects tagged with the tier.
    cm2 = _cm(tmp_path, "retr")
    pm2 = _pm(tmp_path, "retr")
    cm2.record_capability(capability=term, environment="web", confidence=0.9)
    pm2.record_preference(key=term, value="enabled")

    cap_hits = cm2.retrieve(term, top_k=5)
    assert isinstance(cap_hits, list)
    assert cap_hits, "expected at least one capability hit for the seeded term"
    assert all(isinstance(e, MemoryEntry) for e in cap_hits)
    assert all(e.tier == MemoryTier.CAPABILITY for e in cap_hits)

    pref_hits = pm2.retrieve(term, top_k=5)
    assert isinstance(pref_hits, list)
    assert pref_hits, "expected at least one preference hit for the seeded term"
    assert all(isinstance(e, MemoryEntry) for e in pref_hits)
    assert all(e.tier == MemoryTier.PREFERENCE for e in pref_hits)


# =================================================================== Property 5


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(term=st.sampled_from(TERMS))
def test_p5_router_participation(tmp_path, term):
    # Feature: m21-memory-seven-tiers, Property 5: registered under CAPABILITY / PREFERENCE
    # via build_retrieval_router, both tiers contribute to an unfiltered route and are the
    # only results under their respective tier filter. Validates: Requirements 5.1, 5.2
    cm = _cm(tmp_path, "router")
    pm = _pm(tmp_path, "router")
    cm.record_capability(capability=term, environment="web", confidence=0.9)
    pm.record_preference(key=term, value="enabled")

    mem = FridayMemory(data_dir=str(tmp_path / f"fm_{uuid.uuid4().hex}"))
    router = build_retrieval_router(mem, capability_memory=cm, preference_memory=pm)

    tiers = set(router.tiers())
    assert MemoryTier.CAPABILITY in tiers
    assert MemoryTier.PREFERENCE in tiers

    # Unfiltered: the ranked result set can carry both a capability and a preference item.
    unfiltered = router.route(term, top_k=20, per_source_k=20)
    assert any(it.tier == MemoryTier.CAPABILITY.value for it in unfiltered)
    assert any(it.tier == MemoryTier.PREFERENCE.value for it in unfiltered)

    # {CAPABILITY} filter: only capability-tier results, all from the capability source.
    only_cap = router.route(term, tiers={MemoryTier.CAPABILITY}, top_k=20)
    assert only_cap
    assert all(it.tier == MemoryTier.CAPABILITY.value for it in only_cap)
    assert all(it.source == "capability" for it in only_cap)

    # {PREFERENCE} filter: only preference-tier results, all from the preference source.
    only_pref = router.route(term, tiers={MemoryTier.PREFERENCE}, top_k=20)
    assert only_pref
    assert all(it.tier == MemoryTier.PREFERENCE.value for it in only_pref)
    assert all(it.source == "preference" for it in only_pref)


# =================================================================== Property 6


def test_p6_reuse_and_isolation(tmp_path):
    # Feature: m21-memory-seven-tiers, Property 6: both tier modules import only
    # friday.memory.* (interfaces/stores) + stdlib — no friday.competence / friday.recovery
    # / other-subsystem imports; both tiers are usable without a kernel (construct + record
    # + retrieve with _kernel is None). Validates: Requirements 4.1, 4.2, 4.3, 6.1
    allowed_prefixes = ("friday.memory", "friday.events")
    for module in (capability_module, preference_module):
        for imp in _friday_imports(module):
            assert imp.startswith(allowed_prefixes), (
                f"{module.__name__} imports disallowed subsystem: {imp}"
            )
            assert not imp.startswith("friday.competence")
            assert not imp.startswith("friday.recovery")

    # Usable without a kernel: construct + record + retrieve, _kernel stays None.
    cm = _cm(tmp_path, "nokernel")
    assert cm._kernel is None
    cm.record_capability(capability="research", environment="web", confidence=0.7)
    cap_hits = cm.retrieve("research", top_k=5)
    assert all(isinstance(e, MemoryEntry) for e in cap_hits)
    assert cm._kernel is None

    pm = _pm(tmp_path, "nokernel")
    assert pm._kernel is None
    pm.record_preference("theme", "dark")
    pref_hits = pm.retrieve("theme", top_k=5)
    assert all(isinstance(e, MemoryEntry) for e in pref_hits)
    assert pm._kernel is None

    # Records project through the standard MemoryEntry contract (reuse, not duplicate).
    assert CapabilityRecord(capability="c").to_memory_entry().tier == MemoryTier.CAPABILITY
    assert PreferenceRecord(key="k", value="v").to_memory_entry().tier == MemoryTier.PREFERENCE
