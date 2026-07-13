"""M23 — Verified-success-by-World-Model-change property tests.

Feature: m23-browser-generic-desktop-environment

Property 11: step success is established only by an OBSERVED change in the World
Model; input dispatch without an observed change yields an unverified verdict.
Tests the pure decision predicates that gate success in GoalExecutor.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.executor import GoalExecutor
from friday.perception.types import BoundingBox, OCRRegion, UIElement
from friday.perception.world_state import WorldStateBuilder


def _bbox():
    return BoundingBox(x=1, y=2, width=3, height=4)


def test_p11_identical_worldstate_is_no_change():
    # Feature: m23-browser-generic-desktop-environment, Property 11:
    # dispatch alone (no observed change) is NOT success. Validates: Requirements 7.1, 7.2
    ws = WorldStateBuilder().add_ui_elements(
        [UIElement(text="Save", control_type="Button", bbox=_bbox())]
    ).set_screenshot_hash("h1").build()
    # Same perception before/after => no observed change => unverified.
    assert GoalExecutor._observed_change(ws, ws) is False


@settings(max_examples=100)
@given(h1=st.text(min_size=1, max_size=12), h2=st.text(min_size=1, max_size=12))
def test_p11_screenshot_change_is_detected(h1, h2):
    # Feature: m23-browser-generic-desktop-environment, Property 11:
    # a pixel-hash change is an observed World-Model change. Validates: Requirements 7.1, 7.3
    before = WorldStateBuilder().set_screenshot_hash(h1).build()
    after = WorldStateBuilder().set_screenshot_hash(h2).build()
    assert GoalExecutor._observed_change(before, after) is (h1 != h2)


def test_p11_element_count_change_is_detected():
    # Feature: m23-browser-generic-desktop-environment, Property 11:
    # appearance of a new element is an observed change. Validates: Requirements 7.1, 7.3
    before = WorldStateBuilder().add_ui_elements(
        [UIElement(text="A", control_type="Text", bbox=_bbox())]
    ).build()
    after = WorldStateBuilder().add_ui_elements([
        UIElement(text="A", control_type="Text", bbox=_bbox()),
        UIElement(text="B", control_type="Button", bbox=_bbox()),
    ]).build()
    assert GoalExecutor._observed_change(before, after) is True


def test_p11_worldstate_is_real_gate():
    # Feature: m23-browser-generic-desktop-environment, Property 11:
    # an empty (dry-run) WorldState is not "real", so verification is skipped and
    # the adapter result stands; a perceived WorldState IS real. Validates: Requirements 7.2
    empty = WorldStateBuilder().build()
    assert GoalExecutor._worldstate_is_real(empty) is False

    with_ocr = WorldStateBuilder().add_ocr_regions(
        [OCRRegion(text="x", bbox=_bbox(), confidence=0.9)]
    ).build()
    assert GoalExecutor._worldstate_is_real(with_ocr) is True

    with_hash = WorldStateBuilder().set_screenshot_hash("h").build()
    assert GoalExecutor._worldstate_is_real(with_hash) is True
