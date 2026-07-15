"""Board region tracking across sampled frames with redetect / lost diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np

from course_video_analyzer.models import BoardCandidate, BoardRegion, BoardSegment
from course_video_analyzer.vision.dedup import BoardPageDeduper, DedupConfig
from course_video_analyzer.vision.detection import BoardDetectorConfig, OpenCvBoardDetector
from course_video_analyzer.vision.keyframes import KeyframeScorer, KeyframeScoringConfig
from course_video_analyzer.vision.matching import MatchingConfig, OrbFeatureMatcher, crop_region

TrackStatus = Literal["tracked", "redetected", "lost"]


@dataclass(frozen=True)
class TrackingConfig:
    """Central thresholds for track / redetect / lost decisions."""

    matching: MatchingConfig = field(default_factory=MatchingConfig)
    dedup: DedupConfig = field(default_factory=DedupConfig)
    keyframe: KeyframeScoringConfig = field(default_factory=KeyframeScoringConfig)
    # Layout jump when tracked box moves too far relative to frame diagonal.
    max_center_shift_ratio: float = 0.28
    max_area_change_ratio: float = 0.55
    # Text/edge density collapse inside predicted box → redetect.
    min_region_edge_density: float = 0.02
    edge_density_drop_ratio: float = 0.35
    # Minimum ORB score to accept a redetected candidate against the last template.
    min_relocate_score: float = 0.06
    # Prefer content match over geometric IoU when relocating.
    relocate_iou_bonus: float = 0.15
    # Detector settings for full-frame redetect.
    detector_min_score: float = 0.30
    detector_top_k: int = 5
    # Half-open segment end extension for the final observation of a version.
    default_frame_duration_ms: int = 1000
    # Max frames of lost before we still keep emitting lost (never drop silently).
    # (Reserved for pipeline policies; every sample always produces an observation.)
    emit_lost_observations: bool = True


@dataclass
class FrameSample:
    """One time-sorted sampled frame for the tracker."""

    frame_index: int
    timestamp_ms: int
    image_bgr: np.ndarray | None = None
    image_path: Path | None = None

    def load_bgr(self) -> np.ndarray:
        if self.image_bgr is not None:
            return self.image_bgr
        if self.image_path is None:
            raise ValueError(f"frame {self.frame_index} has neither image_bgr nor image_path")
        image = cv2.imread(str(self.image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"failed to read frame image: {self.image_path}")
        return image


@dataclass
class TrackObservation:
    """Per-frame tracking diagnostic — every input frame must produce one."""

    frame_index: int
    timestamp_ms: int
    status: TrackStatus
    region: BoardRegion | None
    reason: str
    match_score: float | None = None
    keyframe_score: float | None = None
    occlusion_ratio: float | None = None
    crop_bgr: np.ndarray | None = None
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrackingResult:
    """Stable board versions plus the full observation timeline."""

    observations: list[TrackObservation]
    segments: list[BoardSegment]
    diagnostics: dict[str, Any] = field(default_factory=dict)


class BoardTracker:
    """Track board regions, relocate across layout changes, and emit versions."""

    def __init__(
        self,
        config: TrackingConfig | None = None,
        *,
        detector: OpenCvBoardDetector | None = None,
        matcher: OrbFeatureMatcher | None = None,
        deduper: BoardPageDeduper | None = None,
        keyframe_scorer: KeyframeScorer | None = None,
    ) -> None:
        self.config = config or TrackingConfig()
        self.matcher = matcher or OrbFeatureMatcher(self.config.matching)
        self.deduper = deduper or BoardPageDeduper(self.config.dedup)
        self.keyframe_scorer = keyframe_scorer or KeyframeScorer(self.config.keyframe)
        if detector is not None:
            self.detector = detector
        else:
            self.detector = OpenCvBoardDetector(
                BoardDetectorConfig(
                    mode="auto",
                    top_k=self.config.detector_top_k,
                    min_score=self.config.detector_min_score,
                    keep_low_confidence=False,
                )
            )

    def track(
        self,
        frames: list[FrameSample],
        *,
        output_dir: Path,
        initial_region: BoardRegion | None = None,
    ) -> TrackingResult:
        """Track a sorted frame list. Never silently drops a sample."""
        if not frames:
            return TrackingResult(observations=[], segments=[], diagnostics={"frame_count": 0})

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        redetect_dir = output_dir / "_redetect_frames"
        redetect_dir.mkdir(parents=True, exist_ok=True)

        observations: list[TrackObservation] = []
        previous_region: BoardRegion | None = initial_region
        previous_crop: np.ndarray | None = None
        previous_edge_density: float | None = None
        # After lost, next recovery must go through full-frame redetect (not silent ORB).
        force_redetect = False

        for sample in frames:
            image = sample.load_bgr()
            # Seed crop from initial_region on the first frame so ORB can track afterward.
            if previous_region is not None and previous_crop is None and not force_redetect:
                seeded = crop_region(image, previous_region)
                if seeded.size > 1 and _edge_density(seeded) >= self.config.min_region_edge_density:
                    previous_crop = seeded
                    previous_edge_density = _edge_density(seeded)

            obs = self._process_frame(
                sample,
                image,
                previous_region=previous_region,
                previous_crop=previous_crop,
                previous_edge_density=previous_edge_density,
                redetect_dir=redetect_dir,
                force_redetect=force_redetect,
            )
            observations.append(obs)
            if obs.region is not None and obs.crop_bgr is not None and obs.status != "lost":
                previous_region = obs.region
                previous_crop = obs.crop_bgr
                previous_edge_density = _edge_density(obs.crop_bgr)
                force_redetect = False
            elif obs.status == "lost":
                # Keep last good template for later recovery; force redetect next time.
                force_redetect = True

        segments = self._build_versions(observations, output_dir=output_dir)
        diagnostics = {
            "frame_count": len(frames),
            "observation_count": len(observations),
            "segment_count": len(segments),
            "status_counts": _count_statuses(observations),
            "lost_frames": [
                {"frame_index": o.frame_index, "timestamp_ms": o.timestamp_ms, "reason": o.reason}
                for o in observations
                if o.status == "lost"
            ],
            "config": {
                "max_center_shift_ratio": self.config.max_center_shift_ratio,
                "max_area_change_ratio": self.config.max_area_change_ratio,
                "min_relocate_score": self.config.min_relocate_score,
                "phash_same_max": self.config.dedup.phash_same_max,
                "phash_ssim_max": self.config.dedup.phash_ssim_max,
                "ssim_same_min": self.config.dedup.ssim_same_min,
            },
        }
        return TrackingResult(
            observations=observations,
            segments=segments,
            diagnostics=diagnostics,
        )

    def _process_frame(
        self,
        sample: FrameSample,
        image: np.ndarray,
        *,
        previous_region: BoardRegion | None,
        previous_crop: np.ndarray | None,
        previous_edge_density: float | None,
        redetect_dir: Path,
        force_redetect: bool = False,
    ) -> TrackObservation:
        # First frame or no prior: always full-frame detect.
        if previous_region is None or previous_crop is None:
            return self._redetect(
                sample,
                image,
                previous_region=previous_region,
                previous_crop=previous_crop,
                redetect_dir=redetect_dir,
                reason="initial_detect",
            )

        if force_redetect:
            return self._redetect(
                sample,
                image,
                previous_region=previous_region,
                previous_crop=previous_crop,
                redetect_dir=redetect_dir,
                reason="recover_after_lost",
            )

        track_result = self.matcher.track_region(previous_crop, previous_region, image)
        need_redetect, redetect_reason = self._should_redetect(
            image,
            previous_region,
            track_result.transformed_region,
            track_result.good_matches,
            track_result.inlier_ratio,
            previous_edge_density=previous_edge_density,
        )
        if not need_redetect and track_result.transformed_region is not None:
            region = track_result.transformed_region
            crop = crop_region(image, region)
            kf = self.keyframe_scorer.score_crop(crop)
            return TrackObservation(
                frame_index=sample.frame_index,
                timestamp_ms=sample.timestamp_ms,
                status="tracked",
                region=region,
                reason="orb_track",
                match_score=track_result.score,
                keyframe_score=kf.total,
                occlusion_ratio=kf.occlusion_ratio,
                crop_bgr=crop,
                debug={
                    "good_matches": track_result.good_matches,
                    "inliers": track_result.inliers,
                    "inlier_ratio": track_result.inlier_ratio,
                },
            )

        return self._redetect(
            sample,
            image,
            previous_region=previous_region,
            previous_crop=previous_crop,
            redetect_dir=redetect_dir,
            reason=redetect_reason,
        )

    def _should_redetect(
        self,
        image: np.ndarray,
        previous_region: BoardRegion,
        tracked_region: BoardRegion | None,
        good_matches: int,
        inlier_ratio: float,
        *,
        previous_edge_density: float | None,
    ) -> tuple[bool, str]:
        cfg = self.config
        if tracked_region is None:
            return True, "feature_insufficient"
        if good_matches < cfg.matching.min_good_matches:
            return True, "feature_insufficient"
        if inlier_ratio < cfg.matching.min_inlier_ratio:
            return True, "feature_insufficient"

        frame_h, frame_w = image.shape[:2]
        diag = float(np.hypot(frame_w, frame_h))
        shift = _center_distance(previous_region, tracked_region) / max(diag, 1.0)
        if shift > cfg.max_center_shift_ratio:
            return True, "layout_shift"

        area_ratio = tracked_region.area / max(previous_region.area, 1)
        if abs(area_ratio - 1.0) > cfg.max_area_change_ratio:
            return True, "layout_area_change"

        crop = crop_region(image, tracked_region)
        density = _edge_density(crop)
        if density < cfg.min_region_edge_density:
            return True, "region_vanished"
        if previous_edge_density is not None and previous_edge_density > 1e-6:
            if density / previous_edge_density < cfg.edge_density_drop_ratio:
                return True, "content_density_drop"

        return False, "ok"

    def _redetect(
        self,
        sample: FrameSample,
        image: np.ndarray,
        *,
        previous_region: BoardRegion | None,
        previous_crop: np.ndarray | None,
        redetect_dir: Path,
        reason: str,
    ) -> TrackObservation:
        frame_path = sample.image_path
        if frame_path is None:
            frame_path = redetect_dir / f"frame_{sample.frame_index:06d}.png"
            if not cv2.imwrite(str(frame_path), image):
                raise OSError(f"failed to write redetect frame: {frame_path}")

        # Temporarily stamp metadata used by detector scoring.
        det_cfg = self.detector.config
        prev_frame_index = det_cfg.frame_index
        prev_timestamp = det_cfg.timestamp_ms
        det_cfg.frame_index = sample.frame_index
        det_cfg.timestamp_ms = sample.timestamp_ms
        try:
            candidates = self.detector.detect(frame_path, previous_region=previous_region)
        finally:
            det_cfg.frame_index = prev_frame_index
            det_cfg.timestamp_ms = prev_timestamp

        best = self._pick_relocate_candidate(image, candidates, previous_crop)
        if best is None:
            return TrackObservation(
                frame_index=sample.frame_index,
                timestamp_ms=sample.timestamp_ms,
                status="lost",
                region=None,
                reason=f"lost_after_{reason}",
                match_score=None,
                keyframe_score=None,
                occlusion_ratio=None,
                crop_bgr=None,
                debug={
                    "redetect_trigger": reason,
                    "candidate_count": len(candidates),
                },
            )

        candidate, match_score = best
        crop = crop_region(image, candidate.region)
        kf = self.keyframe_scorer.score_crop(crop)
        return TrackObservation(
            frame_index=sample.frame_index,
            timestamp_ms=sample.timestamp_ms,
            status="redetected",
            region=candidate.region,
            reason=reason,
            match_score=match_score,
            keyframe_score=kf.total,
            occlusion_ratio=kf.occlusion_ratio,
            crop_bgr=crop,
            debug={
                "redetect_trigger": reason,
                "candidate_score": candidate.score,
                "candidate_count": len(candidates),
                "relocate_score": match_score,
            },
        )

    def _pick_relocate_candidate(
        self,
        image: np.ndarray,
        candidates: list[BoardCandidate],
        previous_crop: np.ndarray | None,
    ) -> tuple[BoardCandidate, float] | None:
        if not candidates:
            return None
        if previous_crop is None:
            top = candidates[0]
            return top, float(top.score)

        ranked: list[tuple[float, float, BoardCandidate]] = []
        for cand in candidates:
            crop = crop_region(image, cand.region)
            sim = self.matcher.content_similarity(previous_crop, crop)
            # Blend detector confidence lightly so empty high-score boxes lose to content.
            combined = 0.75 * sim + 0.25 * float(cand.score)
            ranked.append((combined, sim, cand))
        ranked.sort(key=lambda t: t[0], reverse=True)
        best_combined, best_sim, best_cand = ranked[0]
        if best_sim < self.config.min_relocate_score and best_combined < self.config.min_relocate_score:
            # Still accept top detector hit if no prior content signal was strong,
            # but only when detector score is healthy — else mark lost.
            if best_cand.score < self.config.detector_min_score:
                return None
            # Weak content match: treat as lost rather than binding to a wrong board.
            if best_sim < self.config.min_relocate_score * 0.5:
                return None
        return best_cand, float(best_sim)

    def _build_versions(
        self,
        observations: list[TrackObservation],
        *,
        output_dir: Path,
    ) -> list[BoardSegment]:
        """Group observations into page versions and pick representative crops."""
        active: list[TrackObservation] = [
            o for o in observations if o.status != "lost" and o.region is not None and o.crop_bgr is not None
        ]
        if not active:
            # Still surface lost-only runs as empty versions; diagnostics carry lost frames.
            return []

        groups: list[list[TrackObservation]] = [[active[0]]]
        page_reasons: list[str | None] = [None]

        for obs in active[1:]:
            prev = groups[-1][-1]
            assert prev.crop_bgr is not None and obs.crop_bgr is not None
            compare = self.deduper.compare(
                prev.crop_bgr,
                obs.crop_bgr,
                previous_occlusion=prev.occlusion_ratio,
                current_occlusion=obs.occlusion_ratio,
            )
            if compare.decision == "same_page":
                groups[-1].append(obs)
            else:
                groups.append([obs])
                page_reasons.append(compare.reason)

        segments: list[BoardSegment] = []
        duration = self.config.default_frame_duration_ms
        for version_idx, group in enumerate(groups):
            crops = [o.crop_bgr for o in group if o.crop_bgr is not None]
            best_i, best_score = self.keyframe_scorer.pick_best(crops)
            if best_i < 0:
                continue
            best_obs = group[best_i]
            assert best_obs.region is not None and best_obs.crop_bgr is not None

            version_id = f"board-v{version_idx + 1:03d}"
            image_path = output_dir / f"{version_id}_representative.png"
            if not cv2.imwrite(str(image_path), best_obs.crop_bgr):
                raise OSError(f"failed to write representative frame: {image_path}")

            start_ms = group[0].timestamp_ms
            end_ms = group[-1].timestamp_ms + duration
            if end_ms <= start_ms:
                end_ms = start_ms + duration

            # Prefer most recent non-lost status within the group for diagnostics.
            status = group[-1].status
            dedup_debug = {
                "observation_count": len(group),
                "representative_frame_index": best_obs.frame_index,
                "representative_score": best_score.total,
                "sharpness": best_score.sharpness,
                "occlusion_ratio": best_score.occlusion_ratio,
                "glare_ratio": best_score.glare_ratio,
                "frame_indexes": [o.frame_index for o in group],
                "track_statuses": [o.status for o in group],
            }

            segments.append(
                BoardSegment(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    region=best_obs.region,
                    image_path=image_path,
                    confidence=best_score.total,
                    version_id=version_id,
                    track_status=status,
                    page_change_reason=page_reasons[version_idx],
                    representative_frame_index=best_obs.frame_index,
                    representative_timestamp_ms=best_obs.timestamp_ms,
                    source="board_track",
                )
            )
            # Attach debug onto image sidecar JSON via segment fields only; keep path list.
            _ = dedup_debug  # retained for local clarity / future artifact writers
        return segments


def _count_statuses(observations: list[TrackObservation]) -> dict[str, int]:
    counts: dict[str, int] = {"tracked": 0, "redetected": 0, "lost": 0}
    for obs in observations:
        counts[obs.status] = counts.get(obs.status, 0) + 1
    return counts


def _center_distance(a: BoardRegion, b: BoardRegion) -> float:
    ax = a.x + a.width / 2.0
    ay = a.y + a.height / 2.0
    bx = b.x + b.width / 2.0
    by = b.y + b.height / 2.0
    return float(np.hypot(ax - bx, ay - by))


def _edge_density(crop_bgr: np.ndarray) -> float:
    if crop_bgr.size == 0:
        return 0.0
    gray = crop_bgr if crop_bgr.ndim == 2 else cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    return float(np.mean(edges > 0))
