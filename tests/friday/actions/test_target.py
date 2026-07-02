"""Unit tests for the Target dataclass.

Task 1.2 - exercises `friday/actions/target.py`. Target is a pure frozen
dataclass: construction, validation, the `has_semantic_hint` property, and
immutability. No real I/O or windows are involved (FRIDAY_DRY_RUN=1 enforced
by conftest), and none is needed for a pure value object.

Validates: Requirements 1.2, 3.3
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from friday.actions.target import Target


# ---------------------------------------------------------------------------
# Valid construction with each identifying field individually
# ---------------------------------------------------------------------------

class TestValidConstruction:
    def test_construct_with_text(self):
        t = Target(text="Submit")
        assert t.text == "Submit"

    def test_construct_with_role(self):
        t = Target(role="button")
        assert t.role == "button"

    def test_construct_with_selector(self):
        t = Target(selector="#login")
        assert t.selector == "#login"

    def test_construct_with_automation_id(self):
        t = Target(automation_id="loginButton")
        assert t.automation_id == "loginButton"

    def test_construct_with_window_title(self):
        t = Target(window_title="Notepad")
        assert t.window_title == "Notepad"

    def test_construct_with_coordinates(self):
        t = Target(coordinates=(100, 200))
        assert t.coordinates == (100, 200)

    def test_construct_with_multiple_fields(self):
        t = Target(text="Submit", role="button", index=2)
        assert t.text == "Submit"
        assert t.role == "button"
        assert t.index == 2


# ---------------------------------------------------------------------------
# Validation - at least one identifying field required
# ---------------------------------------------------------------------------

class TestValidation:
    def test_empty_target_raises_value_error(self):
        with pytest.raises(ValueError):
            Target()

    def test_all_empty_strings_raises_value_error(self):
        with pytest.raises(ValueError):
            Target(text="", role="", selector="", automation_id="", window_title="")

    def test_index_only_raises_value_error(self):
        # index is a disambiguator, not an identifying field
        with pytest.raises(ValueError):
            Target(index=3)

    def test_value_error_message_mentions_identifying_field(self):
        with pytest.raises(ValueError, match="identifying field"):
            Target()


# ---------------------------------------------------------------------------
# has_semantic_hint property
# ---------------------------------------------------------------------------

class TestHasSemanticHint:
    def test_true_for_text(self):
        assert Target(text="Submit").has_semantic_hint is True

    def test_true_for_role(self):
        assert Target(role="button").has_semantic_hint is True

    def test_true_for_selector(self):
        assert Target(selector="#login").has_semantic_hint is True

    def test_true_for_automation_id(self):
        assert Target(automation_id="loginButton").has_semantic_hint is True

    def test_false_for_coordinates_only(self):
        assert Target(coordinates=(10, 20)).has_semantic_hint is False

    def test_false_for_window_title_only(self):
        # window_title is not a semantic element hint
        assert Target(window_title="Notepad").has_semantic_hint is False


# ---------------------------------------------------------------------------
# Frozen immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_text_assignment_raises_frozen_instance_error(self):
        t = Target(text="Submit")
        with pytest.raises(FrozenInstanceError):
            t.text = "Cancel"  # type: ignore[misc]

    def test_coordinates_assignment_raises_frozen_instance_error(self):
        t = Target(text="Submit")
        with pytest.raises(FrozenInstanceError):
            t.coordinates = (1, 2)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_index_defaults_to_zero(self):
        assert Target(text="Submit").index == 0

    def test_coordinates_defaults_to_none(self):
        assert Target(text="Submit").coordinates is None

    def test_unset_string_fields_default_to_empty(self):
        t = Target(text="Submit")
        assert t.role == ""
        assert t.selector == ""
        assert t.automation_id == ""
        assert t.window_title == ""
