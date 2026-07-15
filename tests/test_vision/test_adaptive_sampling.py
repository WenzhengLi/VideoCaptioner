from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from course_video_analyzer.vision.adaptive_sampling import (
    AdaptiveSamplingConfig,
    AdaptiveVideoSampler,
    FrameOcrResult,
    FrameObservation,
    MorphologyTextPresenceDetector,
    TextPresenceResult,
    sample_video_adaptively,
    _crop_with_padding,
    _pair_content_views,
    _stable_content_region,
)


class FakeFrameSource:
    fps = 10.0

    def __init__(self, duration_ms: int, timeline: list[tuple[int, int, int]]) -> None:
        self.duration_ms = duration_ms
        self.total_frames = duration_ms // 100
        self.timeline = timeline
        self.read_timestamps: list[int] = []

    def read_at(self, timestamp_ms: int) -> tuple[int, np.ndarray]:
        self.read_timestamps.append(timestamp_ms)
        page = 0
        for start, end, value in self.timeline:
            if start <= timestamp_ms < end:
                page = value
                break
        image = np.full((80, 120, 3), page, dtype=np.uint8)
        return timestamp_ms // 100, image

    def close(self) -> None:
        return None


class EncodedTextDetector:
    def detect(self, image_bgr: np.ndarray) -> TextPresenceResult:
        page = int(image_bgr[0, 0, 0])
        return TextPresenceResult(has_text=page > 0, score=0.9 if page > 0 else 0.0)


class EncodedComparator:
    def similarity(self, first_bgr: np.ndarray, second_bgr: np.ndarray) -> float:
        return 1.0 if int(first_bgr[0, 0, 0]) == int(second_bgr[0, 0, 0]) else 0.0


class EncodedOcrProvider:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def recognize_frame(
        self,
        frame_index: int,
        timestamp_ms: int,
        image_bgr: np.ndarray,
    ) -> FrameOcrResult:
        del frame_index
        self.calls.append(timestamp_ms)
        page = int(image_bgr[0, 0, 0])
        return FrameOcrResult(
            has_text=page > 0,
            text=f"page-{page}" if page > 0 else "",
            text_lines=(
                [{"text": f"page-{page}", "confidence": 0.9}] if page > 0 else []
            ),
            score=0.9 if page > 0 else 0.0,
        )


class PickUncachedRepresentative:
    def select(
        self,
        observations: list[FrameObservation],
        *,
        comparator: object,
        image_loader: object = None,
    ):
        del comparator, image_loader
        selected = next(item for item in observations if item.ocr_result is None)
        return selected, 1.0


class AlwaysSimilarComparator:
    def similarity(self, first_bgr: np.ndarray, second_bgr: np.ndarray) -> float:
        del first_bgr, second_bgr
        return 1.0


def _sampler(**overrides: object) -> AdaptiveVideoSampler:
    values: dict[str, object] = {
        "initial_stride_ms": 10_000,
        "min_interval_ms": 500,
        "max_recursion_depth": 8,
        "max_no_text_span_ms": 3_000,
        "max_detected_frames": 500,
    }
    values.update(overrides)
    return AdaptiveVideoSampler(
        AdaptiveSamplingConfig(**values),  # type: ignore[arg-type]
        text_detector=EncodedTextDetector(),
        comparator=EncodedComparator(),
    )


def test_refines_text_intro_and_outro_boundaries(tmp_path: Path) -> None:
    source = FakeFrameSource(30_000, [(5_000, 25_000, 1)])
    result = _sampler().sample(source, tmp_path)

    assert len(result.intervals) == 1
    interval = result.intervals[0]
    assert 4_500 <= interval.start_ms <= 5_000
    assert 25_000 <= interval.end_ms <= 25_500
    assert result.stats.intro_filtered_range_ms == (0, interval.start_ms)
    assert result.stats.outro_filtered_range_ms == (interval.end_ms, 30_000)
    assert interval.representative_path.is_file()


def test_finds_short_text_between_two_similar_no_text_frames(tmp_path: Path) -> None:
    source = FakeFrameSource(20_000, [(8_000, 12_000, 1)])
    result = _sampler(initial_stride_ms=20_000).sample(source, tmp_path)

    assert len(result.intervals) == 1
    assert abs(result.intervals[0].start_ms - 8_000) <= 500
    assert abs(result.intervals[0].end_ms - 12_000) <= 500
    assert any(9_500 <= timestamp <= 10_500 for timestamp in source.read_timestamps)


def test_stable_text_interval_is_not_over_split(tmp_path: Path) -> None:
    source = FakeFrameSource(20_000, [(0, 20_000, 1)])
    provider = EncodedOcrProvider()
    result = AdaptiveVideoSampler(
        AdaptiveSamplingConfig(
            initial_stride_ms=10_000,
            min_interval_ms=500,
            representative_sample_count=5,
        ),
        ocr_provider=provider,
        comparator=EncodedComparator(),
    ).sample(source, tmp_path)

    assert len(result.intervals) == 1
    assert result.stats.actual_detected_frames == 7
    assert result.stats.full_ocr_count == 3
    assert provider.calls == [0, 10_000, 19_999]
    assert result.stats.ocr_cache_hit_count >= 1


def test_different_text_pages_are_split_into_stable_intervals(tmp_path: Path) -> None:
    source = FakeFrameSource(20_000, [(0, 10_000, 1), (10_000, 20_000, 2)])
    provider = EncodedOcrProvider()
    result = AdaptiveVideoSampler(
        AdaptiveSamplingConfig(initial_stride_ms=20_000, min_interval_ms=500),
        ocr_provider=provider,
        comparator=EncodedComparator(),
    ).sample(source, tmp_path)

    assert len(result.intervals) == 2
    assert result.intervals[0].end_ms == result.intervals[1].start_ms
    assert result.stats.final_image_count == 2
    assert result.stats.ocr_cache_hit_count > 0
    assert len(provider.calls) == len(set(provider.calls))
    assert len(list(tmp_path.glob("adaptive-*.jpg"))) == 2


def test_uncached_representative_is_ocrd_once_after_image_only_selection(
    tmp_path: Path,
) -> None:
    source = FakeFrameSource(20_000, [(0, 20_000, 1)])
    provider = EncodedOcrProvider()
    result = AdaptiveVideoSampler(
        AdaptiveSamplingConfig(initial_stride_ms=10_000, representative_sample_count=5),
        ocr_provider=provider,
        comparator=EncodedComparator(),
        representative_selector=PickUncachedRepresentative(),
    ).sample(source, tmp_path)

    assert result.stats.actual_detected_frames > result.stats.full_ocr_count
    assert result.stats.full_ocr_count == 4
    assert len(provider.calls) == len(set(provider.calls))
    assert result.intervals[0].representative_timestamp_ms not in {0, 10_000, 19_999}


def test_ocr_cache_is_keyed_by_actual_frame_index(tmp_path: Path) -> None:
    source = FakeFrameSource(200, [(0, 200, 1)])
    provider = EncodedOcrProvider()
    result = AdaptiveVideoSampler(
        AdaptiveSamplingConfig(
            initial_stride_ms=50,
            min_interval_ms=10,
            representative_sample_count=0,
        ),
        ocr_provider=provider,
        comparator=EncodedComparator(),
    ).sample(source, tmp_path)

    assert result.stats.ocr_request_count > result.stats.full_ocr_count
    assert result.stats.full_ocr_count == 2


def test_stable_interval_combines_cached_ocr_text_without_more_ocr(tmp_path: Path) -> None:
    source = FakeFrameSource(20_000, [(0, 10_000, 1), (10_000, 20_000, 2)])
    provider = EncodedOcrProvider()
    result = AdaptiveVideoSampler(
        AdaptiveSamplingConfig(initial_stride_ms=10_000, representative_sample_count=3),
        ocr_provider=provider,
        comparator=AlwaysSimilarComparator(),
    ).sample(source, tmp_path)

    assert len(result.intervals) == 1
    assert {line["text"] for line in result.intervals[0].combined_ocr_lines} == {
        "page-1",
        "page-2",
    }
    assert result.stats.full_ocr_count == 3


def test_disk_cache_reuses_frames_and_ocr_on_second_run(tmp_path: Path) -> None:
    source = FakeFrameSource(20_000, [(0, 20_000, 1)])
    first_provider = EncodedOcrProvider()
    config = AdaptiveSamplingConfig(initial_stride_ms=10_000, representative_sample_count=3)
    first = AdaptiveVideoSampler(
        config,
        ocr_provider=first_provider,
        comparator=EncodedComparator(),
    ).sample(source, tmp_path)

    second_provider = EncodedOcrProvider()
    second = AdaptiveVideoSampler(
        config,
        ocr_provider=second_provider,
        comparator=EncodedComparator(),
    ).sample(source, tmp_path)

    assert first.stats.full_ocr_count == 3
    assert second.stats.full_ocr_count == 0
    assert second.stats.disk_frame_cache_hit_count > 0
    assert second.stats.disk_ocr_cache_hit_count > 0
    assert second_provider.calls == []
    assert second.stats.peak_memory_image_count <= config.memory_frame_cache_size


def test_content_region_padding_and_median_suppress_crop_jitter() -> None:
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    region = _stable_content_region(
        [(100, 40, 200, 140), (95, 38, 205, 142), (102, 41, 198, 139)]
    )
    assert region == (100, 40, 200, 140)
    crop = _crop_with_padding(image, region, padding_ratio=0.10)
    assert crop.shape[:2] == (120, 120)
    first, second = _pair_content_views(
        image,
        image.copy(),
        (100, 40, 200, 140),
        (95, 38, 205, 142),
        padding_ratio=0.10,
    )
    assert first.shape == second.shape


def test_recursion_stops_at_configured_depth(tmp_path: Path) -> None:
    source = FakeFrameSource(60_000, [(29_000, 31_000, 1)])
    result = _sampler(
        initial_stride_ms=60_000,
        max_no_text_span_ms=1_000,
        max_recursion_depth=2,
    ).sample(source, tmp_path)

    assert result.stats.max_recursion_depth_reached == 2
    assert result.stats.actual_detected_frames <= 12
    assert result.stats.full_ocr_count <= 7


def test_representative_selector_prefers_sharper_frame() -> None:
    from course_video_analyzer.vision.adaptive_sampling import (
        SharpStableRepresentativeSelector,
    )

    blurry = FrameObservation(0, 0, np.zeros((20, 20, 3), np.uint8), True, 0.9, 1.0)
    sharp = FrameObservation(1_000, 1, np.zeros((20, 20, 3), np.uint8), True, 0.9, 100.0)
    selected, _ = SharpStableRepresentativeSelector().select(
        [blurry, sharp], comparator=EncodedComparator()
    )
    assert selected is sharp


def test_morphology_text_presence_detector_on_synthetic_images() -> None:
    config = AdaptiveSamplingConfig(text_presence_threshold=0.25, text_min_components=2)
    detector = MorphologyTextPresenceDetector(config)
    blank = np.full((360, 640, 3), 255, dtype=np.uint8)
    text = blank.copy()
    cv2.putText(text, "ADAPTIVE OCR", (40, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3)
    cv2.putText(text, "PAGE 2026", (40, 230), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3)

    assert detector.detect(blank).has_text is False
    assert detector.detect(text).has_text is True


def test_real_video_reader_filters_intro_outro_and_splits_pages(tmp_path: Path) -> None:
    video_path = tmp_path / "synthetic.avi"
    writer = cv2.VideoWriter(
        str(video_path),
        getattr(cv2, "VideoWriter_fourcc")(*"MJPG"),
        5.0,
        (640, 360),
    )
    assert writer.isOpened()
    for frame_index in range(50):
        frame = np.full((360, 640, 3), 245, dtype=np.uint8)
        if 10 <= frame_index < 25:
            cv2.putText(frame, "BOARD PAGE A", (60, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 0), 4)
            cv2.putText(frame, "LESSON 01", (60, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
        elif 25 <= frame_index < 40:
            cv2.putText(frame, "NEW CHAPTER", (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.7, (0, 0, 0), 4)
            cv2.putText(frame, "DIAGRAM 02", (190, 190), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)
            cv2.putText(frame, "SUMMARY", (330, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
        writer.write(frame)
    writer.release()

    result = sample_video_adaptively(
        video_path,
        tmp_path / "frames",
        duration_ms=10_000,
        total_frames=50,
        fps=5.0,
        config=AdaptiveSamplingConfig(
            initial_stride_ms=4_000,
            min_interval_ms=250,
            max_no_text_span_ms=1_500,
            text_presence_threshold=0.25,
            text_min_components=2,
            text_similarity_threshold=0.80,
            image_difference_threshold=0.20,
        ),
    )

    assert len(result.intervals) == 2
    assert result.stats.intro_filtered_range_ms is not None
    assert abs(result.stats.intro_filtered_range_ms[1] - 2_000) <= 250
    assert result.stats.outro_filtered_range_ms is not None
    assert abs(result.stats.outro_filtered_range_ms[0] - 8_000) <= 250
    assert result.stats.final_image_count == 2
