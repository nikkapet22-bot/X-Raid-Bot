from __future__ import annotations

import cv2
import numpy as np

from .models import MatchResult


class TemplateMatcher:
    def find_best_match(
        self,
        frame: np.ndarray,
        template: np.ndarray,
        threshold: float,
    ) -> MatchResult | None:
        if threshold < -1.0 or threshold > 1.0:
            raise ValueError(f"threshold must be between -1.0 and 1.0, got {threshold}")
        frame_gray = self._ensure_grayscale(frame)
        template_gray = self._ensure_grayscale(template)
        self._validate_dimensions(frame_gray, template_gray)
        result = cv2.matchTemplate(frame_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_score, _, max_location = cv2.minMaxLoc(result)
        if max_score < threshold:
            return None
        return MatchResult(
            score=float(max_score),
            top_left_x=int(max_location[0]),
            top_left_y=int(max_location[1]),
            width=int(template_gray.shape[1]),
            height=int(template_gray.shape[0]),
        )

    def _ensure_grayscale(self, image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image
        if image.ndim == 3 and image.shape[2] == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if image.ndim == 3 and image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        raise ValueError(f"Unsupported image shape for template matching: {image.shape}")

    def _validate_dimensions(self, frame: np.ndarray, template: np.ndarray) -> None:
        if frame.size == 0 or template.size == 0:
            raise ValueError("Frame and template must be non-empty")
        if template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
            raise ValueError("Template dimensions exceed frame dimensions")
