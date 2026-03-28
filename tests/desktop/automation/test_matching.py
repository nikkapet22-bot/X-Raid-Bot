from __future__ import annotations

import numpy as np
import pytest

from raidbot.desktop.automation.matching import TemplateMatcher


def test_matcher_returns_best_match_above_threshold() -> None:
    frame = np.zeros((40, 40), dtype=np.uint8)
    template = np.array(
        [
            [0, 255, 0],
            [255, 64, 255],
            [0, 255, 0],
        ],
        dtype=np.uint8,
    )
    frame[10:13, 20:23] = template

    match = TemplateMatcher().find_best_match(frame, template, threshold=0.8)

    assert match is not None
    assert match.top_left_x == 20
    assert match.top_left_y == 10
    assert match.center_x == 21
    assert match.center_y == 11
    assert match.width == 3
    assert match.height == 3
    assert match.score >= 0.8


def test_matcher_returns_none_when_score_below_threshold() -> None:
    frame = np.zeros((20, 20), dtype=np.uint8)
    template = np.array(
        [
            [0, 255, 0],
            [255, 64, 255],
            [0, 255, 0],
        ],
        dtype=np.uint8,
    )

    assert TemplateMatcher().find_best_match(frame, template, threshold=0.95) is None


def test_matcher_rejects_template_dimensions_exceeding_frame() -> None:
    frame = np.zeros((4, 4), dtype=np.uint8)
    template = np.zeros((5, 5), dtype=np.uint8)

    with pytest.raises(ValueError, match="Template dimensions exceed frame dimensions"):
        TemplateMatcher().find_best_match(frame, template, threshold=0.5)


def test_matcher_rejects_out_of_range_threshold() -> None:
    frame = np.zeros((6, 6), dtype=np.uint8)
    template = np.zeros((3, 3), dtype=np.uint8)

    with pytest.raises(ValueError, match="threshold"):
        TemplateMatcher().find_best_match(frame, template, threshold=1.5)
