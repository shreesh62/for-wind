"""M23 — Motor preference ordering property tests.

Feature: m23-browser-generic-desktop-environment

Property 9: for a target resolvable by more than one method, the resolver selects
the highest-preference adapter that can handle it, in the order
Keyboard/Accessibility -> Mouse -> Pixel. Accessibility (UIA) is preferred over
raw mouse coordinates, and mouse over pixel/OCR. No app-specific branching.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.actions.adapters.desktop import DesktopAdapter
from friday.actions.adapters.desktop_actions import DesktopActionsAdapter
from friday.actions.adapters.vision import VisionAdapter
from friday.actions.adapters.resolver import AdapterResolver
from friday.actions.target import Target
from friday.perception.types import BoundingBox, OCRRegion, UIElement
from friday.perception.world_state import WorldStateBuilder


def _resolver():
    # Desktop (accessibility) + DesktopActions (mouse) + Vision (pixel), no CDP.
    return AdapterResolver([DesktopAdapter(), DesktopActionsAdapter(), VisionAdapter()])


def _bbox():
    return BoundingBox(x=10, y=20, width=40, height=10)


def test_p9_keyboard_primitives_available_on_every_adapter():
    # Feature: m23-browser-generic-desktop-environment, Property 9 (keyboard tier):
    # keyboard is the least-invasive actuation and is available everywhere.
    # Validates: Requirements 5.1
    for adapter in (DesktopAdapter(), DesktopActionsAdapter(), VisionAdapter()):
        for verb in ("type_text", "press_key", "press_hotkey"):
            assert hasattr(adapter, verb)


@settings(max_examples=100)
@given(word=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=8))
def test_p9_accessibility_preferred_over_pixel(word):
    # Feature: m23-browser-generic-desktop-environment, Property 9:
    # a text target present in BOTH UIA (accessibility) and OCR (pixel) resolves
    # to the accessibility adapter. Validates: Requirements 5.2, 5.4
    ws = (
        WorldStateBuilder()
        .add_ui_elements([UIElement(text=word, control_type="Button", bbox=_bbox())])
        .add_ocr_regions([OCRRegion(text=word, bbox=_bbox(), confidence=0.9)])
        .build()
    )
    result = _resolver().resolve(Target(text=word), ws)
    assert result is not None
    adapter, _ = result
    assert adapter.name == "desktop"  # UIA / accessibility, not vision/pixel


@settings(max_examples=100)
@given(x=st.integers(min_value=0, max_value=1920), y=st.integers(min_value=0, max_value=1080))
def test_p9_mouse_preferred_over_pixel_for_coordinates(x, y):
    # Feature: m23-browser-generic-desktop-environment, Property 9:
    # a coordinate target handled by both mouse (DesktopActions) and pixel (Vision)
    # resolves to mouse. Validates: Requirements 5.3, 5.4
    ws = WorldStateBuilder().add_ocr_regions(
        [OCRRegion(text="anything", bbox=_bbox(), confidence=0.9)]
    ).build()
    result = _resolver().resolve(Target(coordinates=(x, y)), ws)
    assert result is not None
    adapter, _ = result
    assert adapter.name == "desktop_actions"  # mouse tier, above pixel


def test_p9_pixel_is_last_resort():
    # Feature: m23-browser-generic-desktop-environment, Property 9:
    # when only OCR/pixel can resolve the text, vision is used (last resort).
    # Validates: Requirements 5.3
    ws = WorldStateBuilder().add_ocr_regions(
        [OCRRegion(text="OnlyOnScreen", bbox=_bbox(), confidence=0.9)]
    ).build()
    result = _resolver().resolve(Target(text="OnlyOnScreen"), ws)
    assert result is not None
    adapter, _ = result
    assert adapter.name == "vision"
