from __future__ import annotations

import time
from typing import Any, Optional

from .types import WindowContext


def _rect_center(rect: tuple[int, int, int, int] | None) -> tuple[int, int] | None:
    if not rect:
        return None
    l, t, r, b = rect
    return (int((l + r) / 2), int((t + b) / 2))


def _window_bbox(window: WindowContext | None) -> tuple[int, int, int, int] | None:
    if not window:
        return None
    for el in (window.elements or []):
        if el and el.bounding_rect:
            return el.bounding_rect
    return None


def build_snapshot(
    *,
    window: WindowContext | None,
    win32_window: dict | None = None,
    browser_summary: dict | None,
    browser_error: str | None,
    ocr_text: str | None,
    ocr_error: str | None,
    ocr_confidence: float | None,
    ocr_updated_at: float | None,
    timestamp: float | None = None,
    ocr_word_boxes: list[dict[str, Any]] | None = None,
) -> dict:
    now = time.time() if timestamp is None else float(timestamp)

    browser_hints: dict[str, Any] = {}
    if isinstance(browser_summary, dict):
        hints = browser_summary.get("hints")
        if isinstance(hints, dict):
            browser_hints = hints

    source_flags = {
        "uia": bool(window is not None),
        "browser": bool(browser_summary is not None or browser_error),
        "ocr": bool((ocr_text is not None or ocr_error is not None) and ocr_updated_at is not None),
    }

    win32 = win32_window if isinstance(win32_window, dict) else {}

    win32_title = win32.get("title") if win32 else None
    win32_proc = win32.get("process") if win32 else None
    win32_pid = win32.get("pid") if win32 else None
    win32_bbox = win32.get("bounding_rect") if win32 else None

    uia_title = getattr(window, "title", None) if window is not None else None
    uia_proc = getattr(window, "app_exe", None) if window is not None else None
    uia_pid = getattr(window, "process_id", None) if window is not None else None

    snap = {
        "active_window": {
            "title": uia_title or win32_title,
            "process": uia_proc or win32_proc,
            "pid": uia_pid if uia_pid is not None else win32_pid,
            "bounding_box": _window_bbox(window) or (win32_bbox if isinstance(win32_bbox, tuple) else None),
        },
        "uia": {
            "elements": [
                {
                    "name": el.name,
                    "control_type": el.control_type,
                    "bounding_rect": el.bounding_rect,
                    "focused": el.focused,
                }
                for el in (getattr(window, "elements", None) or [])
            ],
        },
        "browser": {
            "title": (browser_summary or {}).get("title") if isinstance(browser_summary, dict) else None,
            "url": (browser_summary or {}).get("url") if isinstance(browser_summary, dict) else None,
            "summary": browser_summary if isinstance(browser_summary, dict) else None,
            "error": browser_error,
            "error_flags": {
                "has_error": bool(browser_error),
                "has_error_modal": bool(browser_hints.get("has_error_modal")) if browser_hints else False,
                "has_login": bool(browser_hints.get("has_login")) if browser_hints else False,
                "has_form": bool(browser_hints.get("has_form")) if browser_hints else False,
                "has_consent": bool(browser_hints.get("has_consent")) if browser_hints else False,
            },
        },
        "ocr": {
            "text": ocr_text,
            "error": ocr_error,
            "word_boxes": ocr_word_boxes,
            "confidence": ocr_confidence,
            "timestamp": ocr_updated_at,
        },
        "meta": {
            "timestamp": now,
            "poll_age_ms": 0,
            "source_flags": source_flags,
        },
    }
    return snap


def redact_snapshot_for_prompt(snapshot: dict, *, max_elements: int = 10, max_ocr_chars: int = 200) -> str:
    if not isinstance(snapshot, dict) or not snapshot:
        return "(unavailable)"

    lines: list[str] = []

    win = snapshot.get("active_window") if isinstance(snapshot.get("active_window"), dict) else {}
    title = win.get("title")
    proc = win.get("process")
    pid = win.get("pid")
    bbox = win.get("bounding_box")
    lines.append(f"Active window: {title or '(unknown)'} | process={proc or '(unknown)'} | pid={pid or '(unknown)'} | bbox={bbox or '(unknown)'}")

    uia = snapshot.get("uia") if isinstance(snapshot.get("uia"), dict) else {}
    elements = uia.get("elements") if isinstance(uia.get("elements"), list) else []
    focused = None
    for el in elements:
        if isinstance(el, dict) and el.get("focused"):
            focused = el
            break
    if focused:
        lines.append(
            "Focused element: "
            f"{focused.get('name') or '(unnamed)'}"
            f" [{focused.get('control_type') or 'unknown'}]"
        )
    else:
        lines.append("Focused element: (unknown)")

    if elements:
        preview = []
        for el in elements[:max_elements]:
            if not isinstance(el, dict):
                continue
            name = (el.get("name") or "").strip() or "(unnamed)"
            ctype = (el.get("control_type") or "").strip() or "unknown"
            preview.append(f"{name} [{ctype}]")
        lines.append(f"UIA elements (top {min(len(preview), max_elements)} of {len(elements)}): " + ", ".join(preview))
    else:
        lines.append("UIA elements: (none)")

    browser = snapshot.get("browser") if isinstance(snapshot.get("browser"), dict) else {}
    b_title = browser.get("title")
    b_url = browser.get("url")
    flags = browser.get("error_flags") if isinstance(browser.get("error_flags"), dict) else {}
    if b_title or b_url:
        lines.append(f"Browser: {b_title or '(untitled)'} | {b_url or '(no url)'} | flags={flags}")
    else:
        lines.append("Browser: (unavailable)")

    ocr = snapshot.get("ocr") if isinstance(snapshot.get("ocr"), dict) else {}
    ocr_text = ocr.get("text") if isinstance(ocr.get("text"), str) else None
    ocr_err = ocr.get("error") if isinstance(ocr.get("error"), str) else None
    ocr_ts = ocr.get("timestamp")
    if ocr_text:
        clipped = ocr_text[:max_ocr_chars]
        if len(ocr_text) > max_ocr_chars:
            clipped += "…"
        lines.append(f"OCR: '{clipped}' | ts={ocr_ts}")
    elif ocr_err:
        lines.append(f"OCR error: {ocr_err} | ts={ocr_ts}")
    else:
        lines.append("OCR: (none)")

    meta = snapshot.get("meta") if isinstance(snapshot.get("meta"), dict) else {}
    lines.append(f"Meta: ts={meta.get('timestamp')} | poll_age_ms={meta.get('poll_age_ms')} | source_flags={meta.get('source_flags')}")

    return "\n".join(lines)
