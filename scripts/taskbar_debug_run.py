from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import sys

# Ensure repo root is importable when running as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.taskbar_trainer import DEFAULT_ICON_SIZE, detect_icon_candidates, save_taskbar_boxes
from automation.taskbar_locator import _load_template, _score_candidate, RATIO_TOL_FRAC  # type: ignore


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline taskbar debug runner")
    ap.add_argument("--image", required=True, help="Path to a taskbar region image (e.g. logs/taskbar_detected.png)")
    ap.add_argument("--anchor", default="chrome", help="Anchor key in memory/taskbar_anchors.json (default: chrome)")
    args = ap.parse_args()

    img_path = Path(args.image)
    if not img_path.exists():
        raise SystemExit(f"Image not found: {img_path}")

    bgr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise SystemExit(f"Unable to read image: {img_path}")

    candidates = detect_icon_candidates(bgr, debug=False)

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    memory_file = Path("memory/taskbar_anchors.json")
    if not memory_file.exists() or not args.anchor:
        save_taskbar_boxes(bgr, candidates, out_path=str(logs_dir / "taskbar_boxes.png"))
        return 0

    anchors: dict[str, Any] = json.loads(memory_file.read_text(encoding="utf-8"))
    anchor = anchors.get(args.anchor)
    if not isinstance(anchor, dict):
        save_taskbar_boxes(bgr, candidates, out_path=str(logs_dir / "taskbar_boxes.png"))
        return 0

    template_bgr = _load_template(anchor.get("template_path"))
    anchor_icon_size = int(anchor.get("icon_size") or DEFAULT_ICON_SIZE)
    anchor_ratio = float(anchor.get("ratio", 0.5))

    height, width = bgr.shape[:2]
    expected_x = int(anchor_ratio * width)
    tol = max(int(anchor_icon_size * 6), int(width * RATIO_TOL_FRAC))
    filtered = [c for c in candidates if abs(int(c["center_x"]) - expected_x) <= tol]
    pool = filtered if filtered else candidates

    best_idx = -1
    best_conf = 0.0
    rows: list[dict[str, Any]] = []

    for idx, c in enumerate(pool):
        scores = _score_candidate(
            candidate=c,
            anchor=anchor,
            candidates=pool,
            candidate_idx=idx,
            screen_width=width,
            taskbar_left=0,
            template_bgr=template_bgr,
        )
        conf = float(scores["total"])
        rows.append(
            {
                "idx": idx,
                "x": int(c["x"]),
                "y": int(c["y"]),
                "w": int(c["w"]),
                "h": int(c["h"]),
                "center_x": int(c["center_x"]),
                "center_y": int(c["center_y"]),
                "confidence": conf,
                "scores": scores,
            }
        )
        if conf > best_conf:
            best_conf = conf
            best_idx = idx

    save_taskbar_boxes(
        bgr,
        pool,
        best_idx=best_idx if best_idx >= 0 else None,
        expected_x=expected_x,
        out_path=str(logs_dir / "taskbar_boxes.png"),
    )

    (logs_dir / "taskbar_locator_scores.json").write_text(
        json.dumps(
            {
                "image": str(img_path),
                "screen": {"width": int(width), "height": int(height)},
                "anchor": {
                    "key": args.anchor,
                    "ratio": float(anchor_ratio),
                    "icon_size": int(anchor_icon_size),
                    "template_path": anchor.get("template_path"),
                },
                "ratio_window": {"expected_x": int(expected_x), "tol": int(tol)},
                "candidates_total": int(len(candidates)),
                "candidates_scored": int(len(pool)),
                "best": {"idx": int(best_idx), "confidence": float(best_conf)},
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"wrote {logs_dir / 'taskbar_boxes.png'}")
    print(f"wrote {logs_dir / 'taskbar_locator_scores.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
