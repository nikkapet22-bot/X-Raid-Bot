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
        frame_matchable, template_matchable = self._prepare_images_for_matching(frame, template)
        self._validate_dimensions(frame_matchable, template_matchable)
        result = cv2.matchTemplate(frame_matchable, template_matchable, cv2.TM_CCOEFF_NORMED)
        _, max_score, _, max_location = cv2.minMaxLoc(result)
        if max_score < threshold:
            return None
        return MatchResult(
            score=float(max_score),
            top_left_x=int(max_location[0]),
            top_left_y=int(max_location[1]),
            width=int(template_matchable.shape[1]),
            height=int(template_matchable.shape[0]),
        )

    def _prepare_images_for_matching(
        self,
        frame: np.ndarray,
        template: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        normalized_frame = self._normalize_channels(frame)
        normalized_template = self._normalize_channels(template)
        if normalized_frame.ndim == normalized_template.ndim:
            return normalized_frame, normalized_template
        return (
            self._ensure_grayscale(normalized_frame),
            self._ensure_grayscale(normalized_template),
        )

    def _normalize_channels(self, image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image
        if image.ndim == 3 and image.shape[2] == 3:
            return image
        if image.ndim == 3 and image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        raise ValueError(f"Unsupported image shape for template matching: {image.shape}")

    def _ensure_grayscale(self, image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image
        if image.ndim == 3 and image.shape[2] == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        raise ValueError(f"Unsupported image shape for template matching: {image.shape}")

    def _validate_dimensions(self, frame: np.ndarray, template: np.ndarray) -> None:
        if frame.size == 0 or template.size == 0:
            raise ValueError("Frame and template must be non-empty")
        if template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
            raise ValueError("Template dimensions exceed frame dimensions")
