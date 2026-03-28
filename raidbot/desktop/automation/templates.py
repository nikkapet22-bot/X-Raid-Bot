from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def load_template_image(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"Template file is missing: {path}")
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"Template file is unreadable: {path}")
    return image
