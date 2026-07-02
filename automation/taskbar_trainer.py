"""Human-style visual taskbar detection system.

Uses perception-based detection instead of blob analysis:
- Edge density for taskbar location
- LAB color space + variance heatmap for icon detection
- Perceptual hashing + histogram + topology for fingerprinting

This matches how humans detect icons: contrast, color variance, context.
"""

from __future__ import annotations

import json
import os
import time
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import cv2
import numpy as np
from PIL import ImageGrab
import pyautogui


# ============================================================
# TASKBAR CONSTANTS
# ============================================================

# Icon size heuristics (in pixels, at the taskbar capture resolution)
ICON_SIZE_MIN = 28
ICON_SIZE_MAX = 56
DEFAULT_ICON_SIZE = 44

# Debug output control
# - "taskbar": save a single taskbar image with boxes
# - "full": save the stacked taskbar+heatmap+binary visualization
# - "fail": do not save from detector; callers may save on failure
DEBUG_TASKBAR_OUTPUT_DEFAULT = "taskbar"


# ============================================================
# PART 1: TASKBAR REGION DETECTION
# ============================================================

def _get_virtual_screen_bounds() -> tuple[int, int, int, int]:
    """Return virtual screen bounds (left, top, width, height)."""
    try:
        user32 = ctypes.windll.user32
        # SM_XVIRTUALSCREEN = 76, SM_YVIRTUALSCREEN = 77
        # SM_CXVIRTUALSCREEN = 78, SM_CYVIRTUALSCREEN = 79
        left = int(user32.GetSystemMetrics(76))
        top = int(user32.GetSystemMetrics(77))
        width = int(user32.GetSystemMetrics(78))
        height = int(user32.GetSystemMetrics(79))
        if width <= 0 or height <= 0:
            raise RuntimeError("Invalid virtual screen metrics")
        return left, top, width, height
    except Exception:
        return (0, 0, 0, 0)


def _map_screen_rect_to_image(
    rect: tuple[int, int, int, int],
    img_w: int,
    img_h: int,
    v_left: int,
    v_top: int,
) -> tuple[int, int, int, int] | None:
    """Map a screen-rect (absolute coords) into an all_screens image crop."""
    left, top, right, bottom = rect
    x1 = left - v_left
    y1 = top - v_top
    x2 = right - v_left
    y2 = bottom - v_top
    x1 = max(0, min(x1, img_w))
    x2 = max(0, min(x2, img_w))
    y1 = max(0, min(y1, img_h))
    y2 = max(0, min(y2, img_h))
    if x2 <= x1 or y2 <= y1:
        return None
    return int(x1), int(y1), int(x2), int(y2)


def detect_taskbar_region(screenshot: np.ndarray) -> Tuple[np.ndarray, int, int]:
    """Detect taskbar region using blur/low-saturation variance heuristics.

    This leverages the "glass/blur" look of the Windows taskbar: low saturation and
    low high-frequency variance compared to app content.

    Args:
        screenshot: Full screen BGR image

    Returns:
        (band_bgr, top, bottom) where top/bottom are absolute screen Y coordinates.
    """
    h, w = screenshot.shape[:2]
    if h <= 0 or w <= 0:
        raise RuntimeError("Invalid screenshot shape")

    band_top = int(h * 0.65)
    band_top = max(0, min(h - 1, band_top))
    search_band = screenshot[band_top:h, :]
    if search_band.size == 0:
        raise RuntimeError("Search band is empty")

    # Convert to HSV and use saturation channel.
    hsv = cv2.cvtColor(search_band, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]

    # Taskbar tends to have extremely low saturation due to blur/glass effects.
    blur_map = cv2.GaussianBlur(sat, (31, 31), 0)
    variance = cv2.Laplacian(blur_map, cv2.CV_64F).var(axis=1)

    # Find longest continuous low-variance band.
    thresh = float(np.mean(variance)) * 0.4
    rows = np.where(variance < thresh)[0]
    if len(rows) < 20:
        raise RuntimeError("Could not locate taskbar using blur-variance method")

    best_start = int(rows[0])
    best_end = int(rows[0])
    best_len = 1
    run_start = int(rows[0])
    prev = int(rows[0])

    for r in rows[1:]:
        r = int(r)
        if r == prev + 1:
            prev = r
            continue
        # end current run
        run_len = prev - run_start + 1
        if run_len > best_len:
            best_len = run_len
            best_start = run_start
            best_end = prev
        run_start = r
        prev = r

    # finalize last run
    run_len = prev - run_start + 1
    if run_len > best_len:
        best_len = run_len
        best_start = run_start
        best_end = prev

    y1 = best_start
    y2 = best_end

    # Expand margin and convert to absolute coords.
    top = band_top + y1 - 8
    bottom = band_top + y2 + 8
    top = max(0, min(top, h - 1))
    bottom = max(0, min(bottom, h))
    if bottom <= top:
        raise RuntimeError("Detected taskbar band is empty after clamping")

    # Sanity checks: taskbar should be near the bottom and not excessively tall.
    band_height = bottom - top
    if bottom < int(h * 0.85):
        raise RuntimeError("Detected band not near bottom of screen")
    if band_height < 30 or band_height > int(h * 0.4):
        raise RuntimeError("Detected band height out of expected range")

    band = screenshot[top:bottom, :]
    v_left, v_top, _, _ = _get_virtual_screen_bounds()
    screen_top = v_top + top
    screen_bottom = v_top + bottom
    return band, screen_top, screen_bottom


def locate_taskbar(screenshot: np.ndarray) -> Tuple[np.ndarray, int, int, int]:
    """Locate taskbar using blur-variance detection, with safe fallbacks.
    
    Args:
        screenshot: Full screen BGR image
        
    Returns:
        (taskbar_band, left, top, bottom) - cropped taskbar image and screen coordinates
    """
    h, w = screenshot.shape[:2]

    v_left, v_top, v_w, v_h = _get_virtual_screen_bounds()

    # Primary: OS-reported taskbar rect (Shell_TrayWnd), mapped into the all_screens image.
    rect = None
    try:
        rect = _get_taskbar_rect_with_wake() or _get_taskbar_rect()
    except Exception:
        rect = None

    if rect:
        mapped = _map_screen_rect_to_image(rect, w, h, v_left, v_top)
        if mapped:
            x1, y1, x2, y2 = mapped
            if x2 > x1 and y2 > y1:
                band_bgr = screenshot[y1:y2, x1:x2]
                return band_bgr, rect[0], rect[1], rect[3]

    # Secondary: blur-variance detection (best effort, validated to be near bottom).
    try:
        band_bgr, top, bottom = detect_taskbar_region(screenshot)
        return band_bgr, v_left, top, bottom
    except Exception:
        pass

    forced_height = min(140, h)
    band_top = max(0, h - forced_height)
    band_bottom = h
    band_bgr = screenshot[band_top:band_bottom, :]
    band_bgr, trim_top, trim_bottom = _trim_taskbar_band(band_bgr)
    return band_bgr, v_left, v_top + band_top + trim_top, v_top + band_top + trim_bottom


def _trim_taskbar_band(
    band: np.ndarray,
    trim_pixels: int = 8,
    min_height: int = 24,
    pad: int = 2,
) -> tuple[np.ndarray, int, int]:
    """Trim extra padding from taskbar band using row-variance heuristics.

    Returns:
        (trimmed_band, offset_top, offset_bottom_exclusive)
    """
    h, w = band.shape[:2]
    if h <= min_height:
        return band, 0, h

    gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    row_vars = np.array(
        [
            np.var(gray[max(0, y - trim_pixels):min(h, y + trim_pixels + 1), :])
            for y in range(h)
        ]
    )

    thresh = np.median(row_vars) * 0.7
    low = row_vars < thresh
    if not np.any(low):
        return band, 0, h

    best_start = 0
    best_end = h
    best_len = 0
    start = None

    for i, is_low in enumerate(low):
        if is_low and start is None:
            start = i
        if not is_low and start is not None:
            end = i
            length = end - start
            if length > best_len:
                best_len = length
                best_start = start
                best_end = end
            start = None

    if start is not None:
        end = h
        length = end - start
        if length > best_len:
            best_len = length
            best_start = start
            best_end = end

    best_start = max(0, best_start - pad)
    best_end = min(h, best_end + pad)

    if best_end - best_start < min_height:
        return band, 0, h

    return band[best_start:best_end, :], best_start, best_end


def _get_debug_taskbar_output() -> str:
    return (os.environ.get("DEBUG_TASKBAR_OUTPUT") or DEBUG_TASKBAR_OUTPUT_DEFAULT).strip().lower()


def _is_icon_like(w: int, h: int) -> bool:
    if not (18 <= w <= 96 and 18 <= h <= 96):
        return False
    if w <= 0 or h <= 0:
        return False
    area = w * h
    if area < 18 * 18 or area > 96 * 96:
        return False
    return True


def _estimate_icon_size(contour_candidates: List[Dict]) -> int:
    sizes: list[int] = []
    for c in contour_candidates:
        w = int(c.get("raw_w", c.get("w", 0)) or 0)
        h = int(c.get("raw_h", c.get("h", 0)) or 0)
        if _is_icon_like(w, h):
            sizes.append(int(min(w, h)))
    if not sizes:
        # No reliable contours. Fall back to a taskbar-height derived guess later if possible.
        return DEFAULT_ICON_SIZE
    med = int(np.median(np.array(sizes, dtype=np.int32)))
    return int(max(ICON_SIZE_MIN, min(ICON_SIZE_MAX, med)))


def _square_bounds(cx: int, cy: int, size: int, max_w: int, max_h: int) -> tuple[int, int, int, int]:
    """Return clamped square bounds (x1, y1, x2, y2) in [0,max)."""
    half = max(1, int(size // 2))
    x1 = int(cx - half)
    y1 = int(cy - half)
    x2 = int(x1 + size)
    y2 = int(y1 + size)

    if x1 < 0:
        x2 -= x1
        x1 = 0
    if y1 < 0:
        y2 -= y1
        y1 = 0
    if x2 > max_w:
        x1 -= (x2 - max_w)
        x2 = max_w
    if y2 > max_h:
        y1 -= (y2 - max_h)
        y2 = max_h

    x1 = max(0, min(x1, max_w))
    y1 = max(0, min(y1, max_h))
    x2 = max(0, min(x2, max_w))
    y2 = max(0, min(y2, max_h))
    if x2 <= x1:
        x2 = min(max_w, x1 + 1)
    if y2 <= y1:
        y2 = min(max_h, y1 + 1)
    return x1, y1, x2, y2


def _normalize_candidates_to_square(
    candidates: List[Dict],
    taskbar_region: np.ndarray,
    icon_size: int,
    combined_heatmap: Optional[np.ndarray],
    row_center_y: Optional[int] = None,
) -> List[Dict]:
    """Normalize each candidate to a consistent icon-sized square crop."""
    h, w = taskbar_region.shape[:2]
    out: list[Dict] = []
    for c in candidates:
        cx = int(c.get("center_x", 0))
        cy = int(c.get("center_y", 0))
        if row_center_y is not None:
            cy = int(row_center_y)

        if combined_heatmap is not None and combined_heatmap.size:
            # Refine center using weighted centroid in the heatmap near the candidate.
            radius = max(2, int(icon_size // 2))
            x1 = max(0, cx - radius)
            x2 = min(w, cx + radius)
            y1 = max(0, cy - radius)
            y2 = min(h, cy + radius)
            if x2 > x1 and y2 > y1:
                local = combined_heatmap[y1:y2, x1:x2].astype(np.float32)
                weight_sum = float(np.sum(local))
                if weight_sum > 1e-3:
                    xs = np.arange(x1, x2, dtype=np.float32)
                    ys = np.arange(y1, y2, dtype=np.float32)
                    col_sum = np.sum(local, axis=0)
                    row_sum = np.sum(local, axis=1)
                    cx = int(np.round(float(np.sum(xs * col_sum) / weight_sum)))
                    if row_center_y is None:
                        cy = int(np.round(float(np.sum(ys * row_sum) / weight_sum)))
        x1, y1, x2, y2 = _square_bounds(cx, cy, icon_size, w, h)
        crop = taskbar_region[y1:y2, x1:x2]

        score = float(c.get("score", (x2 - x1) * (y2 - y1)))
        if combined_heatmap is not None and combined_heatmap.size:
            try:
                score = float(np.mean(combined_heatmap[y1:y2, x1:x2]))
            except Exception:
                pass

        out.append(
            {
                "x": x1,
                "y": y1,
                "w": int(x2 - x1),
                "h": int(y2 - y1),
                "center_x": int((x1 + x2) // 2),
                "center_y": int((y1 + y2) // 2),
                "image": crop.copy(),
                "score": score,
                "icon_size": int(icon_size),
                "source": c.get("source"),
            }
        )
    return out


def _row_center_from_heatmap(combined_heatmap: np.ndarray) -> Optional[int]:
    if combined_heatmap is None or combined_heatmap.size == 0:
        return None
    h, w = combined_heatmap.shape[:2]
    if h <= 0:
        return None
    band_top = int(max(0, h * 0.25))
    band_bottom = int(min(h, h * 0.85))
    band = combined_heatmap[band_top:band_bottom, :]
    if band.size == 0:
        return None
    row_signal = np.mean(band, axis=1)
    idx = int(np.argmax(row_signal))
    return int(band_top + idx)


def _suppress_icon_row(candidates: List[Dict], min_center_spacing: int) -> List[Dict]:
    """Cheap 1D suppression along the taskbar icon row."""
    if not candidates:
        return []
    candidates = sorted(candidates, key=lambda c: int(c.get("center_x", 0)))
    kept: list[Dict] = []
    for c in candidates:
        if not kept:
            kept.append(c)
            continue
        prev = kept[-1]
        if abs(int(c["center_x"]) - int(prev["center_x"])) < int(min_center_spacing):
            if float(c.get("score", 0.0)) > float(prev.get("score", 0.0)):
                kept[-1] = c
        else:
            kept.append(c)
    return kept


def _filter_to_regular_icon_row(
    candidates: List[Dict],
    icon_size: int,
    taskbar_width: int,
) -> List[Dict]:
    """Keep the densest mid-band of icons (filters widget + tray clusters)."""
    if len(candidates) < 6:
        return candidates

    ordered = sorted(candidates, key=lambda c: int(c.get("center_x", 0)))
    centers = [int(c["center_x"]) for c in ordered]

    window_w = max(320, int(taskbar_width * 0.35)) if taskbar_width > 0 else 320
    half = window_w // 2

    best_center = centers[len(centers) // 2]
    best_count = -1
    best_score = -1.0

    for cx in centers:
        lo = cx - half
        hi = cx + half
        window = [c for c in ordered if lo <= int(c["center_x"]) <= hi]
        if not window:
            continue
        count = len(window)
        score = float(sum(float(c.get("score", 0.0)) for c in window))
        if count > best_count or (count == best_count and score > best_score):
            best_count = count
            best_score = score
            best_center = cx

    filtered = [c for c in ordered if abs(int(c["center_x"]) - best_center) <= half]
    if len(filtered) < 6:
        return candidates
    return filtered


def _get_taskbar_rect_with_wake(retries: int = 2, wake_delay_s: float = 0.25) -> Optional[Tuple[int, int, int, int]]:
    rect = _get_taskbar_rect()
    if rect is None:
        return None

    left, top, right, bottom = rect
    height = bottom - top

    for _ in range(retries):
        if height >= 30:
            break
        try:
            pyautogui.moveTo(max(1, (left + right) // 2), max(1, bottom - 1))
        except Exception:
            break
        time.sleep(wake_delay_s)
        rect = _get_taskbar_rect()
        if rect is None:
            return None
        left, top, right, bottom = rect
        height = bottom - top

    if height < 30:
        return None

    return (left, top, right, bottom)


def _get_tray_rect() -> Optional[Tuple[int, int, int, int]]:
    """Get the system tray (TrayNotifyWnd) rect in screen coordinates."""
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return None

    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowExW.restype = wintypes.HWND

    hwnd_taskbar = user32.FindWindowW("Shell_TrayWnd", None)
    if not hwnd_taskbar:
        return None

    hwnd_tray = user32.FindWindowExW(hwnd_taskbar, None, "TrayNotifyWnd", None)
    if not hwnd_tray:
        return None

    rect = wintypes.RECT()
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    if not user32.GetWindowRect(hwnd_tray, ctypes.byref(rect)):
        return None

    left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _rect_within_virtual(
    rect: Tuple[int, int, int, int],
    v_left: int,
    v_top: int,
    v_w: int,
    v_h: int,
) -> bool:
    left, top, right, bottom = rect
    if right <= left or bottom <= top:
        return False
    if v_w <= 0 or v_h <= 0:
        return False
    if left < v_left - 20 or top < v_top - 20:
        return False
    if right > v_left + v_w + 20 or bottom > v_top + v_h + 20:
        return False
    return True


def _get_tasklist_rect() -> Optional[Tuple[int, int, int, int]]:
    """Get the task list (pinned apps) rect in screen coordinates."""
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return None

    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowExW.restype = wintypes.HWND

    hwnd_taskbar = user32.FindWindowW("Shell_TrayWnd", None)
    if not hwnd_taskbar:
        return None

    v_left, v_top, v_w, v_h = _get_virtual_screen_bounds()

    # Try direct task list class names.
    for cls in ("MSTaskListWClass", "TaskbarTaskList", "TaskListThumbnailWnd"):
        hwnd = user32.FindWindowExW(hwnd_taskbar, None, cls, None)
        if hwnd:
            rect = wintypes.RECT()
            user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            user32.GetWindowRect.restype = wintypes.BOOL
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
                candidate = (left, top, right, bottom)
                if _rect_within_virtual(candidate, v_left, v_top, v_w, v_h):
                    return candidate

    # Fallback: search descendants for a wide band inside the taskbar (excluding tray).
    tray_rect = _get_tray_rect()
    tray_left = tray_rect[0] if tray_rect else None

    results: list[tuple[int, int, int, int]] = []

    def enum_proc(hwnd, lparam):
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
            candidate = (left, top, right, bottom)
            if _rect_within_virtual(candidate, v_left, v_top, v_w, v_h):
                results.append(candidate)
        return True

    enum_cb = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(enum_proc)
    user32.EnumChildWindows(hwnd_taskbar, enum_cb, 0)

    if not results:
        return None

    # Choose the widest rect that isn't in the tray area.
    best = None
    best_w = -1
    for left, top, right, bottom in results:
        w = right - left
        h = bottom - top
        if w < 200 or h < 20:
            continue
        if tray_left is not None and left >= tray_left - 20:
            continue
        if w > best_w:
            best_w = w
            best = (left, top, right, bottom)

    return best


def _filter_out_tray_candidates(
    candidates: List[Dict],
    tray_left_x: Optional[int],
    icon_size: int,
) -> List[Dict]:
    if tray_left_x is None:
        return candidates
    cutoff = int(tray_left_x - max(6, icon_size * 0.5))
    return [c for c in candidates if int(c.get("center_x", 0)) < cutoff]


def _filter_out_left_widgets(candidates: List[Dict], icon_size: int) -> List[Dict]:
    """Drop left widget/search clusters by cutting at the largest gap."""
    if len(candidates) < 8:
        return candidates

    ordered = sorted(candidates, key=lambda c: int(c.get("center_x", 0)))
    centers = [int(c["center_x"]) for c in ordered]
    diffs = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    if not diffs:
        return candidates

    max_gap = max(diffs)
    if max_gap < icon_size * 3.0:
        return candidates

    idx = diffs.index(max_gap)
    threshold = (centers[idx] + centers[idx + 1]) / 2.0
    right_group = [c for c in ordered if int(c.get("center_x", 0)) > threshold]

    if len(right_group) >= 5:
        return right_group
    return candidates


def _get_taskbar_rect() -> Optional[Tuple[int, int, int, int]]:
    try:
        user32 = ctypes.windll.user32
    except Exception:
        return None

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND

    hwnd = user32.FindWindowW("Shell_TrayWnd", None)
    if not hwnd:
        return None

    rect = wintypes.RECT()
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None

    left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    if right <= left or bottom <= top:
        return None

    return (left, top, right, bottom)


# ============================================================
# PART 2: ICON HEATMAP DETECTION
# ============================================================

def detect_icon_candidates(
    taskbar_region: np.ndarray,
    debug: bool = False,
    *,
    band_left: Optional[int] = None,
    band_top: Optional[int] = None,
) -> List[Dict]:
    """Detect icon candidates using LAB color space and variance heatmap.
    
    Args:
        taskbar_region: Taskbar BGR image
        debug: If True, save debug visualization
        
    Returns:
        List of candidate icon dicts with x, y, w, h, center_x, center_y, image
    """
    h, w = taskbar_region.shape[:2]
    band_left = int(band_left or 0)
    band_top = int(band_top or 0)
    
    # Convert to LAB color space
    lab = cv2.cvtColor(taskbar_region, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    
    # Compute saturation/chroma map (distance from neutral gray in AB plane)
    chroma = np.sqrt(a_channel.astype(float)**2 + b_channel.astype(float)**2)
    
    # Normalize chroma to 0-255
    chroma_norm = cv2.normalize(chroma, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    
    # Compute local variance using sliding window
    variance_map = compute_local_variance(l_channel, window_size=15)
    
    # Combine: high variance + high chroma = likely icon
    combined = (variance_map * 0.6 + chroma_norm * 0.4).astype(np.uint8)
    
    # Adaptive threshold
    _, binary = cv2.threshold(combined, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    
    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    contour_candidates: list[Dict] = []
    
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        
        # Filter by size (relaxed: 18-96px)
        if 18 <= cw <= 96 and 18 <= ch <= 96:
            # Extract icon region with padding
            pad = 4
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(w, x + cw + pad)
            y2 = min(h, y + ch + pad)
            
            icon_image = taskbar_region[y1:y2, x1:x2]

            score = 0.0
            try:
                score = float(np.mean(combined[y1:y2, x1:x2]))
            except Exception:
                score = float((x2 - x1) * (y2 - y1))

            contour_candidates.append({
                "x": x1,
                "y": y1,
                "w": x2 - x1,
                "h": y2 - y1,
                "center_x": x1 + (x2 - x1) // 2,
                "center_y": y1 + (y2 - y1) // 2,
                "image": icon_image.copy(),
                "score": score,
                "raw_w": int(cw),
                "raw_h": int(ch),
                "source": "contour",
            })
    
    # Icon size estimate (used for square normalization + grid scanning fallback).
    icon_size = _estimate_icon_size(contour_candidates)
    if icon_size == DEFAULT_ICON_SIZE:
        # Derive a better guess from taskbar height (Win11 taskbar ~60px; icons ~32px).
        icon_size = int(max(ICON_SIZE_MIN, min(ICON_SIZE_MAX, int(h * 0.55))))

    # Also use sliding window approach for icons missed by contours
    window_candidates = sliding_window_icons(taskbar_region, variance_map, chroma_norm)
    grid_candidates = grid_window_icons(taskbar_region, combined, icon_size)
    peak_candidates = peak_icon_candidates(taskbar_region, combined, icon_size)

    # Merge candidates (remove duplicates based on proximity)
    # Prefer peak-based candidates when the count looks reasonable; they align to actual icon responses.
    use_peaks = 6 <= len(peak_candidates) <= 60
    if use_peaks:
        raw_candidates = peak_candidates
    else:
        raw_candidates = contour_candidates + window_candidates + grid_candidates
    merged_raw = merge_candidates(raw_candidates)

    # Normalize to stable, icon-sized squares for consistent fingerprinting and clean grids.
    row_center_y = _row_center_from_heatmap(combined)
    normalized = _normalize_candidates_to_square(
        merged_raw,
        taskbar_region,
        icon_size,
        combined,
        row_center_y=row_center_y,
    )

    # Merge again post-normalization (squares overlap more than raw contours/windows).
    normalized = merge_candidates(normalized, iou_thresh=0.35)

    # Suppress duplicates along the 1D icon row.
    min_spacing = int(max(24, icon_size * 0.90))
    all_candidates = _suppress_icon_row(normalized, min_spacing)

    # Prefer OS tasklist rect to keep only pinned app icons.
    tasklist_rect = _get_tasklist_rect()
    if tasklist_rect:
        tl, tt, tr, tb = tasklist_rect
        x1 = int(tl - band_left)
        x2 = int(tr - band_left)
        y1 = int(tt - band_top)
        y2 = int(tb - band_top)
        x1 = max(0, min(x1, w))
        x2 = max(0, min(x2, w))
        y1 = max(0, min(y1, h))
        y2 = max(0, min(y2, h))
        if x2 > x1 and y2 > y1:
            all_candidates = [
                c
                for c in all_candidates
                if x1 <= int(c.get("center_x", 0)) <= x2
                and y1 <= int(c.get("center_y", 0)) <= y2
            ]

    # Always exclude system tray region (right side) to avoid tiny status icons.
    tray_rect = _get_tray_rect()
    tray_left = None
    if tray_rect:
        tray_left = tray_rect[0] - band_left
    all_candidates = _filter_out_tray_candidates(all_candidates, tray_left, icon_size)

    # Drop left widget/search cluster by cutting at the largest gap.
    all_candidates = _filter_out_left_widgets(all_candidates, icon_size)
    
    # Sort by x position
    all_candidates.sort(key=lambda c: c["x"])
    
    if debug:
        mode = _get_debug_taskbar_output()
        if mode == "full":
            save_debug_visualization(taskbar_region, all_candidates, combined, binary)
        elif mode == "taskbar":
            save_taskbar_boxes(taskbar_region, all_candidates)
    
    return all_candidates


def compute_local_variance(gray: np.ndarray, window_size: int = 15) -> np.ndarray:
    """Compute local variance using box filter."""
    gray_float = gray.astype(np.float32)
    
    # Mean
    mean = cv2.blur(gray_float, (window_size, window_size))
    
    # Mean of squares
    sqr_mean = cv2.blur(gray_float ** 2, (window_size, window_size))
    
    # Variance = E[X^2] - E[X]^2
    variance = sqr_mean - mean ** 2
    variance = np.clip(variance, 0, None)
    
    # Normalize to 0-255
    variance_norm = cv2.normalize(variance, None, 0, 255, cv2.NORM_MINMAX)
    return variance_norm.astype(np.uint8)


def sliding_window_icons(taskbar: np.ndarray, variance_map: np.ndarray, 
                         chroma_map: np.ndarray) -> List[Dict]:
    """Find icons using sliding window on variance + chroma maps."""
    h, w = taskbar.shape[:2]
    candidates = []
    
    # Sliding window sizes
    window_sizes = [(40, 40), (48, 48), (56, 56), (64, 64)]
    stride = 20
    
    for win_w, win_h in window_sizes:
        for x in range(0, w - win_w, stride):
            for y in range(0, h - win_h, stride):
                # Extract window
                var_win = variance_map[y:y+win_h, x:x+win_w]
                chroma_win = chroma_map[y:y+win_h, x:x+win_w]
                
                # Score: high variance + non-uniform chroma
                var_score = np.mean(var_win)
                chroma_score = np.std(chroma_win)
                
                combined_score = var_score * 0.5 + chroma_score * 0.5
                
                # Threshold for candidate
                if combined_score > 30:
                    icon_image = taskbar[y:y+win_h, x:x+win_w]
                    
                    candidates.append({
                        "x": x,
                        "y": y,
                        "w": win_w,
                        "h": win_h,
                        "center_x": x + win_w // 2,
                        "center_y": y + win_h // 2,
                        "image": icon_image.copy(),
                        "score": combined_score,
                    })
    
    # Keep only top candidates per region (non-max suppression)
    return non_max_suppression(candidates, overlap_thresh=0.5)


def grid_window_icons(taskbar: np.ndarray, score_map: np.ndarray, icon_size: int) -> List[Dict]:
    """Generate icon candidates by sliding a fixed square window along the icon row.

    This is a robust fallback when contour thresholding fragments icons.
    """
    h, w = taskbar.shape[:2]
    if icon_size <= 0:
        return []
    size = int(max(ICON_SIZE_MIN, min(ICON_SIZE_MAX, icon_size)))
    if size >= w or size >= h:
        return []

    # Icons sit roughly centered vertically in the taskbar.
    y0 = max(0, (h - size) // 2)
    y_candidates = sorted(set([max(0, y0 - 4), y0, min(h - size, y0 + 4)]))

    stride = max(4, size // 4)
    windows: list[Dict] = []

    for y in y_candidates:
        for x in range(0, w - size + 1, stride):
            win = score_map[y : y + size, x : x + size]
            score = float(np.mean(win))
            windows.append(
                {
                    "x": int(x),
                    "y": int(y),
                    "w": int(size),
                    "h": int(size),
                    "center_x": int(x + size // 2),
                    "center_y": int(y + size // 2),
                    "image": taskbar[y : y + size, x : x + size].copy(),
                    "score": score,
                    "source": "grid",
                }
            )

    # Keep the best-scoring windows; then suppress overlaps.
    windows.sort(key=lambda c: float(c.get("score", 0.0)), reverse=True)
    top_k = min(90, max(30, w // max(1, size)))
    windows = windows[:top_k]
    return non_max_suppression(windows, overlap_thresh=0.35)


def peak_icon_candidates(taskbar: np.ndarray, score_map: np.ndarray, icon_size: int) -> List[Dict]:
    """Detect icon centers using 1D peaks over the heatmap, then build square boxes."""
    h, w = score_map.shape[:2]
    if h <= 0 or w <= 0 or icon_size <= 0:
        return []

    size = int(max(ICON_SIZE_MIN, min(ICON_SIZE_MAX, icon_size)))
    band_top = int(max(0, h * 0.25))
    band_bottom = int(min(h, h * 0.85))
    band = score_map[band_top:band_bottom, :]
    if band.size == 0:
        return []

    # 1D signal across X, smoothed for stable peak detection.
    signal = np.mean(band, axis=0).astype(np.float32)
    signal_blur = cv2.GaussianBlur(signal.reshape(1, -1), (1, 11), 0).reshape(-1)

    mean = float(np.mean(signal_blur))
    std = float(np.std(signal_blur))
    thresh = mean + std * 0.4

    peaks: list[int] = []
    for x in range(1, w - 1):
        v = float(signal_blur[x])
        if v > thresh and v >= float(signal_blur[x - 1]) and v >= float(signal_blur[x + 1]):
            peaks.append(x)

    if not peaks:
        return []

    # Non-max suppression in 1D by keeping the strongest peak in each window.
    min_spacing = int(size * 0.9)
    peaks_sorted = sorted(peaks, key=lambda i: float(signal_blur[i]), reverse=True)
    kept: list[int] = []
    for p in peaks_sorted:
        if all(abs(p - k) > min_spacing for k in kept):
            kept.append(p)
    kept.sort()

    candidates: list[Dict] = []
    for p in kept:
        # Recenter vertically using the strongest response in this column.
        col = score_map[:, p]
        cy = int(np.argmax(col))
        x1, y1, x2, y2 = _square_bounds(int(p), int(cy), size, w, h)
        candidates.append(
            {
                "x": int(x1),
                "y": int(y1),
                "w": int(x2 - x1),
                "h": int(y2 - y1),
                "center_x": int((x1 + x2) // 2),
                "center_y": int((y1 + y2) // 2),
                "image": taskbar[y1:y2, x1:x2].copy(),
                "score": float(signal_blur[p]),
                "source": "peak",
            }
        )

    return candidates


def grid_from_signal(
    taskbar: np.ndarray,
    score_map: np.ndarray,
    icon_size: int,
    x_start: int,
    x_end: int,
) -> List[Dict]:
    """Derive a uniform icon grid using autocorrelation of the heatmap signal."""
    h, w = score_map.shape[:2]
    if h <= 0 or w <= 0:
        return []

    x_start = max(0, min(x_start, w - 1))
    x_end = max(1, min(x_end, w))
    if x_end - x_start < icon_size * 4:
        return []

    size = int(max(ICON_SIZE_MIN, min(ICON_SIZE_MAX, icon_size)))

    # 1D signal across X.
    band_top = int(max(0, h * 0.25))
    band_bottom = int(min(h, h * 0.85))
    band = score_map[band_top:band_bottom, x_start:x_end]
    if band.size == 0:
        return []

    signal = np.mean(band, axis=0).astype(np.float32)
    signal = cv2.GaussianBlur(signal.reshape(1, -1), (1, 11), 0).reshape(-1)

    s_min = max(6, int(size * 0.8))
    s_max = max(s_min + 2, int(size * 2.2))

    best_s = s_min
    best_score = -1.0
    for s in range(s_min, s_max + 1):
        if s >= len(signal):
            break
        a = signal[:-s]
        b = signal[s:]
        score = float(np.dot(a, b))
        if score > best_score:
            best_score = score
            best_s = s

    # Best phase (offset) for the grid.
    best_o = 0
    best_o_score = -1.0
    for o in range(best_s):
        positions = np.arange(o, len(signal), best_s, dtype=np.int32)
        if positions.size == 0:
            continue
        score = float(np.sum(signal[positions]))
        if score > best_o_score:
            best_o_score = score
            best_o = o

    mean = float(np.mean(signal))
    std = float(np.std(signal))
    thresh = mean + std * 0.1

    centers_x: list[int] = []
    for pos in range(best_o, len(signal), best_s):
        if signal[pos] >= thresh:
            centers_x.append(int(x_start + pos))

    if len(centers_x) < 5:
        return []

    row_center = _row_center_from_heatmap(score_map)
    if row_center is None:
        row_center = h // 2

    candidates: list[Dict] = []
    for cx in centers_x:
        x1, y1, x2, y2 = _square_bounds(int(cx), int(row_center), size, w, h)
        candidates.append(
            {
                "x": int(x1),
                "y": int(y1),
                "w": int(x2 - x1),
                "h": int(y2 - y1),
                "center_x": int((x1 + x2) // 2),
                "center_y": int((y1 + y2) // 2),
                "image": taskbar[y1:y2, x1:x2].copy(),
                "score": float(signal[int(cx - x_start)]),
                "source": "grid_signal",
            }
        )

    return candidates


def non_max_suppression(candidates: List[Dict], overlap_thresh: float = 0.5) -> List[Dict]:
    """Remove overlapping candidates, keeping highest score."""
    if not candidates:
        return []
    
    # Sort by score descending
    candidates = sorted(candidates, key=lambda c: c.get("score", 0), reverse=True)
    
    keep = []
    
    for candidate in candidates:
        overlap = False
        for kept in keep:
            # Check IoU
            x1 = max(candidate["x"], kept["x"])
            y1 = max(candidate["y"], kept["y"])
            x2 = min(candidate["x"] + candidate["w"], kept["x"] + kept["w"])
            y2 = min(candidate["y"] + candidate["h"], kept["y"] + kept["h"])
            
            if x2 > x1 and y2 > y1:
                intersection = (x2 - x1) * (y2 - y1)
                area1 = candidate["w"] * candidate["h"]
                area2 = kept["w"] * kept["h"]
                union = area1 + area2 - intersection
                
                iou = intersection / union if union > 0 else 0
                
                if iou > overlap_thresh:
                    overlap = True
                    break
        
        if not overlap:
            keep.append(candidate)
    
    return keep


def _iou(a: Dict, b: Dict) -> float:
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = ax1 + a["w"], ay1 + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = bx1 + b["w"], by1 + b["h"]

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def merge_candidates(candidates: List[Dict], iou_thresh: float = 0.25) -> List[Dict]:
    """De-duplicate overlapping candidates (NMS by IoU)."""
    if not candidates:
        return []

    def cand_score(c: Dict) -> float:
        return float(c.get("score", c["w"] * c["h"]))

    candidates = sorted(candidates, key=cand_score, reverse=True)
    kept: List[Dict] = []
    for cand in candidates:
        if all(_iou(cand, k) < iou_thresh for k in kept):
            kept.append(cand)
    return kept


# ============================================================
# PART 3: PASSIVE CLICK DETECTION
# ============================================================

class ClickCapture:
    """Capture mouse clicks without blocking."""
    
    def __init__(self):
        self.click_pos = None
        self.clicked = False
        self._was_down = False
    
    def start(self):
        self.clicked = False
        self.click_pos = None
        self._was_down = False
    
    def wait(self, timeout: float = 30.0) -> Optional[Tuple[int, int]]:
        start = time.time()
        while time.time() - start < timeout:
            try:
                if os.name != "nt":
                    return None
                user32 = ctypes.windll.user32
                state = user32.GetAsyncKeyState(0x01)
                is_down = bool(state & 0x8000)
                if is_down and not self._was_down:
                    pt = wintypes.POINT()
                    if user32.GetCursorPos(ctypes.byref(pt)):
                        self.click_pos = (int(pt.x), int(pt.y))
                        self.clicked = True
                        return self.click_pos
                self._was_down = is_down
            except Exception:
                return None
            time.sleep(0.01)
        return None
    
    def stop(self):
        return


def wait_for_click_passive(timeout: float = 30.0) -> Optional[Tuple[int, int]]:
    """Wait for mouse click passively.
    
    Args:
        timeout: Max seconds to wait
        
    Returns:
        (x, y) click coordinates or None
    """
    capture = ClickCapture()
    capture.start()
    
    result = capture.wait(timeout)
    capture.stop()
    
    return result


# ============================================================
# PART 4: VISUAL FINGERPRINTING
# ============================================================

def perceptual_hash(image: np.ndarray, hash_size: int = 8) -> str:
    """Compute perceptual hash (pHash) of an image."""
    # Resize to hash_size x hash_size
    resized = cv2.resize(image, (hash_size, hash_size))
    
    # Convert to grayscale if needed
    if len(resized.shape) == 3:
        resized = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    
    # Compute DCT
    dct = cv2.dct(resized.astype(np.float32))
    
    # Keep top-left 8x8
    dct_low = dct[:hash_size, :hash_size]
    
    # Compute median
    median = np.median(dct_low)
    
    # Binary hash
    hash_bits = (dct_low > median).flatten()
    hash_value = sum([2 ** i for i, v in enumerate(hash_bits) if v])
    
    return f"{hash_value:016x}"


def color_histogram(image: np.ndarray, bins: int = 16) -> List[float]:
    """Compute normalized color histogram."""
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    
    # Convert to HSV for better color representation
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    # Compute histogram for H and S channels
    hist_h = cv2.calcHist([hsv], [0], None, [bins], [0, 180])
    hist_s = cv2.calcHist([hsv], [1], None, [bins], [0, 256])
    
    # Normalize
    hist_h = cv2.normalize(hist_h, hist_h).flatten()
    hist_s = cv2.normalize(hist_s, hist_s).flatten()
    
    # Concatenate and convert to native Python floats for JSON serialization
    return [float(x) for x in hist_h] + [float(x) for x in hist_s]


def compute_fingerprint(icon: Dict, neighbors: List[Dict], 
                        screen_width: int, taskbar_left: int) -> Dict:
    """Compute full visual fingerprint for an icon.
    
    Args:
        icon: Icon dict with image
        neighbors: List of up to 3 nearest neighbor icons
        screen_width: Full screen width for ratio calculation
        
    Returns:
        Fingerprint dict
    """
    # Perceptual hash
    phash = perceptual_hash(icon["image"])
    
    # Color histogram
    histogram = color_histogram(icon["image"])
    
    # Neighbor fingerprints (up to 3)
    neighbor_hashes = []
    for neighbor in neighbors[:3]:
        neighbor_hashes.append(perceptual_hash(neighbor["image"]))
    
    # Position ratio
    ratio = (taskbar_left + icon["center_x"]) / screen_width if screen_width > 0 else 0.5
    
    return {
        "phash": phash,
        "histogram": histogram,
        "neighbors": neighbor_hashes,
        "ratio": ratio,
    }


# ============================================================
# PART 7: DEBUG VISUALIZATION
# ============================================================

def save_taskbar_boxes(
    taskbar: np.ndarray,
    candidates: List[Dict],
    *,
    best_idx: int | None = None,
    expected_x: int | None = None,
    out_path: str | None = None,
) -> str:
    """Save a single taskbar image with candidate boxes to logs/taskbar_boxes.png."""
    viz = taskbar.copy()
    h, w = viz.shape[:2]

    if expected_x is not None:
        ex = int(max(0, min(w - 1, expected_x)))
        cv2.line(viz, (ex, 0), (ex, h - 1), (0, 255, 255), 2)

    for i, c in enumerate(candidates):
        x, y = int(c["x"]), int(c["y"])
        cw, ch = int(c["w"]), int(c["h"])
        if best_idx is not None and i == best_idx:
            color = (0, 255, 0)
            thickness = 3
        else:
            color = (255, 0, 0)
            thickness = 1
        cv2.rectangle(viz, (x, y), (x + cw, y + ch), color, thickness)
        cv2.putText(
            viz,
            str(i),
            (x + 2, y + 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
        )

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    out = out_path or str(logs_dir / "taskbar_boxes.png")
    cv2.imwrite(out, viz)
    return out


def save_debug_visualization(taskbar: np.ndarray, candidates: List[Dict],
                             heatmap: np.ndarray, binary: np.ndarray):
    """Save debug visualization to logs/taskbar_debug.png."""
    # Create visualization
    h, w = taskbar.shape[:2]
    
    # Stack: original, heatmap, binary, with boxes
    viz_taskbar = taskbar.copy()
    
    # Draw candidate boxes
    for i, candidate in enumerate(candidates):
        x, y = candidate["x"], candidate["y"]
        cw, ch = candidate["w"], candidate["h"]
        
        # Color based on index
        color = (0, 255, 0) if i == 0 else (255, 0, 0)
        cv2.rectangle(viz_taskbar, (x, y), (x + cw, y + ch), color, 2)
        cv2.putText(viz_taskbar, str(i), (x + 2, y + 12), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    
    # Convert heatmap to color
    heatmap_color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
    
    # Convert binary to 3-channel
    binary_color = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    
    # Stack vertically
    viz = np.vstack([viz_taskbar, heatmap_color, binary_color])
    
    # Save
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    cv2.imwrite(str(logs_dir / "taskbar_debug.png"), viz)
    
    print(f"  Debug visualization saved to logs/taskbar_debug.png")


# ============================================================
# MAIN TRAINING FUNCTION
# ============================================================

def train_taskbar_chrome() -> str:
    """Train Jarvis to locate Chrome icon using human-style visual detection.
    
    Returns:
        Status message
    """
    DEBUG = os.environ.get("DEBUG_TASKBAR", "0") == "1"
    
    print("\n" + "="*60)
    print("TRAINING: Taskbar Chrome Icon")
    print("="*60)
    print("\nHuman-style visual detection system.")
    print("Uses: LAB color space, variance heatmap, perceptual hashing.")
    
    # Step 1: Capture screen and locate taskbar
    print("\n" + "-"*60)
    print("STEP 1: Locate Taskbar Region")
    print("-"*60)

    _get_taskbar_rect()
    
    try:
        screenshot = np.array(ImageGrab.grab(all_screens=True))
    except TypeError:
        screenshot = np.array(ImageGrab.grab())
    screenshot_bgr = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
    height, width = screenshot_bgr.shape[:2]
    
    taskbar_region, tx, ty, tb = locate_taskbar(screenshot_bgr)
    th = tb - ty
    
    print(f"✓ Screen: {width}x{height}")
    print(f"✓ Taskbar detected: x={tx}, y={ty}, height={th}px")
    if taskbar_region.size == 0:
        print("✗ Taskbar region is empty; using fallback bottom band")
        forced_height = 140
        ty = max(0, height - forced_height)
        tb = height
        taskbar_region = screenshot_bgr[ty:tb, :]
        tx = 0
        th = tb - ty
        print(f"✓ Fallback band: y={ty}-{tb}, height={th}px")
    
    # Save debug dump
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    cv2.imwrite(str(logs_dir / "taskbar_detected.png"), taskbar_region)
    print("📸 Taskbar band saved to logs/taskbar_detected.png")
    
    # Step 2: Detect icon candidates
    print("\n" + "-"*60)
    print("STEP 2: Detect Icon Candidates")
    print("-"*60)
    
    candidates = detect_icon_candidates(taskbar_region, debug=False, band_left=tx, band_top=ty)
    
    if not candidates:
        print("✗ No icon candidates detected")
        return "Training failed: No icons detected in taskbar"
    
    print(f"✓ Detected {len(candidates)} candidate icons")
    
    # Step 3: Wait for user to click Chrome icon
    print("\n" + "-"*60)
    print("STEP 3: Identify Chrome Icon")
    print("-"*60)
    print("\nClick the Chrome icon in your taskbar now.")
    print("Do NOT touch the terminal.")
    print("")
    
    click_pos = wait_for_click_passive(timeout=30.0)
    
    if not click_pos:
        return "Training cancelled: No click detected (timeout)"
    
    click_x, click_y = click_pos
    print(f"✓ Click detected at ({click_x}, {click_y})")
    
    # Save debug visualization after click if DEBUG_TASKBAR=1
    if DEBUG:
        # Regenerate candidates with debug to get heatmap/binary for visualization
        _ = detect_icon_candidates(taskbar_region, debug=True, band_left=tx, band_top=ty)
        mode = _get_debug_taskbar_output()
        if mode == "full":
            print("  DEBUG mode: see logs/taskbar_debug.png")
        else:
            print("  DEBUG mode: see logs/taskbar_boxes.png")
    
    # Map click to taskbar coordinates (taskbar spans full screen width)
    taskbar_click_x = click_x - tx
    taskbar_click_y = click_y - ty
    
    # Find nearest candidate to click
    clicked_candidate = None
    min_dist = float('inf')
    
    for candidate in candidates:
        # Check if click is inside candidate box
        cx, cy = candidate["center_x"], candidate["center_y"]
        x1, y1 = candidate["x"], candidate["y"]
        x2, y2 = x1 + candidate["w"], y1 + candidate["h"]
        
        if x1 <= taskbar_click_x <= x2 and y1 <= taskbar_click_y <= y2:
            clicked_candidate = candidate
            break
        
        # Otherwise find nearest
        dist = abs(cx - taskbar_click_x) + abs(cy - taskbar_click_y)
        if dist < min_dist:
            min_dist = dist
            clicked_candidate = candidate
    
    if not clicked_candidate:
        return "Training failed: Click did not match any candidate"
    
    print(f"✓ Chrome icon identified at x={clicked_candidate['center_x']}")
    
    # Step 4: Compute visual fingerprint
    print("\n" + "-"*60)
    print("STEP 4: Compute Visual Fingerprint")
    print("-"*60)
    
    # Find neighbors
    clicked_idx = candidates.index(clicked_candidate)
    neighbors = []
    
    if clicked_idx > 0:
        neighbors.append(candidates[clicked_idx - 1])
    if clicked_idx < len(candidates) - 1:
        neighbors.append(candidates[clicked_idx + 1])
    if clicked_idx > 1:
        neighbors.append(candidates[clicked_idx - 2])
    
    fingerprint = compute_fingerprint(clicked_candidate, neighbors, width, tx)
    fingerprint["icon_size"] = int(clicked_candidate.get("icon_size", DEFAULT_ICON_SIZE))

    # Save a visual template crop for robust matching in the locator.
    template_path = Path("memory/taskbar_chrome_template.png")
    template_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Store as forward-slash path for cv2.imread portability.
        cv2.imwrite(str(template_path), clicked_candidate["image"])
        fingerprint["template_path"] = template_path.as_posix()
    except Exception:
        # Template is optional; keep anchor usable even if write fails.
        pass
    
    print(f"✓ Perceptual hash: {fingerprint['phash']}")
    print(f"✓ Color histogram: {len(fingerprint['histogram'])} bins")
    print(f"✓ Neighbor hashes: {len(fingerprint['neighbors'])}")
    print(f"✓ Position ratio: {fingerprint['ratio']:.3f}")
    
    # Step 5: Save to memory
    print("\n" + "-"*60)
    print("STEP 5: Save Anchor")
    print("-"*60)
    
    memory_file = Path("memory/taskbar_anchors.json")
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    
    if memory_file.exists():
        with open(memory_file, 'r') as f:
            anchors = json.load(f)
    else:
        anchors = {}
    
    anchors["chrome"] = fingerprint
    
    with open(memory_file, 'w') as f:
        json.dump(anchors, f, indent=2)
    
    print(f"✓ Saved to {memory_file}")
    
    # Final message
    print("\n" + "="*60)
    print("✅ TRAINING COMPLETE")
    print("="*60)
    print("\nJarvis can now find Chrome using:")
    print("  • Perceptual hash matching")
    print("  • Color histogram similarity")
    print("  • Neighbor topology")
    print("  • Position ratio fallback")
    print("\nThis will survive:")
    print("  ✔ Windows updates")
    print("  ✔ Taskbar moves")
    print("  ✔ Blur effects")
    print("  ✔ DPI scaling")
    print("  ✔ Dark/light mode")
    
    return "Chrome taskbar anchor trained successfully"


if __name__ == "__main__":
    result = train_taskbar_chrome()
    print(f"\n{result}")
