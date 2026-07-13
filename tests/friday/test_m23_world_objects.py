"""M23 — Semantic World Object property tests.

Feature: m23-browser-generic-desktop-environment

Property 8: every Observation (the uniform World Object) carries confidence,
freshness, evidence, source, bounding region, and possible affordances; and
freshness is non-increasing with age (A2.1). No application-specific structure.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.events.event import FrozenDict
from friday.perception.observation import Observation
from friday.perception.types import PerceptionSource


_OBJECT_TYPES = ["button", "link", "textbox", "checkbox", "listitem", "document",
                 "text", "window", "combobox", "slider"]
_SENSORS = ["dom", "uia", "ocr", "vision", "screen", "process"]


@settings(max_examples=100)
@given(
    sensor=st.sampled_from(_SENSORS),
    env=st.sampled_from(["browser", "desktop", "system"]),
    otype=st.sampled_from(_OBJECT_TYPES),
    conf=st.floats(min_value=0.0, max_value=1.0),
    ttl=st.one_of(st.none(), st.floats(min_value=1.0, max_value=600.0)),
)
def test_p8_world_object_metadata_complete(sensor, env, otype, conf, ttl):
    # Feature: m23-browser-generic-desktop-environment, Property 8:
    # World Object metadata completeness + freshness non-increasing.
    # Validates: Requirements 4.1, 4.3, 4.4
    obs = Observation(
        sensor=sensor, environment=env, object_type=otype,
        confidence=conf, bbox=(1, 2, 3, 4), ttl_seconds=ttl,
    )
    # Confidence
    assert 0.0 <= obs.confidence <= 1.0
    # Source (semantic, source-agnostic)
    assert isinstance(obs.source, PerceptionSource)
    # Evidence (raw-signal provenance)
    assert isinstance(obs.evidence, FrozenDict)
    assert obs.evidence.get("sensor") == sensor
    assert obs.evidence.get("observation_id") == obs.id
    # Bounding region
    assert obs.bbox == (1, 2, 3, 4)
    # Affordances (generic, from object_type)
    aff = obs.inferred_affordances()
    assert isinstance(aff, tuple) and len(aff) >= 1
    # Freshness in [0,1]
    f0 = obs.freshness(now=obs.timestamp)
    assert 0.0 <= f0 <= 1.0

    # Freshness is non-increasing with age.
    f_later = obs.freshness(now=obs.timestamp + 1000.0)
    assert f_later <= f0 + 1e-9
    if ttl is None:
        assert f0 == 1.0 and f_later == 1.0  # no decay without a ttl


@settings(max_examples=100)
@given(
    otype=st.sampled_from(_OBJECT_TYPES),
    explicit=st.lists(st.sampled_from(["click", "type", "scroll"]), max_size=3),
)
def test_p8_explicit_affordances_win(otype, explicit):
    # Feature: m23-browser-generic-desktop-environment, Property 8 (cont.):
    # explicit affordances override the generic inference. Validates: Requirements 4.1
    obs = Observation(
        sensor="uia", environment="desktop", object_type=otype,
        affordances=tuple(explicit),
    )
    if explicit:
        assert obs.inferred_affordances() == tuple(explicit)
    else:
        # falls back to generic inference for the type
        assert isinstance(obs.inferred_affordances(), tuple)
