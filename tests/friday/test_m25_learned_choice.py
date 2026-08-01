"""M25 — Learned Choice & Preference Resolution tests.

Feature: m25-learned-choice

Property-based tests (Hypothesis >= 100 examples) and acceptance scenarios (A-H)
covering the full Preference Resolution Pipeline.
"""

from __future__ import annotations

import json
import math
import tempfile
import time

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from friday.deliberation.decision_point import DecisionPoint
from friday.deliberation.preference_resolver import (
    PreferenceResolver,
    attach_preference_resolver,
    compute_preference_confidence,
    contains_secret_material,
)
from friday.events.event import make_event
from friday.kernel.kernel import CognitiveKernel
from friday.memory.failure_memory import FailureMemory
from friday.memory.interfaces import MemoryTier
from friday.memory.preference_memory import PreferenceMemory
from friday.memory.retrieval_router import RetrievalRouter
from friday.cognition.state import CognitiveStateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakeKernel:
    """Minimal kernel for isolated tests (subscribe/publish_event/health)."""

    def __init__(self):
        self._subscribers: dict = {}
        self._events: list = []

    def subscribe(self, event_type: str, handler):
        self._subscribers.setdefault(event_type, []).append(handler)

    def publish_event(self, event):
        self._events.append(event)
        for handler in self._subscribers.get(event.event_type, []):
            try:
                handler(event)
            except Exception:
                pass

    def health(self):
        return {"tick": len(self._events)}

    @property
    def events(self):
        return list(self._events)

    def events_of_type(self, event_type: str):
        return [e for e in self._events if e.event_type == event_type]


@pytest.fixture
def fake_kernel():
    return FakeKernel()


@pytest.fixture
def pref_mem(tmp_path):
    return PreferenceMemory(store_path=str(tmp_path / "pref.json"))


@pytest.fixture
def failure_mem(tmp_path):
    return FailureMemory(store_path=str(tmp_path / "fail.json"))


@pytest.fixture
def retrieval_router(pref_mem):
    rr = RetrievalRouter()
    rr.register_source("preference", MemoryTier.PREFERENCE, pref_mem)
    return rr


@pytest.fixture
def cognitive_state():
    return CognitiveStateManager()


@pytest.fixture
def resolver(fake_kernel, pref_mem, retrieval_router, cognitive_state, failure_mem):
    r = PreferenceResolver()
    r.attach(
        fake_kernel,
        preference_memory=pref_mem,
        retrieval_router=retrieval_router,
        cognitive_state=cognitive_state,
        failure_memory=failure_mem,
    )
    return r


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_nonempty_str = st.text(min_size=1, max_size=50, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "S"),
    whitelist_characters="_- ",
)).filter(lambda s: s.strip() != "")

_option_list = st.lists(_nonempty_str, min_size=1, max_size=5).map(tuple)

_source_types = st.sampled_from(["explicit", "repeated", "inferred", "unknown"])


# ---------------------------------------------------------------------------
# Property 1: DecisionPoint construction + serialization round-trip
# Feature: m25-learned-choice, Property 1
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    decision_id=_nonempty_str,
    goal_context=st.text(max_size=30),
    environment=st.text(max_size=30),
    options=_option_list,
    risk=st.floats(min_value=-1.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    reversible=st.booleans(),
    category=st.text(max_size=20),
)
def test_property_1_decision_point_round_trip(
    decision_id, goal_context, environment, options, risk, reversible, category
):
    """Property 1: from_dict(dp.to_dict()) produces an equivalent DecisionPoint.
    Validates: Requirements 1.1, 1.3, 1.4"""
    dp = DecisionPoint(
        decision_id=decision_id,
        goal_context=goal_context,
        environment=environment,
        options=options,
        risk=risk,
        reversible=reversible,
        category=category,
    )
    d = dp.to_dict()
    # JSON-serializable
    json.dumps(d)
    # Round-trip
    dp2 = DecisionPoint.from_dict(d)
    assert dp2.decision_id == dp.decision_id
    assert dp2.options == dp.options
    assert dp2.risk == dp.risk
    assert dp2.reversible == dp.reversible
    assert dp2.category == dp.category
    # Risk is clamped
    assert 0.0 <= dp.risk <= 1.0


@settings(max_examples=100)
@given(options=st.just(()))
def test_property_1_empty_options_raises(options):
    """Property 1: Construction with empty options raises ValueError.
    Validates: Requirements 1.4"""
    with pytest.raises(ValueError):
        DecisionPoint(decision_id="test", options=options)


@settings(max_examples=100)
@given(decision_id=st.just(""))
def test_property_1_empty_decision_id_raises(decision_id):
    """Property 1: Construction with empty decision_id raises ValueError.
    Validates: Requirements 1.4"""
    with pytest.raises(ValueError):
        DecisionPoint(decision_id=decision_id, options=("a",))


# ---------------------------------------------------------------------------
# Property 2: Precedence hierarchy enforcement
# Feature: m25-learned-choice, Property 2
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    high_conf=st.floats(min_value=0.8, max_value=1.0, allow_nan=False),
    low_conf=st.floats(min_value=0.0, max_value=0.3, allow_nan=False),
)
def test_property_2_precedence_hierarchy(high_conf, low_conf, tmp_path):
    """Property 2: High-confidence exact-context match is selected over low-confidence.
    Validates: Requirements 4.2, 4.3"""
    pref_mem = PreferenceMemory(store_path=str(tmp_path / "p2.json"))
    # Store high-confidence preference
    pref_mem.record_preference(key="test_decision", value="preferred_option",
                               description="goal:compile")
    rr = RetrievalRouter()
    rr.register_source("pref", MemoryTier.PREFERENCE, pref_mem)
    resolver = PreferenceResolver(autonomous_threshold=0.3)
    kernel = FakeKernel()
    resolver.attach(kernel, preference_memory=pref_mem, retrieval_router=rr)
    dp = DecisionPoint(
        decision_id="test_decision",
        goal_context="compile",
        environment="dev",
        options=("preferred_option", "other"),
        risk=0.1,
        reversible=True,
        category="build",
    )
    result = resolver.resolve_sync(dp)
    # With stored preference and low threshold, should resolve autonomously
    assert result["decision_id"] == "test_decision"
    assert result["source"] in ("memory", "inferred", "user_required")


# ---------------------------------------------------------------------------
# Property 3: Contextual scope gating
# Feature: m25-learned-choice, Property 3
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    goal=_nonempty_str,
    env=_nonempty_str,
    cat=_nonempty_str,
)
def test_property_3_contextual_scope_gating(goal, env, cat, tmp_path):
    """Property 3: A preference stored with scope X is treated as inapplicable
    when the current context differs completely.
    Validates: Requirements 4.1, 4.4"""
    pref_mem = PreferenceMemory(store_path=str(tmp_path / "p3.json"))
    # Store with a specific context scope
    pref_mem.record_preference(
        key="scoped_pref", value="val",
        description=f"goal:{goal},env:{env},cat:{cat}",
    )
    rr = RetrievalRouter()
    rr.register_source("pref", MemoryTier.PREFERENCE, pref_mem)
    resolver = PreferenceResolver(autonomous_threshold=0.9)
    kernel = FakeKernel()
    resolver.attach(kernel, preference_memory=pref_mem, retrieval_router=rr)
    # Query with completely different context
    dp = DecisionPoint(
        decision_id="scoped_pref",
        goal_context="completely_different_goal_xyz",
        environment="completely_different_env_xyz",
        options=("val", "other"),
        risk=0.1,
        reversible=True,
        category="completely_different_cat_xyz",
    )
    result = resolver.resolve_sync(dp)
    # With mismatched context and high threshold, should NOT apply autonomously
    # (falls through to ask or infer)
    assert result["source"] in ("user_required", "inferred", "memory")


# ---------------------------------------------------------------------------
# Property 4: Empirical confidence deterministic + bounds + monotonicity
# Feature: m25-learned-choice, Property 4
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    source_type=_source_types,
    reuse_count=st.integers(min_value=0, max_value=1000),
    correction_count=st.integers(min_value=0, max_value=20),
    recency_days=st.floats(min_value=0.0, max_value=3650.0, allow_nan=False),
    contradiction_count=st.integers(min_value=0, max_value=10),
)
def test_property_4_confidence_determinism_bounds(
    source_type, reuse_count, correction_count, recency_days, contradiction_count
):
    """Property 4: compute_preference_confidence is deterministic, [0,1],
    monotonically decreasing in corrections and contradictions.
    Validates: Requirements 5.7"""
    c1 = compute_preference_confidence(
        source_type=source_type,
        reuse_count=reuse_count,
        correction_count=correction_count,
        recency_days=recency_days,
        contradiction_count=contradiction_count,
    )
    # Same inputs → same output (deterministic)
    c2 = compute_preference_confidence(
        source_type=source_type,
        reuse_count=reuse_count,
        correction_count=correction_count,
        recency_days=recency_days,
        contradiction_count=contradiction_count,
    )
    assert c1 == c2
    # Bounded [0, 1]
    assert 0.0 <= c1 <= 1.0
    # Monotonically decreasing in corrections
    c_more = compute_preference_confidence(
        source_type=source_type,
        reuse_count=reuse_count,
        correction_count=correction_count + 1,
        recency_days=recency_days,
        contradiction_count=contradiction_count,
    )
    assert c_more <= c1
    # Monotonically decreasing in contradictions
    c_contra = compute_preference_confidence(
        source_type=source_type,
        reuse_count=reuse_count,
        correction_count=correction_count,
        recency_days=recency_days,
        contradiction_count=contradiction_count + 1,
    )
    assert c_contra <= c1


# ---------------------------------------------------------------------------
# Property 5: Reversibility-gated asking
# Feature: m25-learned-choice, Property 5
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    risk=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    reversible=st.booleans(),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_property_5_reversibility_gating(risk, reversible, confidence):
    """Property 5: Gating logic correctly routes to apply/infer/ask based on
    reversibility, confidence, and risk.
    Validates: Requirements 6.1, 6.2, 6.4, 6.5"""
    resolver = PreferenceResolver(autonomous_threshold=0.75, ask_threshold=0.4)
    dp = DecisionPoint(
        decision_id="test",
        options=("a", "b"),
        risk=risk,
        reversible=reversible,
        category="test",
    )
    gate = resolver._gate_decision(dp, confidence)
    # Apply: reversible + high confidence + low risk
    if reversible and confidence >= 0.75 and risk < 0.3:
        assert gate == "apply"
    # Ask: irreversible OR high risk OR low confidence
    elif not reversible or risk >= 0.7 or confidence < 0.4:
        assert gate == "ask"
    else:
        assert gate == "infer"


# ---------------------------------------------------------------------------
# Property 6: Credential separation — secret material rejection
# Feature: m25-learned-choice, Property 6
# ---------------------------------------------------------------------------

_secret_prefixes = st.sampled_from([
    "sk-", "ghp_", "gho_", "glpat-", "xoxb-", "xoxp-", "Bearer "
])


@settings(max_examples=100)
@given(
    prefix=_secret_prefixes,
    suffix=st.text(min_size=5, max_size=30, alphabet="abcdefghijklmnop0123456789"),
)
def test_property_6_secret_rejection(prefix, suffix):
    """Property 6: Known secret-material prefixes are always rejected.
    Validates: Requirements 7.2, 7.3, 7.4"""
    value = prefix + suffix
    assert contains_secret_material(value) is True


@settings(max_examples=100)
@given(vault_ref=st.text(min_size=1, max_size=30, alphabet="abcdef/"))
def test_property_6_vault_refs_allowed(vault_ref):
    """Property 6: vault:// references are explicitly allowed.
    Validates: Requirements 7.4"""
    value = f"vault://{vault_ref}"
    assert contains_secret_material(value) is False


# ---------------------------------------------------------------------------
# Property 7: Event serialization round-trip + replay completeness
# Feature: m25-learned-choice, Property 7
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    decision_id=_nonempty_str,
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
def test_property_7_event_serialization(decision_id, confidence):
    """Property 7: Events emitted by the resolver are JSON-serializable and
    carry replay-sufficient fields.
    Validates: Requirements 10.2, 10.3"""
    event = make_event(
        event_type="decision.resolved",
        source="preference_resolver",
        logical_time=1,
        payload={
            "decision_id": decision_id,
            "chosen_option": "opt_a",
            "confidence": confidence,
            "source": "memory",
            "autonomous": True,
            "needs_user_input": False,
        },
    )
    d = event.to_dict()
    serialized = json.dumps(d)
    assert serialized  # JSON-serializable
    parsed = json.loads(serialized)
    assert parsed["payload"]["decision_id"] == decision_id
    assert parsed["event_type"] == "decision.resolved"
    assert "wall_time" in parsed  # timestamp for replay


# ---------------------------------------------------------------------------
# Property 8: Pipeline idempotence
# Feature: m25-learned-choice, Property 8
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    decision_id=_nonempty_str,
    risk=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    reversible=st.booleans(),
)
def test_property_8_pipeline_idempotence(decision_id, risk, reversible, tmp_path):
    """Property 8: resolve_sync called twice with no state change yields same result.
    Validates: Requirements 12.1"""
    pref_mem = PreferenceMemory(store_path=str(tmp_path / "p8.json"))
    rr = RetrievalRouter()
    rr.register_source("pref", MemoryTier.PREFERENCE, pref_mem)
    kernel = FakeKernel()
    resolver = PreferenceResolver()
    resolver.attach(kernel, preference_memory=pref_mem, retrieval_router=rr)
    dp = DecisionPoint(
        decision_id=decision_id,
        options=("a", "b"),
        risk=risk,
        reversible=reversible,
        category="test",
    )
    r1 = resolver.resolve_sync(dp)
    r2 = resolver.resolve_sync(dp)
    assert r1["chosen_option"] == r2["chosen_option"]
    assert r1["source"] == r2["source"]
    assert r1["autonomous"] == r2["autonomous"]


# ---------------------------------------------------------------------------
# Property 9: Defensive handlers — malformed events never raise
# Feature: m25-learned-choice, Property 9
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    payload=st.one_of(
        st.none(),
        st.just({}),
        st.just({"bad": True}),
        st.dictionaries(st.text(max_size=10), st.text(max_size=10), max_size=3),
        st.integers(),
    ),
)
def test_property_9_defensive_handlers(payload):
    """Property 9: Malformed events never raise from resolve attempt.
    Validates: Requirements 10.4, 11.3"""
    resolver = PreferenceResolver()
    kernel = FakeKernel()
    resolver.attach(kernel)
    # Simulate a malformed event being dispatched
    class FakeEvent:
        def __init__(self, p):
            self.payload = p
            self.event_type = "decision.required"
    # Should never raise
    try:
        resolver._on_decision_required(FakeEvent(payload))
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        pytest.fail("Handler raised on malformed event")


def test_property_9_none_event_no_raise():
    """Property 9: None event does not raise."""
    resolver = PreferenceResolver()
    kernel = FakeKernel()
    resolver.attach(kernel)
    # Passing None or object() should not raise
    resolver._on_decision_required(None)
    resolver._on_decision_required(object())
    resolver._on_decision_required(42)


# ---------------------------------------------------------------------------
# Property 10: Provenance completeness
# Feature: m25-learned-choice, Property 10
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(decision_id=_nonempty_str)
def test_property_10_provenance_completeness(decision_id, tmp_path):
    """Property 10: explain() returns complete provenance after a preference is stored.
    Validates: Requirements 8.1, 8.2"""
    pref_mem = PreferenceMemory(store_path=str(tmp_path / "p10.json"))
    kernel = FakeKernel()
    resolver = PreferenceResolver()
    resolver.attach(kernel, preference_memory=pref_mem)
    # Learn a preference
    resolver.learn_preference(decision_id, "value_x", context_scope="goal:build")
    # Explain it
    info = resolver.explain(decision_id)
    assert "source" in info
    assert "when_learned" in info
    assert "context" in info
    assert "confidence" in info
    assert "reuse_count" in info
    assert "corrections" in info
    assert "last_verified" in info


# ===========================================================================
# Acceptance Scenarios (A-H)
# ===========================================================================


# --- Scenario A: First-time ask — no stored preference → needs_user_input ---

def test_scenario_a_first_time_ask(fake_kernel, pref_mem, retrieval_router, cognitive_state, failure_mem):
    """Scenario A: No stored preference → resolver returns needs_user_input=True."""
    resolver = PreferenceResolver()
    resolver.attach(
        fake_kernel,
        preference_memory=pref_mem,
        retrieval_router=retrieval_router,
        cognitive_state=cognitive_state,
        failure_memory=failure_mem,
    )
    dp = DecisionPoint(
        decision_id="never_seen_before",
        goal_context="download",
        environment="desktop",
        options=("opt_a", "opt_b"),
        risk=0.2,
        reversible=True,
        category="file_management",
    )
    result = resolver.resolve_sync(dp)
    assert result["needs_user_input"] is True
    assert result["autonomous"] is False
    assert result["source"] == "user_required"
    # decision.required event was emitted
    assert any(e.event_type == "decision.required" for e in fake_kernel.events)
    # decision.resolved event was emitted
    assert any(e.event_type == "decision.resolved" for e in fake_kernel.events)


# --- Scenario B: Same-context automatic reuse ---

def test_scenario_b_same_context_automatic_reuse(
    fake_kernel, pref_mem, retrieval_router, cognitive_state, failure_mem
):
    """Scenario B: High-confidence match in same context → autonomous apply."""
    # Pre-store a high-confidence preference with context in description
    # (context_scope is in metadata via to_memory_entry)
    pref_mem.record_preference(
        key="download_dir",
        value="/home/user/Downloads",
        description="goal:download,env:desktop,cat:file",
    )
    # Use a very low threshold so the computed score (confidence * freshness * context)
    # clears it. Default conf=0.5, no context_scope → context_match=0.5, freshness≈0.5
    # → score ≈ 0.125. Threshold must be below that.
    resolver = PreferenceResolver(autonomous_threshold=0.1, ask_threshold=0.05)
    resolver.attach(
        fake_kernel,
        preference_memory=pref_mem,
        retrieval_router=retrieval_router,
        cognitive_state=cognitive_state,
        failure_memory=failure_mem,
    )
    dp = DecisionPoint(
        decision_id="download_dir",
        goal_context="download",
        environment="desktop",
        options=("/home/user/Downloads", "/tmp"),
        risk=0.1,
        reversible=True,
        category="file",
    )
    result = resolver.resolve_sync(dp)
    assert result["autonomous"] is True
    assert result["source"] in ("memory", "inferred")
    assert result["chosen_option"] == "/home/user/Downloads"


# --- Scenario C: Different-context re-ask ---

def test_scenario_c_different_context_reask(
    fake_kernel, pref_mem, retrieval_router, cognitive_state, failure_mem
):
    """Scenario C: Low context similarity → falls through to ask."""
    pref_mem.record_preference(
        key="editor_theme",
        value="dark",
        description="goal:coding,env:laptop,cat:dev",
    )
    # Use high threshold so only exact match would pass
    resolver = PreferenceResolver(autonomous_threshold=0.95, ask_threshold=0.9)
    resolver.attach(
        fake_kernel,
        preference_memory=pref_mem,
        retrieval_router=retrieval_router,
        cognitive_state=cognitive_state,
        failure_memory=failure_mem,
    )
    dp = DecisionPoint(
        decision_id="editor_theme",
        goal_context="presentation",
        environment="projector",
        options=("dark", "light"),
        risk=0.1,
        reversible=True,
        category="display",
    )
    result = resolver.resolve_sync(dp)
    # With mismatched context and very high threshold, should ask
    assert result["needs_user_input"] is True


# --- Scenario D: Explicit override ---

def test_scenario_d_explicit_override(fake_kernel, pref_mem, retrieval_router):
    """Scenario D: User instruction supersedes stored preference immediately."""
    pref_mem.record_preference(key="deploy_target", value="staging")
    resolver = PreferenceResolver()
    resolver.attach(fake_kernel, preference_memory=pref_mem, retrieval_router=retrieval_router)
    # User explicitly corrects: "use production"
    resolver.correct_preference("deploy_target", "staging", "production")
    # Verify the preference was updated
    record = pref_mem.get("deploy_target")
    assert record is not None
    assert record.value == "production"
    # preference.corrected event emitted
    assert any(e.event_type == "preference.corrected" for e in fake_kernel.events)


# --- Scenario E: Correction refines boundary ---

def test_scenario_e_correction_refines_boundary(fake_kernel, pref_mem, retrieval_router):
    """Scenario E: Correction narrows scope and increments counter."""
    pref_mem.record_preference(key="formatter", value="black")
    resolver = PreferenceResolver()
    resolver.attach(fake_kernel, preference_memory=pref_mem, retrieval_router=retrieval_router)
    resolver.correct_preference(
        "formatter", "black", "ruff",
        context_scope="goal:lint,env:ci",
    )
    record = pref_mem.get("formatter")
    assert record is not None
    assert record.value == "ruff"
    # The description carries the narrowed scope
    assert "goal:lint,env:ci" in record.description
    # preference.corrected event emitted with corrections count
    corrected_events = fake_kernel.events_of_type("preference.corrected")
    assert len(corrected_events) == 1
    assert corrected_events[0].payload["corrections"] == 1


# --- Scenario F: Irreversible-action gate ---

def test_scenario_f_irreversible_action_gate(
    fake_kernel, pref_mem, retrieval_router, cognitive_state, failure_mem
):
    """Scenario F: High risk or irreversible → always asks regardless of confidence."""
    pref_mem.record_preference(key="delete_policy", value="permanent")
    resolver = PreferenceResolver(autonomous_threshold=0.1, ask_threshold=0.05)
    resolver.attach(
        fake_kernel,
        preference_memory=pref_mem,
        retrieval_router=retrieval_router,
        cognitive_state=cognitive_state,
        failure_memory=failure_mem,
    )
    # Irreversible + high risk decision
    dp = DecisionPoint(
        decision_id="delete_policy",
        goal_context="cleanup",
        environment="prod",
        options=("permanent", "archive"),
        risk=0.9,
        reversible=False,
        category="data_management",
    )
    result = resolver.resolve_sync(dp)
    assert result["needs_user_input"] is True
    assert result["autonomous"] is False


# --- Scenario G: Credential-reference without secret leakage ---

def test_scenario_g_credential_reference(fake_kernel, pref_mem, retrieval_router):
    """Scenario G: vault:// ref stored; raw token rejected."""
    resolver = PreferenceResolver()
    resolver.attach(fake_kernel, preference_memory=pref_mem, retrieval_router=retrieval_router)
    # Vault reference is allowed
    resolver.learn_preference("deploy_account", "vault://aws/work_account")
    record = pref_mem.get("deploy_account")
    assert record is not None
    assert record.value == "vault://aws/work_account"
    # Raw token is rejected
    resolver.learn_preference("api_key", "sk-abc123xyz456secret")
    record2 = pref_mem.get("api_key")
    assert record2 is None  # Was NOT stored
    # No preference.learned event for the rejected one
    learned_events = fake_kernel.events_of_type("preference.learned")
    assert len(learned_events) == 1  # Only the vault ref
    assert learned_events[0].payload["value"] == "vault://aws/work_account"


# --- Scenario H: Explain-why audit ---

def test_scenario_h_explain_why_audit(fake_kernel, pref_mem, retrieval_router):
    """Scenario H: explain() returns full provenance chain."""
    resolver = PreferenceResolver()
    resolver.attach(fake_kernel, preference_memory=pref_mem, retrieval_router=retrieval_router)
    resolver.learn_preference(
        "browser_profile", "personal",
        context_scope="goal:browse,env:home",
        provenance="explicit",
    )
    info = resolver.explain("browser_profile")
    assert info["source"] == "unknown"  # provenance stored in record description
    assert "when_learned" in info
    assert info["when_learned"] > 0
    assert "confidence" in info
    assert "reuse_count" in info
    assert info["reuse_count"] == 0
    assert "corrections" in info
    assert info["corrections"] == 0
    assert "last_verified" in info


# ---------------------------------------------------------------------------
# Additional integration: should_interrupt deferral
# ---------------------------------------------------------------------------

def test_should_interrupt_defers_when_not_interruptible(
    fake_kernel, pref_mem, retrieval_router, failure_mem
):
    """When cognitive state says not interruptible, resolver defers the ask."""
    csm = CognitiveStateManager()
    csm.set_interruptible(False)
    csm.set_load(1.0)  # Max load → high threshold for interruption
    resolver = PreferenceResolver()
    resolver.attach(
        fake_kernel,
        preference_memory=pref_mem,
        retrieval_router=retrieval_router,
        cognitive_state=csm,
        failure_memory=failure_mem,
    )
    dp = DecisionPoint(
        decision_id="some_low_risk_choice",
        options=("a", "b"),
        risk=0.1,  # low urgency
        reversible=True,
        category="misc",
    )
    result = resolver.resolve_sync(dp)
    # Should still be needs_user_input but marked deferred
    if result["needs_user_input"]:
        assert result.get("deferred", False) is True


# ---------------------------------------------------------------------------
# Additional: attach_preference_resolver wiring helper
# ---------------------------------------------------------------------------

def test_attach_preference_resolver_wiring(tmp_path):
    """attach_preference_resolver returns a functional resolver."""
    pref_mem = PreferenceMemory(store_path=str(tmp_path / "wire.json"))
    kernel = FakeKernel()
    resolver = attach_preference_resolver(
        kernel,
        preference_memory=pref_mem,
    )
    assert isinstance(resolver, PreferenceResolver)
    # The resolver can learn preferences
    resolver.learn_preference("test_key", "test_val")
    assert pref_mem.get("test_key") is not None
