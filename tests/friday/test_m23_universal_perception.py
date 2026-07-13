"""M23 — Universal Perception property tests.

Feature: m23-browser-generic-desktop-environment

Covers the pure fusion builder ``observe_active_window`` with injected fake
sensors (no live GUI/UIA/OCR/screen calls):
  - Property 1: universal fused WorldState, ranked, no app/title branching.
  - Property 12: fusion is deterministic/pure over identical sensor inputs.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.perception.active_window import observe_active_window
from friday.perception.priority import SourcePriority
from friday.perception.types import (
    BoundingBox,
    OCRRegion,
    PerceptionSource,
    UIElement,
    WindowInfo,
)


def _bbox() -> BoundingBox:
    return BoundingBox(x=1, y=2, width=3, height=4)


class _FakeDesktop:
    """Injected UIA source."""

    def __init__(self, window, elements, cursor=(5, 5), focused=None):
        self._window = window
        self._elements = elements
        self._cursor = cursor
        self._focused = focused

    def get_active_window(self):
        return self._window

    def get_ui_elements(self):
        return list(self._elements)

    def get_cursor_position(self):
        return self._cursor

    def get_focused_element(self):
        return self._focused


class _FakeShot:
    def __init__(self, pixel_hash, image):
        self.pixel_hash = pixel_hash
        self.image = image


class _FakeScreen:
    def __init__(self, shot):
        self._shot = shot

    def grab(self):
        return self._shot


class _FakeOCR:
    def __init__(self, regions, available=True):
        self._regions = regions
        self.available = available

    def extract_regions(self, image, min_confidence=None):
        return list(self._regions)


def _make_sensors(title, proc, n_ui, n_ocr, phash):
    ui = [
        UIElement(text=f"u{i}", control_type="Button", bbox=_bbox())
        for i in range(n_ui)
    ]
    ocr = [
        OCRRegion(text=f"o{i}", bbox=_bbox(), confidence=0.9) for i in range(n_ocr)
    ]
    win = WindowInfo(title=title, process_name=proc, pid=1)
    desktop = _FakeDesktop(win, ui)
    ocr_engine = _FakeOCR(ocr)
    screen = _FakeScreen(_FakeShot(phash, object()))  # non-None image triggers OCR
    return desktop, ocr_engine, screen


@settings(max_examples=100)
@given(
    title=st.text(max_size=20),
    proc=st.text(max_size=20),
    n_ui=st.integers(min_value=0, max_value=6),
    n_ocr=st.integers(min_value=0, max_value=6),
    phash=st.text(min_size=1, max_size=16),
)
def test_p1_universal_fused_worldstate(title, proc, n_ui, n_ocr, phash):
    # Feature: m23-browser-generic-desktop-environment, Property 1:
    # Universal fused WorldState — fuses UIA + OCR + pixels, source-ranked,
    # no application/browser/window-title branching. Validates: Requirements 1.1, 1.2, 1.4
    desktop, ocr_engine, screen = _make_sensors(title, proc, n_ui, n_ocr, phash)
    ws = observe_active_window(desktop=desktop, ocr=ocr_engine, screen=screen)

    # Fusion completeness: every provided source is represented.
    assert len(ws.ui_elements) == n_ui
    assert len(ws.ocr_regions) == n_ocr
    assert ws.screenshot_hash == phash
    assert ws.active_window is not None and ws.active_window.title == title

    # Source-agnostic capture: the same counts result regardless of window
    # identity (no title/app branching).
    ws_other = observe_active_window(
        desktop=_FakeDesktop(
            WindowInfo(title="ZZZ_other", process_name="x.exe", pid=9),
            [UIElement(text=f"u{i}", control_type="Button", bbox=_bbox())
             for i in range(n_ui)],
        ),
        ocr=_FakeOCR([OCRRegion(text=f"o{i}", bbox=_bbox(), confidence=0.9)
                      for i in range(n_ocr)]),
        screen=_FakeScreen(_FakeShot(phash, object())),
    )
    assert len(ws_other.ui_elements) == n_ui
    assert len(ws_other.ocr_regions) == n_ocr

    # Rank order (SourcePriority) is UIA > OCR > VISION > PIXEL, independent of window.
    assert SourcePriority.UIA > SourcePriority.OCR
    assert SourcePriority.OCR > SourcePriority.VISION
    assert SourcePriority.VISION > SourcePriority.PIXEL


@settings(max_examples=100)
@given(
    title=st.text(max_size=20),
    proc=st.text(max_size=20),
    n_ui=st.integers(min_value=0, max_value=6),
    n_ocr=st.integers(min_value=0, max_value=6),
    phash=st.text(min_size=1, max_size=16),
)
def test_p12_fusion_is_deterministic(title, proc, n_ui, n_ocr, phash):
    # Feature: m23-browser-generic-desktop-environment, Property 12:
    # Fusion is deterministic/pure over identical sensor inputs.
    # Validates: Requirements 11.1, 11.2
    desktop, ocr_engine, screen = _make_sensors(title, proc, n_ui, n_ocr, phash)
    ws1 = observe_active_window(desktop=desktop, ocr=ocr_engine, screen=screen)
    ws2 = observe_active_window(desktop=desktop, ocr=ocr_engine, screen=screen)

    sig1 = (len(ws1.ui_elements), len(ws1.ocr_regions), ws1.screenshot_hash,
            ws1.active_window.title, ws1.state_hash)
    sig2 = (len(ws2.ui_elements), len(ws2.ocr_regions), ws2.screenshot_hash,
            ws2.active_window.title, ws2.state_hash)
    assert sig1 == sig2


@settings(max_examples=100)
@given(
    n_ui=st.integers(min_value=0, max_value=5),
    n_ocr=st.integers(min_value=0, max_value=5),
    phash=st.text(max_size=16),
)
def test_p2_nonempty_worldstate_without_cdp(n_ui, n_ocr, phash):
    # Feature: m23-browser-generic-desktop-environment, Property 2:
    # A non-empty WorldState is produced from the desktop stack with NO CDP
    # controller present. Validates: Requirements 1.3, 3.2
    from hypothesis import assume

    assume(n_ui + n_ocr > 0 or phash)  # at least one source has content
    ui = [UIElement(text=f"u{i}", control_type="Button", bbox=_bbox()) for i in range(n_ui)]
    ocr = [OCRRegion(text=f"o{i}", bbox=_bbox(), confidence=0.9) for i in range(n_ocr)]
    ws = observe_active_window(
        desktop=_FakeDesktop(WindowInfo(title="w", process_name="p", pid=1), ui),
        ocr=_FakeOCR(ocr),
        screen=_FakeScreen(_FakeShot(phash, object())),  # image always present for OCR
    )
    # No CDP: browser source is absent.
    assert ws.browser_connected is False
    assert ws.browser_elements == []
    # Yet the desktop stack yields a non-empty snapshot.
    non_empty = bool(ws.ui_elements) or bool(ws.ocr_regions) or bool(ws.screenshot_hash)
    assert non_empty


@settings(max_examples=100)
@given(word=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=8))
def test_p3_source_agnostic_reasoning(word):
    # Feature: m23-browser-generic-desktop-environment, Property 3:
    # The reasoning layer resolves a target by World_Object attributes via generic
    # source priority, not by which sensor produced it. Validates: Requirements 1.5, 4.2
    from friday.perception.priority import PerceptionResolver
    from friday.perception.world_state import WorldStateBuilder

    resolver = PerceptionResolver()

    # Same text present in BOTH a UIA element and an OCR region: the higher-ranked
    # (UIA) source wins — the consumer never special-cases the source.
    ui = UIElement(text=word, control_type="Button", bbox=_bbox())
    ocr = OCRRegion(text=word, bbox=_bbox(), confidence=0.9)
    ws_both = (
        WorldStateBuilder().add_ui_elements([ui]).add_ocr_regions([ocr]).build()
    )
    resolved = resolver.find_element(ws_both, word)
    assert resolved is not None and resolved.source == PerceptionSource.UIA

    # Same text present ONLY in OCR: resolution still succeeds by attribute match,
    # now returning the OCR World_Object — source-agnostic matching.
    ws_ocr = WorldStateBuilder().add_ocr_regions([OCRRegion(text=word, bbox=_bbox(), confidence=0.9)]).build()
    resolved_ocr = resolver.find_element(ws_ocr, word)
    assert resolved_ocr is not None and resolved_ocr.source == PerceptionSource.OCR


class _RegionScreen:
    """Fake screen that records the region it was asked to grab."""

    def __init__(self, shot):
        self._shot = shot
        self.last_region = "unset"

    def grab(self, region=None):
        self.last_region = region
        return self._shot


def test_region_scoped_ocr_offsets_coords_to_full_screen():
    # Feature: m23-browser-generic-desktop-environment:
    # window-region-scoped perception reads only the target window and offsets OCR
    # coordinates back into full-screen space so clicks land correctly.
    from friday.perception.active_window import observe_active_window

    # OCR (on the cropped region) reports a word at local (5, 5).
    ocr = _FakeOCR([OCRRegion(text="Result", bbox=BoundingBox(5, 5, 20, 8), confidence=0.9)])
    screen = _RegionScreen(_FakeShot("hash", object()))
    region = (100, 200, 800, 600)

    ws = observe_active_window(desktop=_FakeDesktop(
        WindowInfo(title="w", process_name="p", pid=1), []), ocr=ocr, screen=screen,
        region=region)

    assert screen.last_region == region  # perception was scoped to the window
    assert len(ws.ocr_regions) == 1
    r = ws.ocr_regions[0]
    # local (5,5) offset by region origin (100,200) -> full-screen (105,205)
    assert (r.bbox.x, r.bbox.y) == (105, 205)


def test_no_region_grabs_full_screen():
    from friday.perception.active_window import observe_active_window

    ocr = _FakeOCR([OCRRegion(text="x", bbox=BoundingBox(1, 1, 2, 2), confidence=0.9)])
    screen = _RegionScreen(_FakeShot("h", object()))
    observe_active_window(desktop=_FakeDesktop(
        WindowInfo(title="w", process_name="p", pid=1), []), ocr=ocr, screen=screen)
    assert screen.last_region is None  # full-screen grab when no region given
