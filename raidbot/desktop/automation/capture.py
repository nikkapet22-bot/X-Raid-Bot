from __future__ import annotations

from typing import Any, Callable

import numpy as np


Bounds = tuple[int, int, int, int]


class WindowCapture:
    def __init__(self, *, sct_factory: Callable[[], Any] | None = None) -> None:
        self._sct_factory = sct_factory or self._default_sct_factory

    def capture(self, bounds: Bounds) -> np.ndarray:
        left, top, right, bottom = bounds
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid capture bounds: {bounds}")
        monitor = {
            "left": int(left),
            "top": int(top),
            "width": int(width),
            "height": int(height),
        }
        with self._sct_factory() as sct:
            return np.array(sct.grab(monitor))

    def _default_sct_factory(self):
        import mss

        return mss.mss()
