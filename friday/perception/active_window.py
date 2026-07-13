"""Universal perception — fuse the active window into one WorldState.

M23 (Browser as a Generic Desktop Environment): the primary execution path must
perceive ANY application — a browser included — through the same desktop
perception stack, never a browser-specific path. This module builds a single
fused ``WorldState`` for the active window from the ranked perception sources:

    Accessibility / UI Automation  (highest trust — semantic)
        -> OCR                     (text from pixels)
        -> raw pixels / screenshot (change detection + vision substrate)

Computer Vision is applied LAZILY at target-resolution time (VisionAdapter /
VisionPerception.locate_element), not eagerly here, because it is a per-query
cost, not a full-window enumeration. The ranking itself lives in
``perception/priority.py::SourcePriority`` (UIA > OCR > VISION > PIXEL); this
module only feeds the sources into the existing ``WorldStateBuilder``.

The builder performs NO application-, browser-, or window-title-specific
branching (Axiom 15): it fuses whatever the injected sensors report for the
active window, whatever that window happens to be.
"""

from __future__ import annotations

from typing import Any, Optional

from friday.perception.world_state import WorldState, WorldStateBuilder


def _default_desktop() -> Optional[Any]:
    """Best-effort DesktopPerception (UIA). Returns None if unavailable.

    Without an awareness state cache, ``get_ui_elements`` returns []; the caller
    (executor) injects a state-cache-backed instance to get the real UIA tree.
    """
    try:
        from friday.perception.desktop import DesktopPerception
        return DesktopPerception()
    except Exception:  # noqa: BLE001 — perception is best-effort; never crash observe
        return None


def _default_ocr() -> Optional[Any]:
    try:
        from friday.perception.ocr import OCREngine
        return OCREngine()
    except Exception:  # noqa: BLE001
        return None


def _default_screen() -> Optional[Any]:
    try:
        from friday.perception.screen import ScreenCapture
        return ScreenCapture()
    except Exception:  # noqa: BLE001
        return None


def populate_active_window(
    builder: WorldStateBuilder,
    *,
    desktop: Optional[Any] = None,
    ocr: Optional[Any] = None,
    screen: Optional[Any] = None,
    vision: Optional[Any] = None,
    want_vision: bool = False,
    region: Optional[tuple] = None,
) -> WorldStateBuilder:
    """Feed the active window's fused desktop perception into ``builder``.

    Mutates and returns ``builder`` after adding UI Automation elements, the
    active window, focus, cursor, a screenshot hash, and OCR regions. Callers
    that also have a browser DOM source (the optional CDP plugin) can call
    ``builder.set_browser_state(...)`` before ``build()`` to fuse it as an
    additional ranked source. Never raises; a missing/failing sensor is skipped.

    ``region`` (x, y, w, h), when given, scopes screenshot + OCR to just the
    active window's rectangle so perception reads the target application and not
    the whole desktop (other windows/terminals). OCR coordinates are offset back
    into full-screen space so downstream clicks land correctly.
    """
    desktop = desktop if desktop is not None else _default_desktop()
    ocr = ocr if ocr is not None else _default_ocr()
    screen = screen if screen is not None else _default_screen()

    # 1. Accessibility / UI Automation — the semantic, highest-trust source.
    if desktop is not None:
        try:
            window = desktop.get_active_window()
            if window is not None:
                builder.set_window_info(window)
        except Exception:  # noqa: BLE001
            pass
        try:
            elements = desktop.get_ui_elements()
            if elements:
                builder.add_ui_elements(elements)
        except Exception:  # noqa: BLE001
            pass
        try:
            cursor = desktop.get_cursor_position()
            if cursor is not None:
                builder.set_cursor_position(int(cursor[0]), int(cursor[1]))
        except Exception:  # noqa: BLE001
            pass
        try:
            focused = desktop.get_focused_element()
            if focused is not None:
                builder.set_focused_element(focused)
        except Exception:  # noqa: BLE001
            pass

    # 2. Pixels + OCR — capture once, hash for change detection, read text.
    #    Scope to the active window's region when provided (read the target app,
    #    not the whole desktop).
    shot = None
    if screen is not None:
        try:
            shot = screen.grab(region=region) if region is not None else screen.grab()
        except Exception:  # noqa: BLE001
            shot = None
    if shot is not None:
        try:
            pixel_hash = getattr(shot, "pixel_hash", "")
            if pixel_hash:
                builder.set_screenshot_hash(pixel_hash)
        except Exception:  # noqa: BLE001
            pass
        image = getattr(shot, "image", None)
        if ocr is not None and image is not None:
            try:
                if getattr(ocr, "available", False):
                    regions = ocr.extract_regions(image)
                    if regions and region is not None:
                        # Region-cropped image -> offset OCR coords back to full-screen.
                        from friday.perception.types import BoundingBox, OCRRegion
                        ox, oy = int(region[0]), int(region[1])
                        regions = [
                            OCRRegion(
                                text=r.text,
                                bbox=BoundingBox(r.bbox.x + ox, r.bbox.y + oy,
                                                 r.bbox.width, r.bbox.height),
                                confidence=r.confidence,
                                language=getattr(r, "language", "en"),
                            )
                            for r in regions
                        ]
                    if regions:
                        builder.add_ocr_regions(regions)
            except Exception:  # noqa: BLE001
                pass

    # 3. Vision is applied lazily at resolution time (VisionAdapter), not here.
    #    `vision`/`want_vision` are accepted for explicit wiring but the fused
    #    snapshot deliberately stays UIA+OCR+pixels to avoid a per-observe VLM cost.

    return builder


def observe_active_window(
    *,
    desktop: Optional[Any] = None,
    ocr: Optional[Any] = None,
    screen: Optional[Any] = None,
    vision: Optional[Any] = None,
    want_vision: bool = False,
    region: Optional[tuple] = None,
) -> WorldState:
    """Build a fused ``WorldState`` for the active window.

    Thin wrapper over :func:`populate_active_window`: fuses UI Automation
    (semantic elements + active window + focus + cursor), OCR text regions, and a
    screenshot hash into one ``WorldState``. Every sensor is optional and
    defaulted lazily; a missing/failing sensor is skipped so a partial
    environment still yields a valid (possibly sparse) ``WorldState``. Never raises.

    ``vision``/``want_vision`` are reserved for lazy, resolution-time use
    (VisionAdapter); the fused snapshot stays UIA+OCR+pixels to avoid a
    per-observe VLM cost.
    """
    builder = WorldStateBuilder()
    populate_active_window(
        builder, desktop=desktop, ocr=ocr, screen=screen,
        vision=vision, want_vision=want_vision, region=region,
    )
    return builder.build()
