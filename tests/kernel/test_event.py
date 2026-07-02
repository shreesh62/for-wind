"""M1 tests — Event immutability, signatures, serialization (A2, A6 partial)."""

import dataclasses

import pytest
from hypothesis import given, strategies as st

from friday.events.event import Event, FrozenDict, make_event


class TestEventImmutability:
    def test_field_assignment_raises(self):
        event = make_event("test.created", "tests", logical_time=1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.id = "x"

    def test_payload_is_immutable(self):
        event = make_event("test.created", "tests", 1, payload={"a": 1})
        with pytest.raises(TypeError):
            event.payload["a"] = 2
        with pytest.raises(TypeError):
            event.payload.update({"b": 2})
        with pytest.raises(TypeError):
            del event.payload["a"]
        with pytest.raises(TypeError):
            event.payload.clear()

    def test_frozendict_hashable(self):
        assert isinstance(hash(FrozenDict({"a": 1})), int)


class TestEventSignature:
    def test_valid_signature_verifies(self):
        event = make_event("test.created", "tests", 1, payload={"k": "v"})
        assert event.verify()

    def test_tampered_payload_fails_verification(self):
        event = make_event("test.created", "tests", 1, payload={"k": "v"})
        tampered = dataclasses.replace(event, payload=FrozenDict({"k": "hacked"}))
        assert not tampered.verify()

    def test_tampered_type_fails_verification(self):
        event = make_event("test.created", "tests", 1)
        tampered = dataclasses.replace(event, event_type="other.type")
        assert not tampered.verify()

    def test_tampered_parent_fails_verification(self):
        event = make_event("test.created", "tests", 1, parent_id=None)
        tampered = dataclasses.replace(event, parent_id="fake-parent")
        assert not tampered.verify()


class TestEventSerialization:
    def test_roundtrip(self):
        event = make_event(
            "test.created", "tests", 7, payload={"x": 1}, parent_id="p1"
        )
        restored = Event.from_dict(event.to_dict())
        assert restored == event
        assert restored.verify()

    def test_correlation_defaults_to_id(self):
        event = make_event("test.created", "tests", 1)
        assert event.correlation_id == event.id


@given(
    payload=st.dictionaries(
        st.text(min_size=1, max_size=8),
        st.one_of(st.integers(), st.text(max_size=16), st.booleans()),
        max_size=5,
    ),
    logical_time=st.integers(min_value=0, max_value=10**9),
)
def test_property_any_event_roundtrips_and_verifies(payload, logical_time):
    event = make_event("prop.test", "tests", logical_time, payload=payload)
    assert event.verify()
    assert Event.from_dict(event.to_dict()) == event
