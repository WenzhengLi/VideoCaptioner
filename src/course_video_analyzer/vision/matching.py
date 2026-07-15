"""ORB feature matching and board content relocation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from course_video_analyzer.models import BoardRegion
from course_video_analyzer.vision.candidates import clip_region


@dataclass(frozen=True)
class MatchingConfig:
    """Central thresholds for ORB extraction and matching."""

    n_features: int = 800
    scale_factor: float = 1.2
    n_levels: int = 8
    # Lowe ratio test.
    ratio_test: float = 0.75
    # Minimum good matches to consider a track / relocation reliable.
    min_good_matches: int = 12
    min_inlier_ratio: float = 0.30
    # Homography RANSAC.
    ransac_reproj_threshold: float = 5.0
    # Match score = good_matches / max(ref_kp, 1), capped to 1.
    min_relocate_score: float = 0.08
    # Template resize for stable ORB density across board sizes.
    template_max_side: int = 480


@dataclass(frozen=True)
class MatchResult:
    """Outcome of matching a reference crop against a target image/ROI."""

    good_matches: int
    inliers: int
    score: float
    inlier_ratio: float
    transformed_region: BoardRegion | None = None


class OrbFeatureMatcher:
    """ORB matcher used for frame-to-frame tracking and cross-layout relocate."""

    def __init__(self, config: MatchingConfig | None = None) -> None:
        self.config = config or MatchingConfig()
        # cv2 stubs often omit ORB_create; getattr keeps runtime + pyright happy.
        orb_factory = getattr(cv2, "ORB_create")
        self._orb = orb_factory(
            nfeatures=self.config.n_features,
            scaleFactor=self.config.scale_factor,
            nlevels=self.config.n_levels,
        )
        self._bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    def extract(self, image_bgr: np.ndarray) -> tuple[list[Any], np.ndarray | None]:
        """Extract ORB keypoints/descriptors from a BGR image."""
        if image_bgr.size == 0:
            return [], None
        gray = _to_gray(image_bgr)
        gray = self._maybe_resize(gray)
        keypoints, descriptors = self._orb.detectAndCompute(gray, None)
        if keypoints is None or descriptors is None or len(keypoints) == 0:
            return [], None
        return list(keypoints), descriptors

    def match_descriptors(
        self,
        desc_ref: np.ndarray | None,
        desc_tgt: np.ndarray | None,
    ) -> list[cv2.DMatch]:
        """Return good matches after Lowe ratio test."""
        if desc_ref is None or desc_tgt is None:
            return []
        if len(desc_ref) < 2 or len(desc_tgt) < 2:
            return []
        knn = self._bf.knnMatch(desc_ref, desc_tgt, k=2)
        good: list[cv2.DMatch] = []
        for pair in knn:
            if len(pair) < 2:
                continue
            m, n = pair
            if m.distance < self.config.ratio_test * n.distance:
                good.append(m)
        return good

    def match_images(
        self,
        reference_bgr: np.ndarray,
        target_bgr: np.ndarray,
        *,
        previous_region: BoardRegion | None = None,
        estimate_transform: bool = False,
    ) -> MatchResult:
        """Match two BGR images; optionally warp ``previous_region`` into target."""
        kp_ref, desc_ref = self.extract(reference_bgr)
        kp_tgt, desc_tgt = self.extract(target_bgr)
        good = self.match_descriptors(desc_ref, desc_tgt)
        score = float(len(good) / max(len(kp_ref), 1))
        score = float(np.clip(score, 0.0, 1.0))

        if not estimate_transform or previous_region is None or len(good) < 4:
            return MatchResult(
                good_matches=len(good),
                inliers=0,
                score=score,
                inlier_ratio=0.0,
                transformed_region=None,
            )

        src_pts = np.asarray(
            [kp_ref[m.queryIdx].pt for m in good],
            dtype=np.float32,
        ).reshape(-1, 1, 2)
        dst_pts = np.asarray(
            [kp_tgt[m.trainIdx].pt for m in good],
            dtype=np.float32,
        ).reshape(-1, 1, 2)
        # Account for optional template resize on both sides independently.
        src_scale = _scale_for_side(reference_bgr.shape, self.config.template_max_side)
        dst_scale = _scale_for_side(target_bgr.shape, self.config.template_max_side)
        src_pts = src_pts / max(src_scale, 1e-6)
        dst_pts = dst_pts / max(dst_scale, 1e-6)

        matrix, mask = cv2.findHomography(
            src_pts,
            dst_pts,
            cv2.RANSAC,
            self.config.ransac_reproj_threshold,
        )
        if matrix is None or mask is None:
            return MatchResult(
                good_matches=len(good),
                inliers=0,
                score=score,
                inlier_ratio=0.0,
                transformed_region=None,
            )

        inliers = int(mask.ravel().sum())
        inlier_ratio = float(inliers / max(len(good), 1))
        x1, y1, x2, y2 = previous_region.as_xyxy()
        corners = np.asarray(
            [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
            dtype=np.float32,
        ).reshape(-1, 1, 2)
        # Homography is between crop-local coords when reference is a crop.
        # Callers that pass crops should convert region; for full-frame refs, apply directly.
        warped = cv2.perspectiveTransform(corners, matrix)
        xs = warped[:, 0, 0]
        ys = warped[:, 0, 1]
        rx = int(np.floor(xs.min()))
        ry = int(np.floor(ys.min()))
        rw = int(np.ceil(xs.max()) - rx)
        rh = int(np.ceil(ys.max()) - ry)
        frame_h, frame_w = target_bgr.shape[:2]
        region = clip_region(rx, ry, rw, rh, frame_w, frame_h)
        return MatchResult(
            good_matches=len(good),
            inliers=inliers,
            score=score,
            inlier_ratio=inlier_ratio,
            transformed_region=region,
        )

    def content_similarity(
        self,
        reference_bgr: np.ndarray,
        candidate_bgr: np.ndarray,
    ) -> float:
        """Scalar similarity in [0, 1] used to pick the best redetect candidate."""
        result = self.match_images(reference_bgr, candidate_bgr, estimate_transform=False)
        return result.score

    def track_region(
        self,
        previous_crop_bgr: np.ndarray,
        previous_region: BoardRegion,
        current_bgr: np.ndarray,
    ) -> MatchResult:
        """Track board by matching previous crop ORB features into the full current frame."""
        kp_ref, desc_ref = self.extract(previous_crop_bgr)
        kp_tgt, desc_tgt = self.extract(current_bgr)
        good = self.match_descriptors(desc_ref, desc_tgt)
        score = float(np.clip(len(good) / max(len(kp_ref), 1), 0.0, 1.0))

        cfg = self.config
        if len(good) < cfg.min_good_matches or desc_ref is None:
            return MatchResult(
                good_matches=len(good),
                inliers=0,
                score=score,
                inlier_ratio=0.0,
                transformed_region=None,
            )

        src_pts = np.asarray(
            [kp_ref[m.queryIdx].pt for m in good],
            dtype=np.float32,
        ).reshape(-1, 1, 2)
        dst_pts = np.asarray(
            [kp_tgt[m.trainIdx].pt for m in good],
            dtype=np.float32,
        ).reshape(-1, 1, 2)
        src_scale = _scale_for_side(previous_crop_bgr.shape, cfg.template_max_side)
        dst_scale = _scale_for_side(current_bgr.shape, cfg.template_max_side)
        src_pts = src_pts / max(src_scale, 1e-6)
        dst_pts = dst_pts / max(dst_scale, 1e-6)

        matrix, mask = cv2.estimateAffinePartial2D(
            src_pts,
            dst_pts,
            method=cv2.RANSAC,
            ransacReprojThreshold=cfg.ransac_reproj_threshold,
        )
        if matrix is None or mask is None:
            return MatchResult(
                good_matches=len(good),
                inliers=0,
                score=score,
                inlier_ratio=0.0,
                transformed_region=None,
            )

        inliers = int(mask.ravel().sum())
        inlier_ratio = float(inliers / max(len(good), 1))
        if inliers < cfg.min_good_matches or inlier_ratio < cfg.min_inlier_ratio:
            return MatchResult(
                good_matches=len(good),
                inliers=inliers,
                score=score,
                inlier_ratio=inlier_ratio,
                transformed_region=None,
            )

        # Map crop-local rectangle → current full frame via affine (2x3).
        w = float(previous_region.width)
        h = float(previous_region.height)
        corners = np.asarray(
            [[0.0, 0.0], [w, 0.0], [w, h], [0.0, h]],
            dtype=np.float32,
        ).reshape(-1, 1, 2)
        warped = cv2.transform(corners, matrix)
        xs = warped[:, 0, 0]
        ys = warped[:, 0, 1]
        rx = int(np.floor(xs.min()))
        ry = int(np.floor(ys.min()))
        rw = int(max(1, np.ceil(xs.max()) - rx))
        rh = int(max(1, np.ceil(ys.max()) - ry))
        frame_h, frame_w = current_bgr.shape[:2]
        region = clip_region(rx, ry, rw, rh, frame_w, frame_h)
        return MatchResult(
            good_matches=len(good),
            inliers=inliers,
            score=score,
            inlier_ratio=inlier_ratio,
            transformed_region=region,
        )

    def _maybe_resize(self, gray: np.ndarray) -> np.ndarray:
        scale = _scale_for_side(gray.shape, self.config.template_max_side)
        if abs(scale - 1.0) < 1e-3:
            return gray
        return cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR,
        )


def crop_region(image_bgr: np.ndarray, region: BoardRegion) -> np.ndarray:
    """Return a copy of the axis-aligned crop for ``region``."""
    x1, y1, x2, y2 = region.as_xyxy()
    h, w = image_bgr.shape[:2]
    x1 = max(0, min(x1, w))
    x2 = max(0, min(x2, w))
    y1 = max(0, min(y1, h))
    y2 = max(0, min(y2, h))
    if x2 <= x1 or y2 <= y1:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    return image_bgr[y1:y2, x1:x2].copy()


def _to_gray(image_bgr: np.ndarray) -> np.ndarray:
    if image_bgr.ndim == 2:
        return image_bgr
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)


def _scale_for_side(shape: tuple[int, ...], max_side: int) -> float:
    h, w = int(shape[0]), int(shape[1])
    longest = max(h, w)
    if longest <= 0 or longest <= max_side:
        return 1.0
    return float(max_side) / float(longest)
