"""OCR-scheduled adaptive interval splitting for course videos.

Frames and image comparisons are cheap and may be numerous. OCR is requested
only for coarse anchors, ambiguous/change midpoints, and an uncached final
representative. Both frame reads and OCR results are cached by timestamp.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol

import cv2
import imagehash
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

from course_video_analyzer.vision.frame_repository import DiskFrameRepository

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdaptiveSamplingConfig:
    """All thresholds controlling adaptive interval subdivision."""

    initial_stride_ms: int = 60_000
    min_interval_ms: int = 1_000
    max_recursion_depth: int = 8
    max_no_text_span_ms: int = 8_000
    text_presence_threshold: float = 0.42
    text_min_components: int = 3
    text_edge_density_full: float = 0.055
    text_similarity_threshold: float = 0.55
    no_text_similarity_threshold: float = 0.94
    image_difference_threshold: float = 0.45
    ocr_text_similarity_threshold: float = 0.88
    ocr_presence_min_confidence: float = 0.20
    ocr_presence_min_lines: int = 2
    representative_sample_count: int = 5
    content_region_padding_ratio: float = 0.08
    disk_cache_enabled: bool = True
    memory_frame_cache_size: int = 8
    comparison_size: tuple[int, int] = (320, 180)
    representative_text_weight: float = 0.35
    representative_sharpness_weight: float = 0.45
    representative_stability_weight: float = 0.20
    max_detected_frames: int = 2_000
    jpeg_quality: int = 92

    def validate(self) -> None:
        if self.initial_stride_ms <= 0:
            raise ValueError("initial_stride_ms must be > 0")
        if self.min_interval_ms <= 0:
            raise ValueError("min_interval_ms must be > 0")
        if self.max_recursion_depth < 0:
            raise ValueError("max_recursion_depth must be >= 0")
        if self.max_no_text_span_ms <= 0:
            raise ValueError("max_no_text_span_ms must be > 0")
        if self.max_detected_frames <= 0:
            raise ValueError("max_detected_frames must be > 0")
        if self.representative_sample_count < 0:
            raise ValueError("representative_sample_count must be >= 0")
        if self.ocr_presence_min_lines <= 0:
            raise ValueError("ocr_presence_min_lines must be > 0")
        if self.memory_frame_cache_size <= 0:
            raise ValueError("memory_frame_cache_size must be > 0")
        for name in (
            "text_presence_threshold",
            "text_similarity_threshold",
            "no_text_similarity_threshold",
            "image_difference_threshold",
            "ocr_text_similarity_threshold",
            "ocr_presence_min_confidence",
            "content_region_padding_ratio",
        ):
            value = float(getattr(self, name))
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")


@dataclass(frozen=True)
class TextPresenceResult:
    has_text: bool
    score: float
    component_count: int = 0
    edge_density: float = 0.0


@dataclass(frozen=True)
class FrameOcrResult:
    """Cached OCR decision and reusable recognized lines for one source frame."""

    has_text: bool
    text: str = ""
    text_lines: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    content_region: tuple[int, int, int, int] | None = None


@dataclass
class FrameObservation:
    timestamp_ms: int
    frame_index: int
    image_bgr: np.ndarray | None
    has_text: bool | None
    text_score: float
    sharpness: float
    component_count: int = 0
    edge_density: float = 0.0
    ocr_result: FrameOcrResult | None = None
    image_path: Path | None = None
    content_region: tuple[int, int, int, int] | None = None


@dataclass
class AdaptiveTextInterval:
    start_ms: int
    end_ms: int
    representative_timestamp_ms: int
    representative_frame_index: int
    representative_path: Path
    detected_timestamps_ms: list[int] = field(default_factory=list)
    text_score: float = 0.0
    stability_score: float = 0.0
    combined_ocr_lines: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AdaptiveSamplingStats:
    video_duration_ms: int
    video_total_frames: int
    actual_detected_frames: int
    image_comparison_count: int
    full_ocr_count: int
    ocr_request_count: int
    ocr_cache_hit_count: int
    disk_frame_cache_hit_count: int
    disk_ocr_cache_hit_count: int
    peak_memory_image_count: int
    intro_filtered_range_ms: tuple[int, int] | None
    outro_filtered_range_ms: tuple[int, int] | None
    valid_interval_count: int
    final_image_count: int
    max_recursion_depth_reached: int
    config: dict[str, object]


@dataclass
class AdaptiveSamplingResult:
    intervals: list[AdaptiveTextInterval]
    observations: list[FrameObservation]
    stats: AdaptiveSamplingStats
    ocr_cache: dict[int, FrameOcrResult] = field(default_factory=dict)

    @property
    def representative_paths(self) -> list[Path]:
        return [item.representative_path for item in self.intervals]


class RandomAccessFrameSource(Protocol):
    duration_ms: int
    total_frames: int
    fps: float

    def read_at(self, timestamp_ms: int) -> tuple[int, np.ndarray]: ...

    def close(self) -> None: ...


class TextPresenceDetector(Protocol):
    def detect(self, image_bgr: np.ndarray) -> TextPresenceResult: ...


class FrameOcrProvider(Protocol):
    def recognize_frame(
        self,
        frame_index: int,
        timestamp_ms: int,
        image_bgr: np.ndarray,
    ) -> FrameOcrResult: ...


class FrameComparator(Protocol):
    def similarity(self, first_bgr: np.ndarray, second_bgr: np.ndarray) -> float: ...


class RepresentativeSelector(Protocol):
    def select(
        self,
        observations: list[FrameObservation],
        *,
        comparator: FrameComparator,
        image_loader: Callable[[FrameObservation], np.ndarray] | None = None,
    ) -> tuple[FrameObservation, float]: ...


class OpenCvRandomAccessFrameSource:
    """OpenCV-backed random-access reader used by the production pipeline."""

    def __init__(
        self,
        source: Path,
        *,
        duration_ms: int | None = None,
        total_frames: int | None = None,
        fps: float | None = None,
    ) -> None:
        self.source = Path(source)
        if not self.source.is_file():
            raise FileNotFoundError(f"视频不存在: {self.source}")
        self._capture = cv2.VideoCapture(str(self.source))
        if not self._capture.isOpened():
            raise RuntimeError(f"无法打开视频: {self.source}")
        detected_fps = float(self._capture.get(cv2.CAP_PROP_FPS) or 0.0)
        detected_frames = int(self._capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.fps = float(fps if fps is not None and fps > 0 else detected_fps)
        self.total_frames = int(
            total_frames if total_frames is not None and total_frames > 0 else detected_frames
        )
        detected_duration = (
            int(round(self.total_frames / self.fps * 1000))
            if self.total_frames > 0 and self.fps > 0
            else 0
        )
        self.duration_ms = int(
            duration_ms if duration_ms is not None and duration_ms > 0 else detected_duration
        )

    def read_at(self, timestamp_ms: int) -> tuple[int, np.ndarray]:
        timestamp_ms = max(0, min(int(timestamp_ms), max(0, self.duration_ms - 1)))
        self._capture.set(cv2.CAP_PROP_POS_MSEC, float(timestamp_ms))
        ok, frame = self._capture.read()
        if not ok or frame is None:
            # Some codecs fail near the exact final timestamp; back off several frames.
            frame_ms = int(round(1000 / max(self.fps, 1.0)))
            for offset in (1, 2, 5, 10):
                fallback = max(0, timestamp_ms - frame_ms * offset)
                self._capture.set(cv2.CAP_PROP_POS_MSEC, float(fallback))
                ok, frame = self._capture.read()
                if ok and frame is not None:
                    break
        if not ok or frame is None:
            raise RuntimeError(f"无法读取视频帧: timestamp_ms={timestamp_ms}")
        frame_index = int(max(0, round(self._capture.get(cv2.CAP_PROP_POS_FRAMES) - 1)))
        return frame_index, frame

    def close(self) -> None:
        self._capture.release()


class MorphologyTextPresenceDetector:
    """Cheap morphology/edge detector that answers only whether text exists."""

    def __init__(self, config: AdaptiveSamplingConfig | None = None) -> None:
        self.config = config or AdaptiveSamplingConfig()

    def detect(self, image_bgr: np.ndarray) -> TextPresenceResult:
        if image_bgr.size == 0:
            return TextPresenceResult(False, 0.0)
        image = _resize_for_analysis(image_bgr, max_width=960)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 45, 135)
        edge_density = float(np.mean(edges > 0))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 3))
        connected = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
        contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        height, width = gray.shape[:2]
        image_area = float(height * width)
        component_count = 0
        component_area = 0.0
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area_ratio = (w * h) / max(image_area, 1.0)
            aspect = w / max(h, 1)
            if w < 12 or h < 4 or h > height * 0.22:
                continue
            if aspect < 0.55 or aspect > 35:
                continue
            if area_ratio < 0.00002 or area_ratio > 0.18:
                continue
            component_count += 1
            component_area += area_ratio

        component_score = min(1.0, component_count / max(self.config.text_min_components, 1))
        edge_score = min(
            1.0,
            edge_density / max(self.config.text_edge_density_full, 1e-6),
        )
        area_score = min(1.0, component_area / 0.025)
        score = float(np.clip(0.50 * component_score + 0.35 * edge_score + 0.15 * area_score, 0, 1))
        has_text = (
            component_count >= self.config.text_min_components
            and score >= self.config.text_presence_threshold
        )
        return TextPresenceResult(
            has_text=has_text,
            score=score,
            component_count=component_count,
            edge_density=edge_density,
        )


class HybridFrameComparator:
    """SSIM + pHash comparator for full frames or board screenshots."""

    def __init__(self, config: AdaptiveSamplingConfig | None = None) -> None:
        self.config = config or AdaptiveSamplingConfig()

    def similarity(self, first_bgr: np.ndarray, second_bgr: np.ndarray) -> float:
        size = self.config.comparison_size
        first = _prepare_gray(first_bgr, size)
        second = _prepare_gray(second_bgr, size)
        raw_ssim = structural_similarity(first, second, data_range=255)
        if isinstance(raw_ssim, tuple):
            raw_ssim = raw_ssim[0]
        ssim = float(raw_ssim)
        first_hash = imagehash.phash(Image.fromarray(first), hash_size=16)
        second_hash = imagehash.phash(Image.fromarray(second), hash_size=16)
        phash_similarity = 1.0 - min(1.0, float(first_hash - second_hash) / 256.0)
        return float(np.clip(0.72 * ssim + 0.28 * phash_similarity, 0.0, 1.0))


class SharpStableRepresentativeSelector:
    def __init__(self, config: AdaptiveSamplingConfig | None = None) -> None:
        self.config = config or AdaptiveSamplingConfig()

    def select(
        self,
        observations: list[FrameObservation],
        *,
        comparator: FrameComparator,
        image_loader: Callable[[FrameObservation], np.ndarray] | None = None,
    ) -> tuple[FrameObservation, float]:
        if not observations:
            raise ValueError("observations must not be empty")
        max_sharpness = max(item.sharpness for item in observations) or 1.0
        best = observations[0]
        best_score = -1.0
        loader = image_loader or _observation_image
        for index, item in enumerate(observations):
            neighbors: list[float] = []
            if index > 0:
                neighbors.append(
                    comparator.similarity(loader(item), loader(observations[index - 1]))
                )
            if index + 1 < len(observations):
                neighbors.append(
                    comparator.similarity(loader(item), loader(observations[index + 1]))
                )
            stability = sum(neighbors) / len(neighbors) if neighbors else 1.0
            sharpness = min(1.0, item.sharpness / max_sharpness)
            cfg = self.config
            score = (
                cfg.representative_text_weight * item.text_score
                + cfg.representative_sharpness_weight * sharpness
                + cfg.representative_stability_weight * stability
            )
            if score > best_score:
                best = item
                best_score = score
        return best, float(best_score)


class AdaptiveVideoSampler:
    """Split intervals while caching frames and scheduling as few OCR calls as possible."""

    def __init__(
        self,
        config: AdaptiveSamplingConfig | None = None,
        *,
        ocr_provider: FrameOcrProvider | None = None,
        text_detector: TextPresenceDetector | None = None,
        comparator: FrameComparator | None = None,
        representative_selector: RepresentativeSelector | None = None,
    ) -> None:
        self.config = config or AdaptiveSamplingConfig()
        self.config.validate()
        self.ocr_provider = ocr_provider
        self.text_detector = text_detector or MorphologyTextPresenceDetector(self.config)
        self.comparator = comparator or HybridFrameComparator(self.config)
        self.representative_selector = representative_selector or SharpStableRepresentativeSelector(
            self.config
        )
        self._max_depth_reached = 0
        self._comparison_count = 0
        self._image_loader: Callable[[FrameObservation], np.ndarray] | None = None
        self._raw_image_loader: Callable[[FrameObservation], np.ndarray] | None = None
        self._active_repository: DiskFrameRepository | None = None

    def sample(
        self,
        frame_source: RandomAccessFrameSource,
        output_dir: Path,
        *,
        prefix: str = "adaptive",
        cache_dir: Path | None = None,
    ) -> AdaptiveSamplingResult:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        duration_ms = int(frame_source.duration_ms)
        if duration_ms <= 0:
            raise ValueError("frame_source.duration_ms must be > 0")
        self._max_depth_reached = 0
        self._comparison_count = 0

        frame_cache: dict[int, FrameObservation] = {}
        ocr_cache: dict[int, FrameOcrResult] = {}
        ocr_cache_by_frame_index: dict[int, FrameOcrResult] = {}
        ocr_request_count = 0
        ocr_cache_hit_count = 0
        ocr_call_count = 0
        disk_frame_cache_hit_count = 0
        disk_ocr_cache_hit_count = 0
        peak_memory_image_count = 0
        repository = (
            DiskFrameRepository(
                cache_dir or output_dir / "_frame_cache",
                memory_cache_size=self.config.memory_frame_cache_size,
                jpeg_quality=self.config.jpeg_quality,
            )
            if self.config.disk_cache_enabled
            else None
        )
        self._active_repository = repository

        def load_image(observation: FrameObservation) -> np.ndarray:
            nonlocal peak_memory_image_count
            if observation.image_bgr is not None:
                return observation.image_bgr
            if repository is None:
                raise ValueError(f"frame {observation.frame_index} has no decoded image")
            stored = repository.get_frame(observation.timestamp_ms)
            if stored is None:
                raise FileNotFoundError(f"missing cached frame: {observation.timestamp_ms}")
            image = repository.load_image(stored)
            peak_memory_image_count = max(
                peak_memory_image_count,
                repository.memory_image_count,
            )
            return image

        def get_frame(timestamp_ms: int) -> FrameObservation:
            nonlocal disk_frame_cache_hit_count, peak_memory_image_count
            timestamp_ms = max(0, min(int(timestamp_ms), duration_ms - 1))
            cached = frame_cache.get(timestamp_ms)
            if cached is not None:
                return cached
            if len(frame_cache) >= self.config.max_detected_frames:
                raise RuntimeError(
                    "自适应抽帧超过 max_detected_frames="
                    f"{self.config.max_detected_frames}，请增大最小间距或最大帧数"
                )
            stored = repository.get_frame(timestamp_ms) if repository is not None else None
            if stored is not None:
                disk_frame_cache_hit_count += 1
                observation = FrameObservation(
                    timestamp_ms=stored.timestamp_ms,
                    frame_index=stored.frame_index,
                    image_bgr=None,
                    has_text=None,
                    text_score=0.0,
                    sharpness=stored.sharpness,
                    image_path=stored.image_path,
                )
                frame_cache[timestamp_ms] = observation
                return observation
            frame_index, image = frame_source.read_at(timestamp_ms)
            sharpness = _sharpness(image)
            image_path: Path | None = None
            cached_image: np.ndarray | None = image
            if repository is not None:
                stored = repository.store_frame(
                    timestamp_ms,
                    frame_index,
                    image,
                    sharpness=sharpness,
                )
                image_path = stored.image_path
                cached_image = None
                peak_memory_image_count = max(
                    peak_memory_image_count,
                    repository.memory_image_count,
                )
            observation = FrameObservation(
                timestamp_ms=timestamp_ms,
                frame_index=frame_index,
                image_bgr=cached_image,
                has_text=None,
                text_score=0.0,
                sharpness=sharpness,
                image_path=image_path,
            )
            frame_cache[timestamp_ms] = observation
            return observation

        def request_ocr(timestamp_ms: int) -> FrameObservation:
            nonlocal ocr_request_count, ocr_cache_hit_count, ocr_call_count
            nonlocal disk_ocr_cache_hit_count
            observation = get_frame(timestamp_ms)
            ocr_request_count += 1
            cached = ocr_cache.get(observation.timestamp_ms) or ocr_cache_by_frame_index.get(
                observation.frame_index
            )
            if cached is None and repository is not None:
                stored_ocr = repository.load_ocr(observation.timestamp_ms)
                if stored_ocr is None:
                    stored_ocr = repository.load_ocr_by_frame_index(observation.frame_index)
                if stored_ocr is not None:
                    cached = FrameOcrResult(**stored_ocr)
                    disk_ocr_cache_hit_count += 1
            if cached is not None:
                ocr_cache_hit_count += 1
                ocr_cache[observation.timestamp_ms] = cached
                observation.ocr_result = cached
                observation.has_text = cached.has_text
                observation.text_score = cached.score
                observation.content_region = cached.content_region
                if repository is not None:
                    repository.store_ocr(
                        observation.timestamp_ms,
                        has_text=cached.has_text,
                        score=cached.score,
                        text=cached.text,
                        text_lines=cached.text_lines,
                        content_region=cached.content_region,
                    )
                return observation
            if self.ocr_provider is not None:
                result = self.ocr_provider.recognize_frame(
                    observation.frame_index,
                    observation.timestamp_ms,
                    load_image(observation),
                )
            else:
                detected = self.text_detector.detect(load_image(observation))
                result = FrameOcrResult(
                    has_text=detected.has_text,
                    score=detected.score,
                )
                observation.component_count = detected.component_count
                observation.edge_density = detected.edge_density
            ocr_call_count += 1
            ocr_cache[observation.timestamp_ms] = result
            ocr_cache_by_frame_index[observation.frame_index] = result
            observation.ocr_result = result
            observation.has_text = result.has_text
            observation.text_score = result.score
            observation.content_region = result.content_region
            if repository is not None:
                repository.store_ocr(
                    observation.timestamp_ms,
                    has_text=result.has_text,
                    score=result.score,
                    text=result.text,
                    text_lines=result.text_lines,
                    content_region=result.content_region,
                )
            return observation

        def analysis_image(observation: FrameObservation) -> np.ndarray:
            return _crop_with_padding(
                load_image(observation),
                observation.content_region,
                padding_ratio=self.config.content_region_padding_ratio,
            )

        self._image_loader = analysis_image
        self._raw_image_loader = load_image

        coarse = list(range(0, duration_ms, self.config.initial_stride_ms))
        final_ts = duration_ms - 1
        if not coarse or coarse[-1] != final_ts:
            coarse.append(final_ts)
        for timestamp in coarse:
            request_ocr(timestamp)
        for left_ts, right_ts in zip(coarse, coarse[1:]):
            self._refine_interval(left_ts, right_ts, 0, get_frame, request_ocr)

        observations = sorted(frame_cache.values(), key=lambda item: item.timestamp_ms)
        ocr_observations = sorted(
            (item for item in observations if item.ocr_result is not None),
            key=lambda item: item.timestamp_ms,
        )
        interval_groups = self._build_text_groups(ocr_observations)
        intervals: list[AdaptiveTextInterval] = []
        for index, (start_ms, end_ms, group) in enumerate(interval_groups, start=1):
            candidates = list(group)
            stable_region = _stable_content_region(
                [item.content_region for item in group if item.content_region is not None]
            )
            if stable_region is not None:
                for candidate in candidates:
                    candidate.content_region = stable_region
            if self.config.representative_sample_count > 0 and end_ms > start_ms:
                for sample_index in range(1, self.config.representative_sample_count + 1):
                    timestamp = start_ms + (end_ms - start_ms) * sample_index // (
                        self.config.representative_sample_count + 1
                    )
                    candidate = get_frame(timestamp)
                    if candidate.content_region is None:
                        candidate.content_region = stable_region
                    if all(item.timestamp_ms != candidate.timestamp_ms for item in candidates):
                        candidates.append(candidate)
                candidates.sort(key=lambda item: item.timestamp_ms)
            representative, stability = self.representative_selector.select(
                candidates,
                comparator=self.comparator,
                image_loader=analysis_image,
            )
            representative = request_ocr(representative.timestamp_ms)
            if not representative.has_text:
                representative, stability = self.representative_selector.select(
                    group,
                    comparator=self.comparator,
                    image_loader=analysis_image,
                )
                representative = request_ocr(representative.timestamp_ms)
            image_path = output_dir / f"{prefix}-{index:04d}.jpg"
            ok = cv2.imwrite(
                str(image_path),
                load_image(representative),
                [cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality],
            )
            if not ok:
                raise OSError(f"无法写入代表帧: {image_path}")
            intervals.append(
                AdaptiveTextInterval(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    representative_timestamp_ms=representative.timestamp_ms,
                    representative_frame_index=representative.frame_index,
                    representative_path=image_path,
                    detected_timestamps_ms=[item.timestamp_ms for item in group],
                    text_score=representative.text_score,
                    stability_score=stability,
                    combined_ocr_lines=_combine_ocr_lines(
                        [
                            line
                            for item in [*group, representative]
                            if item.ocr_result is not None
                            for line in item.ocr_result.text_lines
                        ]
                    ),
                )
            )

        first_start = intervals[0].start_ms if intervals else duration_ms
        last_end = intervals[-1].end_ms if intervals else 0
        intro = (0, first_start) if first_start > 0 else None
        outro = (last_end, duration_ms) if last_end < duration_ms else None
        observations = sorted(frame_cache.values(), key=lambda item: item.timestamp_ms)
        stats = AdaptiveSamplingStats(
            video_duration_ms=duration_ms,
            video_total_frames=int(frame_source.total_frames),
            actual_detected_frames=len(observations),
            image_comparison_count=self._comparison_count,
            full_ocr_count=ocr_call_count,
            ocr_request_count=ocr_request_count,
            ocr_cache_hit_count=ocr_cache_hit_count,
            disk_frame_cache_hit_count=disk_frame_cache_hit_count,
            disk_ocr_cache_hit_count=disk_ocr_cache_hit_count,
            peak_memory_image_count=peak_memory_image_count,
            intro_filtered_range_ms=intro,
            outro_filtered_range_ms=outro,
            valid_interval_count=len(intervals),
            final_image_count=len(intervals),
            max_recursion_depth_reached=self._max_depth_reached,
            config=asdict(self.config),
        )
        LOGGER.info(
            "adaptive_sampling total_frames=%s extracted_frames=%s ocr_calls=%s "
            "ocr_requests=%s cache_hits=%s intro=%s outro=%s intervals=%s final_images=%s",
            stats.video_total_frames,
            stats.actual_detected_frames,
            stats.full_ocr_count,
            stats.ocr_request_count,
            stats.ocr_cache_hit_count,
            stats.intro_filtered_range_ms,
            stats.outro_filtered_range_ms,
            stats.valid_interval_count,
            stats.final_image_count,
        )
        result = AdaptiveSamplingResult(
            intervals=intervals,
            observations=observations,
            stats=stats,
            ocr_cache=dict(ocr_cache),
        )
        self._image_loader = None
        self._raw_image_loader = None
        if repository is not None:
            repository.close()
        self._active_repository = None
        return result

    def close(self) -> None:
        if self._active_repository is not None:
            self._active_repository.close()
            self._active_repository = None

    def _refine_interval(
        self,
        left_ts: int,
        right_ts: int,
        depth: int,
        get_frame: Callable[[int], FrameObservation],
        request_ocr: Callable[[int], FrameObservation],
    ) -> None:
        self._max_depth_reached = max(self._max_depth_reached, depth)
        gap = right_ts - left_ts
        if gap <= self.config.min_interval_ms or depth >= self.config.max_recursion_depth:
            return
        left = request_ocr(left_ts)
        right = request_ocr(right_ts)
        similarity = self._compare(left, right)
        should_split = False
        if left.has_text != right.has_text:
            should_split = True
        elif left.has_text and right.has_text:
            image_changed = (
                similarity < self.config.text_similarity_threshold
                and 1.0 - similarity > self.config.image_difference_threshold
            )
            text_changed = self.ocr_provider is None or (
                self._ocr_text_similarity(left, right)
                < self.config.ocr_text_similarity_threshold
            )
            should_split = image_changed and text_changed
        else:
            should_split = (
                (
                    similarity < self.config.no_text_similarity_threshold
                    and 1.0 - similarity > self.config.image_difference_threshold
                )
                or gap > self.config.max_no_text_span_ms
            )
        if not should_split:
            return
        middle = left_ts + gap // 2
        if middle <= left_ts or middle >= right_ts:
            return
        get_frame(middle)
        request_ocr(middle)
        self._refine_interval(left_ts, middle, depth + 1, get_frame, request_ocr)
        self._refine_interval(middle, right_ts, depth + 1, get_frame, request_ocr)

    def _build_text_groups(
        self,
        observations: list[FrameObservation],
    ) -> list[tuple[int, int, list[FrameObservation]]]:
        groups: list[tuple[int, int, list[FrameObservation]]] = []
        current: list[FrameObservation] = []
        start_ms = 0
        for observation in observations:
            if not observation.has_text:
                if current:
                    groups.append((start_ms, observation.timestamp_ms, current))
                    current = []
                continue
            if not current:
                current = [observation]
                start_ms = observation.timestamp_ms
                continue
            previous = current[-1]
            similarity = self._compare(previous, observation)
            image_changed = similarity < self.config.text_similarity_threshold
            text_changed = self.ocr_provider is None or (
                self._ocr_text_similarity(previous, observation)
                < self.config.ocr_text_similarity_threshold
            )
            if image_changed and text_changed:
                groups.append((start_ms, observation.timestamp_ms, current))
                current = [observation]
                start_ms = observation.timestamp_ms
            else:
                current.append(observation)
        if current:
            groups.append((start_ms, self._interval_end(current, observations), current))
        return [item for item in groups if item[1] > item[0]]

    def _compare(self, first: FrameObservation, second: FrameObservation) -> float:
        self._comparison_count += 1
        raw_loader = self._raw_image_loader or _observation_image
        first_image = raw_loader(first)
        second_image = raw_loader(second)
        first_view, second_view = _pair_content_views(
            first_image,
            second_image,
            first.content_region,
            second.content_region,
            padding_ratio=self.config.content_region_padding_ratio,
        )
        return self.comparator.similarity(first_view, second_view)

    @staticmethod
    def _ocr_text_similarity(first: FrameObservation, second: FrameObservation) -> float:
        first_text = (first.ocr_result.text if first.ocr_result else "").strip()
        second_text = (second.ocr_result.text if second.ocr_result else "").strip()
        if not first_text and not second_text:
            return 1.0
        if not first_text or not second_text:
            return 0.0
        return SequenceMatcher(None, first_text, second_text, autojunk=False).ratio()

    @staticmethod
    def _interval_end(
        current: list[FrameObservation],
        observations: list[FrameObservation],
    ) -> int:
        last = current[-1]
        for item in observations:
            if item.timestamp_ms > last.timestamp_ms and not item.has_text:
                return item.timestamp_ms
        return observations[-1].timestamp_ms + 1


def sample_video_adaptively(
    source: Path,
    output_dir: Path,
    *,
    duration_ms: int,
    total_frames: int = 0,
    fps: float = 0.0,
    config: AdaptiveSamplingConfig | None = None,
    ocr_provider: FrameOcrProvider | None = None,
    text_detector: TextPresenceDetector | None = None,
    comparator: FrameComparator | None = None,
    representative_selector: RepresentativeSelector | None = None,
    cache_dir: Path | None = None,
) -> AdaptiveSamplingResult:
    """Reusable production entrypoint requested by the adaptive sampling task."""
    frame_source = OpenCvRandomAccessFrameSource(
        source,
        duration_ms=duration_ms,
        total_frames=total_frames,
        fps=fps,
    )
    sampler: AdaptiveVideoSampler | None = None
    try:
        sampler = AdaptiveVideoSampler(
            config,
            ocr_provider=ocr_provider,
            text_detector=text_detector,
            comparator=comparator,
            representative_selector=representative_selector,
        )
        return sampler.sample(frame_source, output_dir, cache_dir=cache_dir)
    finally:
        if sampler is not None:
            sampler.close()
        frame_source.close()


def _resize_for_analysis(image_bgr: np.ndarray, *, max_width: int) -> np.ndarray:
    height, width = image_bgr.shape[:2]
    if width <= max_width:
        return image_bgr
    scale = max_width / width
    return cv2.resize(
        image_bgr,
        (max_width, max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )


def _prepare_gray(image_bgr: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    gray = image_bgr if image_bgr.ndim == 2 else cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, size, interpolation=cv2.INTER_AREA)


def _sharpness(image_bgr: np.ndarray) -> float:
    gray = image_bgr if image_bgr.ndim == 2 else cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _observation_image(observation: FrameObservation) -> np.ndarray:
    if observation.image_bgr is None:
        raise ValueError(f"frame {observation.frame_index} image is not loaded")
    return observation.image_bgr


def _crop_with_padding(
    image_bgr: np.ndarray,
    region: tuple[int, int, int, int] | None,
    *,
    padding_ratio: float,
) -> np.ndarray:
    if region is None:
        return image_bgr
    height, width = image_bgr.shape[:2]
    x1, y1, x2, y2 = region
    pad_x = round(max(1, x2 - x1) * padding_ratio)
    pad_y = round(max(1, y2 - y1) * padding_ratio)
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(width, x2 + pad_x)
    y2 = min(height, y2 + pad_y)
    crop = image_bgr[y1:y2, x1:x2]
    return crop if crop.size > 0 else image_bgr


def _stable_content_region(
    regions: list[tuple[int, int, int, int]],
) -> tuple[int, int, int, int] | None:
    """Median box suppresses detector jitter such as 100px vs 110px crops."""
    if not regions:
        return None
    coordinates = list(zip(*regions))
    medians = [int(round(float(np.median(values)))) for values in coordinates]
    x1, y1, x2, y2 = medians
    if x2 <= x1 or y2 <= y1:
        return regions[0]
    return x1, y1, x2, y2


def _pair_content_views(
    first_image: np.ndarray,
    second_image: np.ndarray,
    first_region: tuple[int, int, int, int] | None,
    second_region: tuple[int, int, int, int] | None,
    *,
    padding_ratio: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Use one stabilized crop for jitter, separate crops for real layout moves."""
    if first_region is None and second_region is None:
        return first_image, second_image
    if first_region is None:
        first_region = second_region
    if second_region is None:
        second_region = first_region
    assert first_region is not None and second_region is not None
    if _region_iou(first_region, second_region) >= 0.50:
        stable = _stable_content_region([first_region, second_region])
        return (
            _crop_with_padding(first_image, stable, padding_ratio=padding_ratio),
            _crop_with_padding(second_image, stable, padding_ratio=padding_ratio),
        )
    return (
        _crop_with_padding(first_image, first_region, padding_ratio=padding_ratio),
        _crop_with_padding(second_image, second_region, padding_ratio=padding_ratio),
    )


def _region_iou(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if intersection <= 0:
        return 0.0
    first_area = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    second_area = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def estimated_total_frames(duration_ms: int, fps: float) -> int:
    return int(math.ceil(max(0, duration_ms) / 1000.0 * max(0.0, fps)))


def _combine_ocr_lines(
    lines: list[dict[str, Any]],
    *,
    similarity_threshold: float = 0.92,
) -> list[dict[str, Any]]:
    """Combine cached OCR lines without issuing another OCR request."""
    output: list[dict[str, Any]] = []
    normalized: list[str] = []
    for line in lines:
        text = str(line.get("corrected_text") or line.get("text") or "").strip()
        key = re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()
        if not key:
            continue
        duplicate_index = next(
            (
                index
                for index, old in enumerate(normalized)
                if key == old
                or (
                    min(len(key), len(old)) >= 6
                    and SequenceMatcher(None, key, old, autojunk=False).ratio()
                    >= similarity_threshold
                )
            ),
            None,
        )
        if duplicate_index is None:
            output.append(dict(line))
            normalized.append(key)
            continue
        old_confidence = float(output[duplicate_index].get("confidence") or 0.0)
        new_confidence = float(line.get("confidence") or 0.0)
        if new_confidence > old_confidence:
            output[duplicate_index] = dict(line)
            normalized[duplicate_index] = key
    return output
