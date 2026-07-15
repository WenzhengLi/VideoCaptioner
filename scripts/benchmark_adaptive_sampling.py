"""Run adaptive sampling/tracking and optionally real PaddleOCR on one video."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from course_video_analyzer.media.ffmpeg import FFmpegMediaProcessor
from course_video_analyzer.runtime_cleanup import (
    cleanup_disposable_artifacts,
    validate_json_output,
)
from course_video_analyzer.vision.adaptive_sampling import (
    AdaptiveSamplingConfig,
    sample_video_adaptively,
)
from course_video_analyzer.vision.tracking import BoardTracker, FrameSample


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--initial-stride-ms", type=int, default=60_000)
    parser.add_argument("--min-interval-ms", type=int, default=1_000)
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--text-similarity", type=float, default=0.55)
    parser.add_argument("--image-difference", type=float, default=0.45)
    parser.add_argument("--max-detected-frames", type=int, default=2_000)
    parser.add_argument("--duration-ms", type=int, default=None)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--reuse-output", action="store_true")
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="保留帧、OCR 图片和跟踪目录；默认只保留 benchmark.json。",
    )
    args = parser.parse_args()

    video = args.video.resolve()
    requested_output = args.output.resolve()
    output = requested_output if args.reuse_output else _versioned_output_dir(requested_output)
    frames_dir = output / "frames"
    tracked_dir = output / "tracked"
    media = FFmpegMediaProcessor().inspect(video)
    duration_ms = min(media.duration_ms, args.duration_ms or media.duration_ms)
    total_frames = round(duration_ms / 1000 * media.fps)
    config = AdaptiveSamplingConfig(
        initial_stride_ms=args.initial_stride_ms,
        min_interval_ms=args.min_interval_ms,
        max_recursion_depth=args.max_depth,
        text_similarity_threshold=args.text_similarity,
        image_difference_threshold=args.image_difference,
        max_detected_frames=args.max_detected_frames,
    )

    ocr_provider = None
    if args.ocr:
        from course_video_analyzer.vision.frame_ocr import CachedBoardFrameOcrProvider
        from course_video_analyzer.vision.ocr import PaddleBoardOcr

        ocr_provider = CachedBoardFrameOcrProvider(
            PaddleBoardOcr(),
            probe_dir=output / "ocr_cache" / "probes",
            artifact_dir=output / "ocr_cache",
        )
    started = time.perf_counter()
    sampling = sample_video_adaptively(
        video,
        frames_dir,
        duration_ms=duration_ms,
        total_frames=total_frames,
        fps=media.fps,
        config=config,
        ocr_provider=ocr_provider,
        cache_dir=args.cache_dir.resolve() if args.cache_dir else None,
    )
    sampled_at = time.perf_counter()
    samples = [
        FrameSample(
            item.representative_frame_index,
            item.representative_timestamp_ms,
            image_path=item.representative_path,
        )
        for item in sampling.intervals
    ]
    tracking = BoardTracker().track(samples, output_dir=tracked_dir)
    tracked_at = time.perf_counter()

    payload: dict[str, Any] = {
        "video": str(video),
        "sampling_stats": sampling.stats.__dict__,
        "tracked_version_count": len(tracking.segments),
        "sampling_elapsed_s": round(sampled_at - started, 3),
        "tracking_elapsed_s": round(tracked_at - sampled_at, 3),
    }
    if args.ocr:
        ocr_at = time.perf_counter()
        payload.update(
            {
                "actual_full_ocr_count": sampling.stats.full_ocr_count,
                "ocr_cache_hit_count": sampling.stats.ocr_cache_hit_count,
                "ocr_elapsed_s_included_in_sampling": True,
                "total_elapsed_s": round(ocr_at - started, 3),
            }
        )
    else:
        payload["total_elapsed_s"] = round(tracked_at - started, 3)

    output.mkdir(parents=True, exist_ok=True)
    benchmark_path = output / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    validate_json_output(benchmark_path)
    if not args.keep_artifacts:
        cleanup = cleanup_disposable_artifacts(output)
        payload["cleanup"] = cleanup.as_dict()
        benchmark_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        validate_json_output(benchmark_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _versioned_output_dir(requested: Path) -> Path:
    if not requested.exists() or not any(requested.iterdir()):
        return requested
    version = 2
    while True:
        candidate = requested.with_name(f"{requested.name}-v{version:03d}")
        if not candidate.exists():
            return candidate
        version += 1


if __name__ == "__main__":
    raise SystemExit(main())
