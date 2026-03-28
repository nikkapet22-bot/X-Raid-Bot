from __future__ import annotations

import cv2
import numpy as np
import pytest

from raidbot.desktop.automation.templates import load_template_image


def test_template_loader_raises_for_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="missing"):
        load_template_image(tmp_path / "missing.png")


def test_template_loader_raises_for_unreadable_file(tmp_path) -> None:
    path = tmp_path / "broken.png"
    path.write_bytes(b"not-an-image")

    with pytest.raises(ValueError, match="unreadable"):
        load_template_image(path)


def test_template_loader_reads_grayscale_image(tmp_path) -> None:
    image = np.array(
        [
            [0, 64, 255],
            [32, 128, 192],
            [16, 80, 240],
        ],
        dtype=np.uint8,
    )
    path = tmp_path / "template.png"
    assert cv2.imwrite(str(path), image) is True

    loaded = load_template_image(path)

    assert loaded.shape == image.shape
    assert loaded.dtype == np.uint8
    assert np.array_equal(loaded, image)
