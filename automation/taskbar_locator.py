"""Human-style visual taskbar locator.

Finds Chrome icon using confidence-based matching:
- Perceptual hash similarity
- Color histogram comparison
- Neighbor topology matching
- Position ratio fallback

HARD FAIL: Confidence must be > 0.82 or abort.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import cv2
import numpy as np
from PIL import ImageGrab

from automation.taskbar_trainer import (
    DEFAULT_ICON_SIZE,
    _get_taskbar_rect,
    locate_taskbar,
    detect_icon_candidates,
    perceptual_hash,
    color_histogram,
    save_taskbar_boxes,
)


# Confidence threshold - HARD FAIL if below this
CONFIDENCE_THRESHOLD = 0.82

RATIO_TOL_FRAC = 0.15


def hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two hex hash strings."""
    try:
        xor = int(hash1, 16) ^ int(hash2, 16)
        return bin(xor).count('1')
    except (ValueError, TypeError):
        return 64  # Max distance for 64-bit hash


def hash_similarity(hash1: str, hash2: str) -> float:
    """Compute similarity score from hash distance (0.0 to 1.0)."""
    distance = hamming_distance(hash1, hash2)
    # 64-bit hash, so max distance is 64
    return 1.0 - (distance / 64.0)


def histogram_similarity(hist1: List[float], hist2: List[float]) -> float:
    """Compute histogram similarity using correlation."""
    if not hist1 or not hist2:
        return 0.0
    
    h1 = np.array(hist1, dtype=np.float32)
    h2 = np.array(hist2, dtype=np.float32)
    
    # Ensure same length
    min_len = min(len(h1), len(h2))
    h1 = h1[:min_len]
    h2 = h2[:min_len]
    
    # Correlation coefficient
    corr = cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)
    
    # Normalize to 0-1
    return max(0.0, (corr + 1.0) / 2.0)


def _template_similarity(candidate_bgr: np.ndarray, template_bgr: np.ndarray) -> float:
    """Edge-normalized template correlation in [0, 1]."""
    if candidate_bgr.size == 0 or template_bgr.size == 0:
        return 0.0

    cand = candidate_bgr
    templ = template_bgr

    # Resize candidate to template size for stable correlation.
    if cand.shape[:2] != templ.shape[:2]:
        cand = cv2.resize(cand, (templ.shape[1], templ.shape[0]), interpolation=cv2.INTER_AREA)

    cand_g = cv2.cvtColor(cand, cv2.COLOR_BGR2GRAY)
    templ_g = cv2.cvtColor(templ, cv2.COLOR_BGR2GRAY)

    cand_e = cv2.Canny(cand_g, 60, 180)
    templ_e = cv2.Canny(templ_g, 60, 180)

    # matchTemplate returns a 1x1 result when images are same size.
    res = cv2.matchTemplate(cand_e, templ_e, cv2.TM_CCOEFF_NORMED)
    v = float(res[0][0]) if res.size else 0.0
    if np.isnan(v) or np.isinf(v):
        return 0.0
    # TM_CCOEFF_NORMED is [-1, 1]
    return max(0.0, min(1.0, (v + 1.0) / 2.0))


def _load_template(template_path: str | None) -> Optional[np.ndarray]:
    if not template_path:
        return None
    try:
        img = cv2.imread(template_path, cv2.IMREAD_COLOR)
        return img if img is not None and img.size else None
    except Exception:
        return None


def _score_candidate(
    *,
    candidate: Dict,
    anchor: Dict,
    candidates: List[Dict],
    candidate_idx: int,
    screen_width: int,
    taskbar_left: int,
    template_bgr: Optional[np.ndarray],
) -> dict:
    """Return component scores and total."""
    anchor_phash = anchor.get("phash", "")
    anchor_hist = anchor.get("histogram", [])
    anchor_neighbors = anchor.get("neighbors", [])
    anchor_ratio = float(anchor.get("ratio", 0.5))

    candidate_phash = perceptual_hash(candidate["image"])
    phash_sim = hash_similarity(candidate_phash, anchor_phash) if anchor_phash else 0.0

    candidate_hist = color_histogram(candidate["image"])
    hist_sim = histogram_similarity(candidate_hist, anchor_hist) if anchor_hist else 0.0

    neighbor_sim = 0.0
    if anchor_neighbors and len(candidates) > 1:
        neighbor_scores: list[float] = []
        neighbor_indices = []
        if candidate_idx > 0:
            neighbor_indices.append(candidate_idx - 1)
        if candidate_idx < len(candidates) - 1:
            neighbor_indices.append(candidate_idx + 1)
        if candidate_idx > 1:
            neighbor_indices.append(candidate_idx - 2)
        for i, ni in enumerate(neighbor_indices):
            if i < len(anchor_neighbors):
                neighbor_phash = perceptual_hash(candidates[ni]["image"])
                neighbor_scores.append(hash_similarity(neighbor_phash, anchor_neighbors[i]))
        if neighbor_scores:
            neighbor_sim = float(sum(neighbor_scores) / len(neighbor_scores))

    candidate_ratio = (
        (taskbar_left + int(candidate["center_x"])) / screen_width if screen_width > 0 else 0.5
    )
    ratio_diff = abs(anchor_ratio - float(candidate_ratio))
    ratio_sim = max(0.0, 1.0 - ratio_diff * 5.0)

    templ_sim = 0.0
    if template_bgr is not None:
        templ_sim = _template_similarity(candidate["image"], template_bgr)

    # Weights: prefer template when present.
    if template_bgr is not None:
        weights = {"phash": 0.25, "hist": 0.15, "templ": 0.35, "neighbor": 0.15, "ratio": 0.10}
    else:
        weights = {"phash": 0.35, "hist": 0.25, "templ": 0.0, "neighbor": 0.25, "ratio": 0.15}

    total = (
        phash_sim * weights["phash"]
        + hist_sim * weights["hist"]
        + templ_sim * weights["templ"]
        + neighbor_sim * weights["neighbor"]
        + ratio_sim * weights["ratio"]
    )

    return {
        "total": float(total),
        "phash": float(phash_sim),
        "histogram": float(hist_sim),
        "template": float(templ_sim),
        "neighbors": float(neighbor_sim),
        "ratio": float(ratio_sim),
        "candidate_ratio": float(candidate_ratio),
    }


def _write_locator_scores(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        return


def compute_candidate_confidence(
    candidate: Dict,
    anchor: Dict,
    candidates: List[Dict],
    candidate_idx: int,
    screen_width: int,
    taskbar_left: int
) -> float:
    """Compute confidence score for a candidate matching the anchor.
    
    Returns:
        Confidence score 0.0 to 1.0
    """
    scores = []
    weights = []
    
    # 1. Perceptual hash similarity (weight: 0.4)
    candidate_phash = perceptual_hash(candidate["image"])
    anchor_phash = anchor.get("phash", "")
    
    if anchor_phash:
        phash_sim = hash_similarity(candidate_phash, anchor_phash)
        scores.append(phash_sim)
        weights.append(0.4)
    
    # 2. Color histogram similarity (weight: 0.3)
    candidate_hist = color_histogram(candidate["image"])
    anchor_hist = anchor.get("histogram", [])
    
    if anchor_hist:
        hist_sim = histogram_similarity(candidate_hist, anchor_hist)
        scores.append(hist_sim)
        weights.append(0.3)
    
    # 3. Neighbor topology matching (weight: 0.2)
    anchor_neighbors = anchor.get("neighbors", [])
    
    if anchor_neighbors and len(candidates) > 1:
        neighbor_scores = []
        
        # Check neighbors
        neighbor_indices = []
        if candidate_idx > 0:
            neighbor_indices.append(candidate_idx - 1)
        if candidate_idx < len(candidates) - 1:
            neighbor_indices.append(candidate_idx + 1)
        if candidate_idx > 1:
            neighbor_indices.append(candidate_idx - 2)
        
        for i, ni in enumerate(neighbor_indices):
            if i < len(anchor_neighbors):
                neighbor_phash = perceptual_hash(candidates[ni]["image"])
                neighbor_sim = hash_similarity(neighbor_phash, anchor_neighbors[i])
                neighbor_scores.append(neighbor_sim)
        
        if neighbor_scores:
            scores.append(sum(neighbor_scores) / len(neighbor_scores))
            weights.append(0.2)
    
    # 4. Position ratio similarity (weight: 0.1)
    anchor_ratio = anchor.get("ratio", 0.5)
    candidate_ratio = (
        (taskbar_left + candidate["center_x"]) / screen_width if screen_width > 0 else 0.5
    )
    
    ratio_diff = abs(anchor_ratio - candidate_ratio)
    ratio_sim = max(0.0, 1.0 - ratio_diff * 5)  # 0.2 diff = 0.0 similarity
    scores.append(ratio_sim)
    weights.append(0.1)
    
    # Weighted average
    if not scores:
        return 0.0
    
    total_weight = sum(weights)
    weighted_sum = sum(s * w for s, w in zip(scores, weights))
    
    return weighted_sum / total_weight


def locate_chrome() -> Tuple[Optional[Tuple[int, int]], float]:
    """Locate Chrome icon using confidence-based matching.
    
    Returns:
        ((x, y), confidence) or (None, 0.0) if not found
    """
    DEBUG = os.environ.get("DEBUG_TASKBAR", "0") == "1"
    debug_mode = (os.environ.get("DEBUG_TASKBAR_OUTPUT") or "taskbar").strip().lower()
    
    # Load anchor
    memory_file = Path("memory/taskbar_anchors.json")
    
    if not memory_file.exists():
        raise RuntimeError(
            "Chrome taskbar anchor not trained. Run: train taskbar_chrome"
        )
    
    with open(memory_file, 'r') as f:
        anchors = json.load(f)
    
    if "chrome" not in anchors:
        raise RuntimeError(
            "Chrome anchor not found in memory. Run: train taskbar_chrome"
        )
    
    chrome_anchor = anchors["chrome"]
    template_bgr = _load_template(chrome_anchor.get("template_path"))
    anchor_icon_size = int(chrome_anchor.get("icon_size") or DEFAULT_ICON_SIZE)
    
    # Capture screen
    _get_taskbar_rect()
    try:
        screenshot = np.array(ImageGrab.grab(all_screens=True))
    except TypeError:
        screenshot = np.array(ImageGrab.grab())
    screenshot_bgr = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
    height, width = screenshot_bgr.shape[:2]
    
    # Locate taskbar
    taskbar_region, tx, ty, tb = locate_taskbar(screenshot_bgr)
    th = tb - ty
    
    # Detect icon candidates
    internal_debug = bool(DEBUG and debug_mode == "full")
    candidates = detect_icon_candidates(taskbar_region, debug=internal_debug, band_left=tx, band_top=ty)
    
    if not candidates:
        if DEBUG and debug_mode in ("taskbar", "full"):
            save_taskbar_boxes(taskbar_region, [], out_path=str(Path("logs") / "taskbar_boxes.png"))
        return (None, 0.0)

    # Ratio window filter to reduce false positives.
    anchor_ratio = float(chrome_anchor.get("ratio", 0.5))
    expected_taskbar_x = int(anchor_ratio * width - tx)
    tol = max(int(anchor_icon_size * 6), int(width * RATIO_TOL_FRAC))
    filtered = [c for c in candidates if abs(int(c["center_x"]) - expected_taskbar_x) <= tol]
    score_pool = filtered if filtered else candidates
    
    # Score all candidates
    best_candidate = None
    best_confidence = 0.0
    best_idx = -1
    scored_rows: list[dict] = []
    
    for idx, candidate in enumerate(score_pool):
        scores = _score_candidate(
            candidate=candidate,
            anchor=chrome_anchor,
            candidates=score_pool,
            candidate_idx=idx,
            screen_width=width,
            taskbar_left=tx,
            template_bgr=template_bgr,
        )
        confidence = float(scores["total"])

        scored_rows.append(
            {
                "idx": idx,
                "x": int(candidate["x"]),
                "y": int(candidate["y"]),
                "w": int(candidate["w"]),
                "h": int(candidate["h"]),
                "center_x": int(candidate["center_x"]),
                "center_y": int(candidate["center_y"]),
                "confidence": confidence,
                "scores": scores,
            }
        )
        
        if confidence > best_confidence:
            best_confidence = confidence
            best_candidate = candidate
            best_idx = idx
    
    if best_candidate is None:
        return (None, 0.0)
    
    # Convert to screen coordinates (taskbar starts at x=0)
    screen_x = tx + best_candidate["center_x"]
    screen_y = ty + best_candidate["center_y"]

    # Debug artifacts
    if DEBUG:
        should_write = debug_mode in ("taskbar", "full")
        if debug_mode == "fail" and best_confidence < CONFIDENCE_THRESHOLD:
            should_write = True
        if should_write:
            save_taskbar_boxes(
                taskbar_region,
                score_pool,
                best_idx=best_idx,
                expected_x=expected_taskbar_x,
                out_path=str(Path("logs") / "taskbar_boxes.png"),
            )
            _write_locator_scores(
                Path("logs") / "taskbar_locator_scores.json",
                {
                    "screen": {"width": int(width), "height": int(height)},
                    "taskbar": {"left": int(tx), "top": int(ty), "bottom": int(tb), "height": int(th)},
                    "anchor": {
                        "ratio": float(anchor_ratio),
                        "icon_size": int(anchor_icon_size),
                        "template_path": chrome_anchor.get("template_path"),
                    },
                    "ratio_window": {"expected_taskbar_x": int(expected_taskbar_x), "tol": int(tol)},
                    "candidates_total": int(len(candidates)),
                    "candidates_scored": int(len(score_pool)),
                    "best": {"idx": int(best_idx), "confidence": float(best_confidence)},
                    "rows": scored_rows,
                },
            )
    
    return ((screen_x, screen_y), best_confidence)


def find_chrome_icon() -> Optional[Tuple[int, int]]:
    """Find Chrome icon with HARD FAIL rule.
    
    Returns:
        (x, y) screen coordinates or raises RuntimeError if confidence < 0.82
    """
    coords, confidence = locate_chrome()
    
    if coords is None:
        raise RuntimeError(
            "I could not visually locate the Chrome icon. "
            "No icon candidates detected in taskbar. "
            "Please retrain taskbar Chrome."
        )
    
    if confidence < CONFIDENCE_THRESHOLD:
        raise RuntimeError(
            f"I could not visually locate the Chrome icon. "
            f"Confidence {confidence:.2f} is below threshold {CONFIDENCE_THRESHOLD}. "
            f"Please retrain taskbar Chrome."
        )
    
    return coords


def click_chrome_icon() -> bool:
    """Find and click Chrome icon.
    
    Returns:
        True if clicked successfully
        
    Raises:
        RuntimeError: If confidence < 0.82
    """
    import pyautogui
    
    coords = find_chrome_icon()
    
    x, y = coords
    pyautogui.click(x, y)
    
    return True
