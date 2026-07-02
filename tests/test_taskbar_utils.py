from __future__ import annotations

from automation.taskbar_trainer import _estimate_icon_size, _square_bounds, _suppress_icon_row


def test_estimate_icon_size_uses_median_and_clamps() -> None:
    candidates = [
        {"raw_w": 20, "raw_h": 20},
        {"raw_w": 44, "raw_h": 44},
        {"raw_w": 52, "raw_h": 52},
        {"raw_w": 80, "raw_h": 10},  # not icon-like
    ]
    assert _estimate_icon_size(candidates) == 44


def test_square_bounds_clamps() -> None:
    x1, y1, x2, y2 = _square_bounds(cx=2, cy=2, size=44, max_w=100, max_h=50)
    assert x1 == 0
    assert y1 == 0
    assert x2 <= 100
    assert y2 <= 50
    assert x2 > x1
    assert y2 > y1


def test_suppress_icon_row_keeps_higher_score() -> None:
    candidates = [
        {"center_x": 10, "score": 1.0},
        {"center_x": 20, "score": 5.0},
        {"center_x": 100, "score": 2.0},
    ]
    kept = _suppress_icon_row(candidates, min_center_spacing=30)
    assert len(kept) == 2
    assert kept[0]["center_x"] == 20
    assert kept[1]["center_x"] == 100

