"""Representative keyframe scoring for a board version."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from course_video_analyzer.models import BoardRegion


@dataclass(frozen=True)
class KeyframeScoringConfig:
    """Weights and normalization for representative-frame selection."""

    weight_sharpness: float = 0.55
    weight_occlusion: float = 0.35
    weight_glare: float = 0.10
    # Laplacian variance at or above this maps to sharpness 1.0.
    sharpness_full_at: float = 250.0
    # Skin-tone coverage treated as fully occluded for scoring.
    occlusion_full_at: float = 0.45
    # Near-white pixel fraction treated as fully glared.
    glare_full_at: float = 0.25
    glare_min_value: int = 245


@dataclass(frozen=True)
class KeyframeScore:
    """Decomposed score for one board crop candidate."""

    total: float
    sharpness: float
    occlusion_ratio: float
    glare_ratio: float
    components: dict[str, float]


class KeyframeScorer:
    """Prefer sharp, low-occlusion, low-glare crops as version representatives.

    Formula (weights renormalized to sum 1):

        score = w_s * sharp_n + w_o * (1 - occ_n) + w_g * (1 - glare_n)

    where
        sharp_n  = clip(laplacian_var / sharpness_full_at, 0, 1)
        occ_n    = clip(skin_ratio / occlusion_full_at, 0, 1)
        glare_n  = clip(near_white_ratio / glare_full_at, 0, 1)
    """

    def __init__(self, config: KeyframeScoringConfig | None = None) -> None:
        self.config = config or KeyframeScoringConfig()

    def score_crop(self, crop_bgr: np.ndarray) -> KeyframeScore:
        cfg = self.config
        sharpness_raw = laplacian_variance(crop_bgr)
        occlusion = skin_occlusion_ratio(crop_bgr)
        glare = glare_ratio(crop_bgr, min_value=cfg.glare_min_value)

        sharp_n = float(np.clip(sharpness_raw / max(cfg.sharpness_full_at, 1e-6), 0.0, 1.0))
        occ_n = float(np.clip(occlusion / max(cfg.occlusion_full_at, 1e-6), 0.0, 1.0))
        glare_n = float(np.clip(glare / max(cfg.glare_full_at, 1e-6), 0.0, 1.0))

        w_sum = cfg.weight_sharpness + cfg.weight_occlusion + cfg.weight_glare
        w_s = cfg.weight_sharpness / max(w_sum, 1e-6)
        w_o = cfg.weight_occlusion / max(w_sum, 1e-6)
        w_g = cfg.weight_glare / max(w_sum, 1e-6)

        total = float(np.clip(w_s * sharp_n + w_o * (1.0 - occ_n) + w_g * (1.0 - glare_n), 0.0, 1.0))
        return KeyframeScore(
            total=total,
            sharpness=sharpness_raw,
            occlusion_ratio=occlusion,
            glare_ratio=glare,
            components={
                "sharpness_norm": sharp_n,
                "occlusion_norm": occ_n,
                "glare_norm": glare_n,
                "weight_sharpness": w_s,
                "weight_occlusion": w_o,
                "weight_glare": w_g,
            },
        )

    def score_region(self, image_bgr: np.ndarray, region: BoardRegion) -> KeyframeScore:
        x1, y1, x2, y2 = region.as_xyxy()
        h, w = image_bgr.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return KeyframeScore(
                total=0.0,
                sharpness=0.0,
                occlusion_ratio=1.0,
                glare_ratio=1.0,
                components={},
            )
        return self.score_crop(image_bgr[y1:y2, x1:x2])

    def pick_best(
        self,
        crops_bgr: list[np.ndarray],
    ) -> tuple[int, KeyframeScore]:
        """Return index and score of the best crop. Empty input → (-1, zero score)."""
        if not crops_bgr:
            return -1, KeyframeScore(0.0, 0.0, 1.0, 1.0, {})
        best_idx = 0
        best_score = self.score_crop(crops_bgr[0])
        for idx in range(1, len(crops_bgr)):
            score = self.score_crop(crops_bgr[idx])
            if score.total > best_score.total:
                best_idx = idx
                best_score = score
        return best_idx, best_score


def laplacian_variance(image_bgr: np.ndarray) -> float:
    """Focus / sharpness proxy via Laplacian variance."""
    if image_bgr.size == 0:
        return 0.0
    gray = image_bgr if image_bgr.ndim == 2 else cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def skin_occlusion_ratio(image_bgr: np.ndarray) -> float:
    """Cheap person-occlusion proxy using YCrCb skin range."""
    if image_bgr.size == 0:
        return 0.0
    if image_bgr.ndim == 2:
        image_bgr = cv2.cvtColor(image_bgr, cv2.COLOR_GRAY2BGR)
    ycrcb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2YCrCb)
    skin = cv2.inRange(
        ycrcb,
        np.array([0, 133, 77], dtype=np.uint8),
        np.array([255, 173, 127], dtype=np.uint8),
    )
    return float(np.mean(skin > 0))


def glare_ratio(image_bgr: np.ndarray, *, min_value: int = 245) -> float:
    """Fraction of near-white pixels (specular / overexposure proxy)."""
    if image_bgr.size == 0:
        return 0.0
    gray = image_bgr if image_bgr.ndim == 2 else cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray >= min_value))
