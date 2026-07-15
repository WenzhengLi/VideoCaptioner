"""Create a new visual-analysis version while reusing an existing audio analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

from course_video_analyzer.exporters.boards_index import export_boards_index
from course_video_analyzer.exporters.json_exporter import export_analysis_json, export_timeline_json
from course_video_analyzer.exporters.srt_exporter import export_srt
from course_video_analyzer.exporters.txt_exporter import export_txt
from course_video_analyzer.media.ffmpeg import FFmpegMediaProcessor
from course_video_analyzer.models import AnalysisResult, OcrLine
from course_video_analyzer.timeline.merger import merge_timeline
from course_video_analyzer.vision.adaptive_sampling import (
    AdaptiveSamplingConfig,
    sample_video_adaptively,
)
from course_video_analyzer.vision.frame_ocr import CachedBoardFrameOcrProvider
from course_video_analyzer.vision.ocr import PaddleBoardOcr
from course_video_analyzer.vision.ocr_dedup import deduplicate_ocr_board_segments
from course_video_analyzer.vision.tracking import BoardTracker, FrameSample


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("baseline_analysis", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("output_txt", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--initial-stride-ms", type=int, default=60_000)
    parser.add_argument("--image-similarity-threshold", type=float, default=0.55)
    parser.add_argument("--image-difference-threshold", type=float, default=0.45)
    args = parser.parse_args()

    video = args.video.resolve()
    baseline_path = args.baseline_analysis.resolve()
    output_dir = args.output_dir.resolve()
    output_txt = args.output_txt.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"版本目录已存在且非空，拒绝覆盖: {output_dir}")
    if output_txt.exists():
        raise FileExistsError(f"输出 TXT 已存在，拒绝覆盖: {output_txt}")
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline = AnalysisResult.model_validate_json(baseline_path.read_text(encoding="utf-8"))
    media = FFmpegMediaProcessor().inspect(video)
    cache_dir = (
        args.cache_dir.resolve()
        if args.cache_dir is not None
        else output_dir.parent / "_video_cache" / _video_cache_key(video)
    )
    config = AdaptiveSamplingConfig(
        initial_stride_ms=args.initial_stride_ms,
        text_similarity_threshold=args.image_similarity_threshold,
        image_difference_threshold=args.image_difference_threshold,
    )
    provider = CachedBoardFrameOcrProvider(
        PaddleBoardOcr(),
        probe_dir=output_dir / "ocr_probes",
        artifact_dir=output_dir / "ocr_cache",
        min_confidence=config.ocr_presence_min_confidence,
        min_lines=config.ocr_presence_min_lines,
        region_padding_ratio=config.content_region_padding_ratio,
    )

    started = time.perf_counter()
    sampling = sample_video_adaptively(
        video,
        output_dir / "frames",
        duration_ms=media.duration_ms,
        total_frames=round(media.duration_ms / 1000 * media.fps),
        fps=media.fps,
        config=config,
        ocr_provider=provider,
        cache_dir=cache_dir,
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
    tracking = BoardTracker().track(samples, output_dir=output_dir / "boards")
    combined_by_frame = {
        item.representative_frame_index: [
            OcrLine.model_validate(line) for line in item.combined_ocr_lines
        ]
        for item in sampling.intervals
    }
    segments = [
        segment.model_copy(
            update={
                "text_lines": combined_by_frame.get(
                    segment.representative_frame_index or -1,
                    [],
                )
            }
        )
        for segment in tracking.segments
    ]
    segments = deduplicate_ocr_board_segments(segments)

    result = baseline.model_copy(
        update={
            "media": media,
            "board_segments": segments,
            "timeline": merge_timeline(baseline.speech_segments, segments),
            "diagnostics": {
                **baseline.diagnostics,
                "visual_version": output_dir.name,
                "adaptive_sampling": sampling.stats.__dict__,
                "tracking": tracking.diagnostics,
                "shared_cache_dir": str(cache_dir),
            },
        }
    )
    artifacts_dir = output_dir / "artifacts"
    export_analysis_json(result, artifacts_dir / "analysis.json")
    export_timeline_json(result.timeline, artifacts_dir / "timeline.json")
    generated_txt = export_txt(result, artifacts_dir / "transcript.txt")
    export_srt(result, artifacts_dir / "transcript.srt")
    export_boards_index(result, artifacts_dir / "boards_index.json")
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(generated_txt, output_txt)

    payload = {
        "video": str(video),
        "baseline_analysis": str(baseline_path),
        "output_txt": str(output_txt),
        "cache_dir": str(cache_dir),
        "sampling_stats": sampling.stats.__dict__,
        "tracked_version_count": len(tracking.segments),
        "final_board_count": len(segments),
        "sampling_elapsed_s": round(sampled_at - started, 3),
        "tracking_export_elapsed_s": round(time.perf_counter() - sampled_at, 3),
        "total_elapsed_s": round(time.perf_counter() - started, 3),
    }
    (output_dir / "version.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def _video_cache_key(source: Path) -> str:
    stat = source.stat()
    payload = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:20]


if __name__ == "__main__":
    raise SystemExit(main())
