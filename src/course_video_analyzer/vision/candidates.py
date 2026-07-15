"""Contour and edge based board candidate generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from course_video_analyzer.models import BoardRegion

BoardMode = Literal["auto", "electronic", "physical"]


@dataclass(frozen=True)
class CandidateGeneratorConfig:
    """Tunable thresholds for rectangular region proposals."""

    min_area_ratio: float = 0.10
    max_area_ratio: float = 0.98
    min_rectangularity: float = 0.55
    min_aspect_ratio: float = 0.45
    max_aspect_ratio: float = 3.2
    canny_low: int = 40
    canny_high: int = 120
    morph_kernel: int = 5
    max_candidates: int = 24
    nms_iou: float = 0.55


@dataclass(frozen=True)
class RawCandidate:
    """Unscored geometric proposal from the current frame."""

    region: BoardRegion
    rectangularity: float
    source: str


def clip_region(x: int, y: int, width: int, height: int, frame_w: int, frame_h: int) -> BoardRegion | None:
    """Clamp a box to the frame and drop degenerate results."""
    x1 = max(0, min(x, frame_w - 1))
    y1 = max(0, min(y, frame_h - 1))
    x2 = max(0, min(x + width, frame_w))
    y2 = max(0, min(y + height, frame_h))
    w = x2 - x1
    h = y2 - y1
    if w <= 1 or h <= 1:
        return None
    return BoardRegion(x=x1, y=y1, width=w, height=h)


def region_iou(a: BoardRegion, b: BoardRegion) -> float:
    """Intersection-over-union for axis-aligned board regions."""
    ax1, ay1, ax2, ay2 = a.as_xyxy()
    bx1, by1, bx2, by2 = b.as_xyxy()
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    union = a.area + b.area - inter
    return float(inter / union) if union > 0 else 0.0


class CandidateGenerator:
    """Generate large rectangular board/slide proposals without fixed layout rules."""

    def __init__(self, config: CandidateGeneratorConfig | None = None) -> None:
        self.config = config or CandidateGeneratorConfig()

    def generate(
        self,
        image_bgr: np.ndarray,
        *,
        mode: BoardMode = "auto",
    ) -> list[RawCandidate]:
        """Return unique axis-aligned candidates from edges, fill, and panel cues."""
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            raise ValueError("image_bgr must be an HxWx3 BGR image")

        frame_h, frame_w = image_bgr.shape[:2]
        frame_area = float(frame_w * frame_h)
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        proposals: list[RawCandidate] = []
        proposals.extend(self._from_edges(blur, frame_w, frame_h, frame_area, source="edges"))
        if mode in ("auto", "electronic"):
            proposals.extend(
                self._from_bright_panels(image_bgr, frame_w, frame_h, frame_area, source="bright_panel")
            )
        if mode in ("auto", "physical"):
            proposals.extend(
                self._from_dark_panels(image_bgr, frame_w, frame_h, frame_area, source="dark_panel")
            )
        proposals.extend(self._from_vertical_splits(blur, frame_w, frame_h, frame_area))

        return self._nms(proposals)

    def _accept(
        self,
        region: BoardRegion,
        contour_area: float,
        frame_area: float,
        source: str,
    ) -> RawCandidate | None:
        area_ratio = region.area / frame_area
        cfg = self.config
        if area_ratio < cfg.min_area_ratio or area_ratio > cfg.max_area_ratio:
            return None
        aspect = region.width / region.height
        if aspect < cfg.min_aspect_ratio or aspect > cfg.max_aspect_ratio:
            return None
        rectangularity = float(np.clip(contour_area / max(region.area, 1), 0.0, 1.0))
        if rectangularity < cfg.min_rectangularity:
            return None
        return RawCandidate(region=region, rectangularity=rectangularity, source=source)

    def _contours_to_candidates(
        self,
        binary: np.ndarray,
        frame_w: int,
        frame_h: int,
        frame_area: float,
        source: str,
    ) -> list[RawCandidate]:
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out: list[RawCandidate] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < frame_area * self.config.min_area_ratio * 0.5:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            region = clip_region(x, y, w, h, frame_w, frame_h)
            if region is None:
                continue
            # Prefer fitted rectangle area when polygon is near-rect.
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
            if 4 <= len(approx) <= 8:
                rect_area = float(cv2.contourArea(approx))
            else:
                rect_area = area
            # Rectangularity vs axis-aligned bbox.
            candidate = self._accept(region, max(rect_area, area * 0.85), frame_area, source)
            if candidate is not None:
                out.append(candidate)

            # Also consider min-area rotated rect projected to AABB.
            (cx, cy), (rw, rh), _angle = cv2.minAreaRect(contour)
            if rw < 1 or rh < 1:
                continue
            aw, ah = abs(rw), abs(rh)
            rx = int(cx - aw / 2)
            ry = int(cy - ah / 2)
            rotated = clip_region(rx, ry, int(aw), int(ah), frame_w, frame_h)
            if rotated is None:
                continue
            fitted = self._accept(rotated, aw * ah, frame_area, f"{source}_minrect")
            if fitted is not None:
                out.append(fitted)
        return out

    def _from_edges(
        self,
        gray: np.ndarray,
        frame_w: int,
        frame_h: int,
        frame_area: float,
        *,
        source: str,
    ) -> list[RawCandidate]:
        cfg = self.config
        edges = cv2.Canny(gray, cfg.canny_low, cfg.canny_high)
        k = max(3, cfg.morph_kernel | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        dilated = cv2.dilate(closed, kernel, iterations=1)
        return self._contours_to_candidates(dilated, frame_w, frame_h, frame_area, source)

    def _from_bright_panels(
        self,
        image_bgr: np.ndarray,
        frame_w: int,
        frame_h: int,
        frame_area: float,
        *,
        source: str,
    ) -> list[RawCandidate]:
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        # Light slides / whiteboards: high value, low saturation.
        mask = cv2.inRange(
            hsv,
            np.array([0, 0, 170], dtype=np.uint8),
            np.array([180, 80, 255], dtype=np.uint8),
        )
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
        return self._contours_to_candidates(mask, frame_w, frame_h, frame_area, source)

    def _from_dark_panels(
        self,
        image_bgr: np.ndarray,
        frame_w: int,
        frame_h: int,
        frame_area: float,
        *,
        source: str,
    ) -> list[RawCandidate]:
        hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
        # Chalkboards / dark UI panels: low value, low-mid saturation.
        mask = cv2.inRange(
            hsv,
            np.array([0, 0, 0], dtype=np.uint8),
            np.array([180, 90, 90], dtype=np.uint8),
        )
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
        return self._contours_to_candidates(mask, frame_w, frame_h, frame_area, source)

    def _from_vertical_splits(
        self,
        gray: np.ndarray,
        frame_w: int,
        frame_h: int,
        frame_area: float,
    ) -> list[RawCandidate]:
        """Propose left/right panels from strong vertical separators (no fixed ratio)."""
        edges = cv2.Canny(gray, self.config.canny_low, self.config.canny_high)
        # Sum edge strength along columns; look for tall separators.
        col_score = edges.mean(axis=0).astype(np.float32)
        col_score = cv2.GaussianBlur(col_score.reshape(1, -1), (0, 0), 5).ravel()
        peak = float(col_score.max())
        median = float(np.median(col_score))
        # Require a clearly stronger separator than the background edge field.
        if peak < max(8.0, median * 3.0):
            return self._fullscreen_if_structured(gray, frame_w, frame_h, frame_area)

        threshold = max(float(np.percentile(col_score, 95)), median * 2.5)
        out: list[RawCandidate] = []
        # Candidate split columns away from extreme borders.
        for x in range(int(frame_w * 0.2), int(frame_w * 0.8)):
            if col_score[x] < threshold:
                continue
            # local peak
            left = col_score[max(0, x - 5) : x]
            right = col_score[x + 1 : min(frame_w, x + 6)]
            if left.size and col_score[x] < left.max():
                continue
            if right.size and col_score[x] < right.max():
                continue

            left_region = clip_region(0, 0, x, frame_h, frame_w, frame_h)
            right_region = clip_region(x, 0, frame_w - x, frame_h, frame_w, frame_h)
            for region, name in ((left_region, "split_left"), (right_region, "split_right")):
                if region is None:
                    continue
                candidate = self._accept(region, float(region.area), frame_area, name)
                if candidate is not None:
                    out.append(candidate)

        out.extend(self._fullscreen_if_structured(gray, frame_w, frame_h, frame_area))
        return out

    def _fullscreen_if_structured(
        self,
        gray: np.ndarray,
        frame_w: int,
        frame_h: int,
        frame_area: float,
    ) -> list[RawCandidate]:
        """Emit a full-frame proposal only when edges suggest slide-like content."""
        edges = cv2.Canny(gray, self.config.canny_low, self.config.canny_high)
        if float(np.mean(edges > 0)) < 0.04:
            return []
        full = BoardRegion(x=0, y=0, width=frame_w, height=frame_h)
        full_candidate = self._accept(full, float(full.area), frame_area, "fullscreen")
        return [full_candidate] if full_candidate is not None else []

    def _nms(self, proposals: list[RawCandidate]) -> list[RawCandidate]:
        if not proposals:
            return []
        # Keep higher rectangularity first, then larger area.
        ordered = sorted(
            proposals,
            key=lambda c: (c.rectangularity, c.region.area),
            reverse=True,
        )
        kept: list[RawCandidate] = []
        for cand in ordered:
            if any(region_iou(cand.region, k.region) >= self.config.nms_iou for k in kept):
                continue
            kept.append(cand)
            if len(kept) >= self.config.max_candidates:
                break
        return kept
