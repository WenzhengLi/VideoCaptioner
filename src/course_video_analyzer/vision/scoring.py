"""Configurable scoring for board candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import cv2
import numpy as np

from course_video_analyzer.models import BoardCandidate, BoardRegion
from course_video_analyzer.vision.candidates import RawCandidate, region_iou


class TextDensityEstimator(Protocol):
    """Optional injection point for text-box density (no OCR transcript)."""

    def estimate(self, image_bgr: np.ndarray, region: BoardRegion) -> float:
        """Return a value in [0, 1] approximating content density inside ``region``."""
        ...


@dataclass(frozen=True)
class ScoringWeights:
    """Relative contribution of each score component (should roughly sum to 1)."""

    area: float = 0.30
    rectangularity: float = 0.20
    text_density: float = 0.25
    stability: float = 0.15
    occlusion: float = 0.10


@dataclass(frozen=True)
class ScoringThresholds:
    """Acceptance and soft-preference thresholds."""

    min_score: float = 0.35
    keep_low_confidence: bool = False
    low_confidence_score: float = 0.25
    # Soft peak for preferred board size (person PIP sits below min_area_soft).
    min_area_soft: float = 0.18
    ideal_area_low: float = 0.28
    ideal_area_high: float = 0.82
    edge_density_full: float = 0.12
    # Below this, treat the region as likely empty / non-board clutter.
    min_text_density: float = 0.10
    max_useful_occlusion: float = 0.55


@dataclass
class BoardScorer:
    """Score raw proposals into ``BoardCandidate`` objects."""

    weights: ScoringWeights = field(default_factory=ScoringWeights)
    thresholds: ScoringThresholds = field(default_factory=ScoringThresholds)
    text_density_estimator: TextDensityEstimator | None = None

    def score_all(
        self,
        image_bgr: np.ndarray,
        proposals: list[RawCandidate],
        *,
        previous_region: BoardRegion | None = None,
        frame_index: int | None = None,
        timestamp_ms: int | None = None,
        top_k: int = 3,
    ) -> list[BoardCandidate]:
        """Score, filter, and return descending candidates (Top-K)."""
        frame_h, frame_w = image_bgr.shape[:2]
        frame_area = float(frame_w * frame_h)
        scored: list[BoardCandidate] = []
        for proposal in proposals:
            scored.append(
                self.score_one(
                    image_bgr,
                    proposal,
                    frame_area=frame_area,
                    previous_region=previous_region,
                    frame_index=frame_index,
                    timestamp_ms=timestamp_ms,
                )
            )

        scored.sort(key=lambda c: c.score, reverse=True)
        reliable = [c for c in scored if c.score >= self.thresholds.min_score]
        if reliable:
            return reliable[:top_k]
        if self.thresholds.keep_low_confidence and scored:
            weak = scored[0]
            if weak.score >= self.thresholds.low_confidence_score:
                return [weak]
        return []

    def score_one(
        self,
        image_bgr: np.ndarray,
        proposal: RawCandidate,
        *,
        frame_area: float,
        previous_region: BoardRegion | None = None,
        frame_index: int | None = None,
        timestamp_ms: int | None = None,
    ) -> BoardCandidate:
        region = proposal.region
        area_ratio = float(np.clip(region.area / frame_area, 0.0, 1.0))
        rectangularity = float(np.clip(proposal.rectangularity, 0.0, 1.0))
        text_density = self._text_density(image_bgr, region)
        stability = self._stability(region, previous_region)
        occlusion_ratio = self._occlusion_ratio(image_bgr, region)

        area_s = self._area_score(area_ratio)
        rect_s = rectangularity
        text_s = text_density
        stab_s = stability
        occ_s = 1.0 - float(np.clip(occlusion_ratio / self.thresholds.max_useful_occlusion, 0.0, 1.0))

        w = self.weights
        weight_sum = w.area + w.rectangularity + w.text_density + w.stability + w.occlusion
        raw = (
            w.area * area_s
            + w.rectangularity * rect_s
            + w.text_density * text_s
            + w.stability * stab_s
            + w.occlusion * occ_s
        ) / max(weight_sum, 1e-6)
        # Down-weight tiny person windows even if other cues look ok.
        if area_ratio < self.thresholds.min_area_soft:
            raw *= 0.45 + 0.55 * (area_ratio / max(self.thresholds.min_area_soft, 1e-6))
        # Sparse regions (noise / gradients without writing) stay below min_score.
        min_td = self.thresholds.min_text_density
        if text_density < min_td and stability < 0.65:
            raw *= 0.35 * (text_density / max(min_td, 1e-6))

        score = float(np.clip(raw, 0.0, 1.0))
        return BoardCandidate(
            region=region,
            score=score,
            area_ratio=area_ratio,
            rectangularity=rectangularity,
            text_density=text_density,
            stability=stability,
            occlusion_ratio=occlusion_ratio,
            frame_index=frame_index,
            timestamp_ms=timestamp_ms,
            debug={
                "source": proposal.source,
                "components": {
                    "area": area_s,
                    "rectangularity": rect_s,
                    "text_density": text_s,
                    "stability": stab_s,
                    "occlusion": occ_s,
                },
                "weights": {
                    "area": w.area,
                    "rectangularity": w.rectangularity,
                    "text_density": w.text_density,
                    "stability": w.stability,
                    "occlusion": w.occlusion,
                },
            },
        )

    def _text_density(self, image_bgr: np.ndarray, region: BoardRegion) -> float:
        if self.text_density_estimator is not None:
            value = float(self.text_density_estimator.estimate(image_bgr, region))
            return float(np.clip(value, 0.0, 1.0))
        return edge_density(image_bgr, region, full_at=self.thresholds.edge_density_full)

    def _stability(self, region: BoardRegion, previous: BoardRegion | None) -> float:
        if previous is None:
            # Neutral prior when there is no temporal cue.
            return 0.5
        return float(np.clip(region_iou(region, previous), 0.0, 1.0))

    def _area_score(self, area_ratio: float) -> float:
        thr = self.thresholds
        if area_ratio <= 0:
            return 0.0
        if area_ratio < thr.min_area_soft:
            return 0.15 * (area_ratio / thr.min_area_soft)
        if area_ratio < thr.ideal_area_low:
            t = (area_ratio - thr.min_area_soft) / max(thr.ideal_area_low - thr.min_area_soft, 1e-6)
            return 0.15 + 0.55 * t
        if area_ratio <= thr.ideal_area_high:
            return 0.95
        # Nearly full-frame slides remain strong.
        if area_ratio <= 0.98:
            return 0.88
        return 0.75

    def _occlusion_ratio(self, image_bgr: np.ndarray, region: BoardRegion) -> float:
        """Skin-tone / warm blob coverage as a cheap person-occlusion proxy."""
        x1, y1, x2, y2 = region.as_xyxy()
        roi = image_bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return 0.0
        ycrcb = cv2.cvtColor(roi, cv2.COLOR_BGR2YCrCb)
        # Classic loose skin range in YCrCb.
        skin = cv2.inRange(
            ycrcb,
            np.array([0, 133, 77], dtype=np.uint8),
            np.array([255, 173, 127], dtype=np.uint8),
        )
        return float(np.mean(skin > 0))


def edge_density(
    image_bgr: np.ndarray,
    region: BoardRegion,
    *,
    full_at: float = 0.12,
    canny_low: int = 50,
    canny_high: int = 150,
) -> float:
    """Edge-pixel fraction inside ``region``, scaled so ``full_at`` maps to 1.0."""
    x1, y1, x2, y2 = region.as_xyxy()
    roi = image_bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, canny_low, canny_high)
    density = float(np.mean(edges > 0))
    return float(np.clip(density / max(full_at, 1e-6), 0.0, 1.0))
