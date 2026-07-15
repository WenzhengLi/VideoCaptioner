"""Recoverable top-level orchestration and TASK-009 service entrypoint."""

from __future__ import annotations

import json
import math
import re
import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from course_video_analyzer.audio.alignment import (
    AlignmentConfig,
    align_speech_with_diagnostics,
    write_alignment_artifact,
)
from course_video_analyzer.audio.base import SpeakerDiarizer, SpeechRecognizer
from course_video_analyzer.exporters.boards_index import export_boards_index
from course_video_analyzer.exporters.json_exporter import (
    export_analysis_json,
    export_timeline_json,
    sort_analysis_result,
)
from course_video_analyzer.exporters.srt_exporter import export_srt
from course_video_analyzer.exporters.txt_exporter import export_txt
from course_video_analyzer.jobs.workspace import JobWorkspace, atomic_write_text
from course_video_analyzer.models import (
    AnalysisResult,
    BoardSegment,
    JobStage,
    MediaInfo,
    OcrLine,
    SpeakerTurn,
    SpeechSegment,
    TimelineEntry,
    TranscriptSegment,
)
from course_video_analyzer.processing_profiles import resolve_processing_config
from course_video_analyzer.timeline.merger import merge_timeline
from course_video_analyzer.vision.base import BoardOcr

# Stable stage order for resume / skip.
PIPELINE_STAGES: tuple[JobStage, ...] = (
    JobStage.MEDIA,
    JobStage.TRANSCRIPT,
    JobStage.DIARIZATION,
    JobStage.ALIGNMENT,
    JobStage.BOARD_DETECT,
    JobStage.BOARD_TRACK,
    JobStage.BOARD_OCR,
    JobStage.MERGE,
    JobStage.EXPORT,
)

REL_AUDIO_ARTIFACTS = "artifacts/audio"
REL_BOARD_ARTIFACTS = "artifacts/boards"
REL_TRANSCRIPT = f"{REL_AUDIO_ARTIFACTS}/transcript.json"
REL_SPEAKER_TURNS = f"{REL_AUDIO_ARTIFACTS}/speaker_turns.json"
REL_ALIGNMENT = f"{REL_AUDIO_ARTIFACTS}/alignment.json"
REL_BOARD_SEGMENTS = f"{REL_BOARD_ARTIFACTS}/segments.json"
REL_ANALYSIS = "artifacts/analysis.json"
REL_TIMELINE = "artifacts/timeline.json"
REL_TXT = "artifacts/transcript.txt"
REL_SRT = "artifacts/transcript.srt"
REL_BOARDS_INDEX = f"{REL_BOARD_ARTIFACTS}/index.json"
REL_ADAPTIVE_RESULTS = f"{REL_BOARD_ARTIFACTS}/adaptive_results.json"
REL_FRAME_MANIFEST = "frames/manifest.json"


@runtime_checkable
class MediaProcessor(Protocol):
    def inspect(self, source: Path) -> MediaInfo: ...

    def extract_wav(self, source: Path, output_wav: Path) -> Path: ...


@runtime_checkable
class BoardTrackerProtocol(Protocol):
    def track(
        self,
        frames: list[Any],
        *,
        output_dir: Path,
        initial_region: Any | None = None,
    ) -> Any: ...


class AudioPipeline(Protocol):
    def process(self, media: MediaInfo, job_dir: Path) -> list[SpeechSegment]: ...


class BoardPipeline(Protocol):
    def process(self, media: MediaInfo, job_dir: Path) -> list[BoardSegment]: ...


class TimelineMerger(Protocol):
    def merge(
        self,
        speech: list[SpeechSegment],
        boards: list[BoardSegment],
    ) -> list[TimelineEntry]: ...


@dataclass
class AnalysisDependencies:
    """Injectable adapters for tests / production factories."""

    media_processor: MediaProcessor
    recognizer: SpeechRecognizer | None = None
    diarizer: SpeakerDiarizer | None = None
    board_tracker: BoardTrackerProtocol | None = None
    board_ocr: BoardOcr | None = None


class CourseVideoPipeline:
    """Simple non-workspace coordinator kept for TASK-001 compatibility."""

    def __init__(
        self,
        media_processor: MediaProcessor,
        audio_pipeline: AudioPipeline,
        board_pipeline: BoardPipeline,
        timeline_merger: TimelineMerger | None = None,
    ) -> None:
        self.media_processor = media_processor
        self.audio_pipeline = audio_pipeline
        self.board_pipeline = board_pipeline
        self.timeline_merger = timeline_merger

    def process(self, source: Path, job_dir: Path) -> AnalysisResult:
        media = self.media_processor.inspect(source)
        speech = self.audio_pipeline.process(media, job_dir)
        boards = self.board_pipeline.process(media, job_dir)
        if self.timeline_merger is not None:
            timeline = self.timeline_merger.merge(speech, boards)
        else:
            timeline = merge_timeline(speech, boards)
        return AnalysisResult(
            media=media,
            speech_segments=speech,
            board_segments=boards,
            timeline=timeline,
        )


class AnalysisService:
    """Single entrypoint for TASK-009: create jobs, run with resume, load results."""

    def __init__(self, deps: AnalysisDependencies) -> None:
        self.deps = deps

    @classmethod
    def from_dependencies(
        cls,
        *,
        media_processor: MediaProcessor,
        recognizer: SpeechRecognizer | None = None,
        diarizer: SpeakerDiarizer | None = None,
        board_tracker: BoardTrackerProtocol | None = None,
        board_ocr: BoardOcr | None = None,
    ) -> AnalysisService:
        return cls(
            AnalysisDependencies(
                media_processor=media_processor,
                recognizer=recognizer,
                diarizer=diarizer,
                board_tracker=board_tracker,
                board_ocr=board_ocr,
            )
        )

    def create_job(
        self,
        source: Path,
        jobs_root: Path,
        config: dict[str, Any] | None = None,
    ) -> JobWorkspace:
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(f"媒体文件不存在: {source}")
        workspace = JobWorkspace(Path(jobs_root))
        workspace.create(source, config=resolve_processing_config(config))
        return workspace

    def run(self, workspace: JobWorkspace, *, resume: bool = True) -> AnalysisResult:
        workspace.ensure_layout()
        state = workspace.load_state()
        # Resolve again so jobs created before profiles existed keep their
        # explicit legacy switches while gaining deterministic defaults.
        ctx = _RunContext(workspace=workspace, config=resolve_processing_config(state.config))

        for stage in PIPELINE_STAGES:
            if resume and workspace.should_skip(stage):
                self._hydrate_from_artifacts(stage, ctx)
                continue
            workspace.mark_running(stage)
            try:
                artifacts = self._run_stage(stage, ctx)
                workspace.mark_completed(stage, artifact_paths=artifacts)
            except Exception as exc:
                workspace.mark_failed(stage, str(exc))
                raise

        result = ctx.result
        if result is None:
            result = self.load_result(workspace)
        if result is None:
            raise RuntimeError("导出完成后无法加载 AnalysisResult")
        return result

    def load_result(self, workspace: JobWorkspace) -> AnalysisResult | None:
        path = workspace.job_dir / REL_ANALYSIS
        if not path.exists():
            return None
        return AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))

    def _run_stage(self, stage: JobStage, ctx: _RunContext) -> list[str]:
        if stage is JobStage.MEDIA:
            return self._stage_media(ctx)
        if stage is JobStage.TRANSCRIPT:
            return self._stage_transcript(ctx)
        if stage is JobStage.DIARIZATION:
            return self._stage_diarization(ctx)
        if stage is JobStage.ALIGNMENT:
            return self._stage_alignment(ctx)
        if stage is JobStage.BOARD_DETECT:
            return self._stage_board_detect(ctx)
        if stage is JobStage.BOARD_TRACK:
            return self._stage_board_track(ctx)
        if stage is JobStage.BOARD_OCR:
            return self._stage_board_ocr(ctx)
        if stage is JobStage.MERGE:
            return self._stage_merge(ctx)
        if stage is JobStage.EXPORT:
            return self._stage_export(ctx)
        raise RuntimeError(f"未知阶段: {stage}")

    def _hydrate_from_artifacts(self, stage: JobStage, ctx: _RunContext) -> None:
        """Reload in-memory context when a completed stage is skipped."""
        ws = ctx.workspace
        if stage is JobStage.MEDIA:
            media = ws.load_media()
            if media is not None:
                ctx.media = media
        elif stage is JobStage.TRANSCRIPT:
            ctx.transcripts = _load_model_list(
                ws.job_dir / REL_TRANSCRIPT,
                TranscriptSegment,
            )
        elif stage is JobStage.DIARIZATION:
            ctx.speaker_turns = _load_model_list(
                ws.job_dir / REL_SPEAKER_TURNS,
                SpeakerTurn,
            )
        elif stage is JobStage.ALIGNMENT:
            ctx.speech_segments = _load_speech_from_alignment(ws.job_dir / REL_ALIGNMENT)
            if not ctx.speech_segments:
                ctx.speech_segments = []
        elif stage is JobStage.BOARD_TRACK:
            ctx.board_segments = _load_model_list(
                ws.job_dir / REL_BOARD_SEGMENTS,
                BoardSegment,
            )
        elif stage is JobStage.BOARD_OCR:
            ctx.board_segments = _load_model_list(
                ws.job_dir / REL_BOARD_SEGMENTS,
                BoardSegment,
            )
        elif stage is JobStage.MERGE or stage is JobStage.EXPORT:
            loaded = self.load_result(ws)
            if loaded is not None:
                ctx.result = loaded
                ctx.media = loaded.media
                ctx.transcripts = loaded.transcript_segments
                ctx.speaker_turns = loaded.speaker_turns
                ctx.speech_segments = loaded.speech_segments
                ctx.board_segments = loaded.board_segments
                ctx.speakers = dict(loaded.speakers)

    def _stage_media(self, ctx: _RunContext) -> list[str]:
        state = ctx.workspace.load_state()
        source = Path(state.source_path)
        media = self.deps.media_processor.inspect(source)
        ctx.workspace.save_media(media)
        ctx.media = media
        artifacts = ["media.json"]

        if media.has_audio:
            wav = ctx.workspace.audio_wav_path()
            self.deps.media_processor.extract_wav(source, wav)
            artifacts.append(str(wav.relative_to(ctx.workspace.job_dir)).replace("\\", "/"))
        return artifacts

    def _stage_transcript(self, ctx: _RunContext) -> list[str]:
        media = _require_media(ctx)
        artifact_dir = ctx.workspace.job_dir / REL_AUDIO_ARTIFACTS
        artifact_dir.mkdir(parents=True, exist_ok=True)
        out = artifact_dir / "transcript.json"

        if not media.has_audio:
            ctx.transcripts = []
            _write_json_list(out, [])
            return [REL_TRANSCRIPT]

        recognizer = self.deps.recognizer
        if recognizer is None:
            raise RuntimeError("未配置语音识别适配器（SpeechRecognizer）")
        wav = ctx.workspace.audio_wav_path()
        if not wav.exists():
            raise FileNotFoundError(f"缺少音频文件: {wav}")
        ctx.transcripts = list(recognizer.transcribe(wav, artifact_dir))
        return [REL_TRANSCRIPT]

    def _stage_diarization(self, ctx: _RunContext) -> list[str]:
        media = _require_media(ctx)
        artifact_dir = ctx.workspace.job_dir / REL_AUDIO_ARTIFACTS
        artifact_dir.mkdir(parents=True, exist_ok=True)
        out = artifact_dir / "speaker_turns.json"

        if not media.has_audio:
            ctx.speaker_turns = []
            _write_json_list(out, [])
            return [REL_SPEAKER_TURNS]

        diarizer = self.deps.diarizer
        if diarizer is None:
            raise RuntimeError("未配置说话人分离适配器（SpeakerDiarizer）")
        wav = ctx.workspace.audio_wav_path()
        if not wav.exists():
            raise FileNotFoundError(f"缺少音频文件: {wav}")
        ctx.speaker_turns = list(diarizer.diarize(wav, artifact_dir))
        return [REL_SPEAKER_TURNS]

    def _stage_alignment(self, ctx: _RunContext) -> list[str]:
        artifact_dir = ctx.workspace.job_dir / REL_AUDIO_ARTIFACTS
        artifact_dir.mkdir(parents=True, exist_ok=True)
        speaker_names = _speaker_names_from_config(ctx.config)

        if ctx.transcripts is None:
            ctx.transcripts = _load_model_list(
                ctx.workspace.job_dir / REL_TRANSCRIPT,
                TranscriptSegment,
            )
        if ctx.speaker_turns is None:
            ctx.speaker_turns = _load_model_list(
                ctx.workspace.job_dir / REL_SPEAKER_TURNS,
                SpeakerTurn,
            )

        alignment_config = AlignmentConfig()
        aligned = align_speech_with_diagnostics(
            ctx.transcripts,
            ctx.speaker_turns,
            config=alignment_config,
            speaker_names=speaker_names or None,
        )
        write_alignment_artifact(artifact_dir, aligned, config=alignment_config)
        ctx.speech_segments = list(aligned.segments)
        ctx.speakers = dict(speaker_names)
        # Ensure speakers map covers observed ids even without explicit names.
        for seg in ctx.speech_segments:
            ctx.speakers.setdefault(seg.speaker_id, seg.speaker_name or seg.speaker_id)
        return [REL_ALIGNMENT]

    def _stage_board_detect(self, ctx: _RunContext) -> list[str]:
        media = _require_media(ctx)
        frames_dir = ctx.workspace.frames_dir
        frames_dir.mkdir(parents=True, exist_ok=True)
        requested_interval_ms = int(ctx.config.get("interval_ms", 5000))
        max_frames = int(ctx.config.get("max_frames", 800))
        if requested_interval_ms <= 0 or max_frames <= 0:
            raise ValueError("interval_ms and max_frames must be > 0")
        interval_ms = max(
            requested_interval_ms,
            math.ceil(media.duration_ms / max_frames),
        )

        if not media.has_video:
            manifest = {"mode": "none", "interval_ms": interval_ms, "frames": []}
            path = ctx.workspace.job_dir / REL_FRAME_MANIFEST
            atomic_write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            ctx.frame_paths = []
            ctx.frame_timestamps_ms = []
            ctx.frame_interval_ms = interval_ms
            return [REL_FRAME_MANIFEST]

        # Existing preview frames are kept as a backward-compatible/resume path.
        # The default complete-v1 profile intentionally uses the 01 fixed path.
        existing_preview_frames = sorted(frames_dir.glob("preview-*.jpg"))
        use_adaptive = ctx.config.get("sampling_mode", "fixed") == "adaptive"
        use_adaptive = use_adaptive and not existing_preview_frames
        if use_adaptive:
            from course_video_analyzer.vision.adaptive_sampling import (
                AdaptiveSamplingConfig,
                estimated_total_frames,
                sample_video_adaptively,
            )

            state = ctx.workspace.load_state()
            source_path = Path(state.source_path)
            adaptive_config = AdaptiveSamplingConfig(
                initial_stride_ms=int(
                    ctx.config.get("adaptive_initial_stride_ms", max(60_000, interval_ms))
                ),
                min_interval_ms=int(ctx.config.get("adaptive_min_interval_ms", 1_000)),
                max_recursion_depth=int(
                    ctx.config.get("adaptive_max_recursion_depth", 8)
                ),
                max_no_text_span_ms=int(
                    ctx.config.get("adaptive_max_no_text_span_ms", 8_000)
                ),
                text_presence_threshold=float(
                    ctx.config.get("adaptive_text_presence_threshold", 0.42)
                ),
                text_min_components=int(ctx.config.get("adaptive_text_min_components", 3)),
                text_similarity_threshold=float(
                    ctx.config.get("adaptive_text_similarity_threshold", 0.55)
                ),
                no_text_similarity_threshold=float(
                    ctx.config.get("adaptive_no_text_similarity_threshold", 0.94)
                ),
                image_difference_threshold=float(
                    ctx.config.get("adaptive_image_difference_threshold", 0.45)
                ),
                ocr_text_similarity_threshold=float(
                    ctx.config.get("adaptive_ocr_text_similarity_threshold", 0.88)
                ),
                ocr_presence_min_confidence=float(
                    ctx.config.get("adaptive_ocr_presence_min_confidence", 0.20)
                ),
                ocr_presence_min_lines=int(
                    ctx.config.get("adaptive_ocr_presence_min_lines", 2)
                ),
                representative_sample_count=int(
                    ctx.config.get("adaptive_representative_sample_count", 5)
                ),
                content_region_padding_ratio=float(
                    ctx.config.get("adaptive_content_region_padding_ratio", 0.08)
                ),
                disk_cache_enabled=bool(ctx.config.get("adaptive_disk_cache_enabled", True)),
                memory_frame_cache_size=int(
                    ctx.config.get("adaptive_memory_frame_cache_size", 8)
                ),
                max_detected_frames=int(
                    ctx.config.get("adaptive_max_detected_frames", max(2_000, max_frames))
                ),
            )
            total_frames = estimated_total_frames(media.duration_ms, media.fps)
            ocr_provider = None
            if self.deps.board_ocr is not None:
                from course_video_analyzer.vision.frame_ocr import (
                    CachedBoardFrameOcrProvider,
                )

                ocr_provider = CachedBoardFrameOcrProvider(
                    self.deps.board_ocr,
                    probe_dir=frames_dir / "_ocr_probes",
                    artifact_dir=ctx.workspace.job_dir
                    / REL_BOARD_ARTIFACTS
                    / "_adaptive_ocr_cache",
                    min_confidence=adaptive_config.ocr_presence_min_confidence,
                    min_lines=adaptive_config.ocr_presence_min_lines,
                    region_padding_ratio=adaptive_config.content_region_padding_ratio,
                )
            cache_dir = Path(
                ctx.config.get(
                    "adaptive_cache_dir",
                    ctx.workspace.job_dir.parent
                    / "_video_cache"
                    / _video_cache_key(source_path),
                )
            )
            result = sample_video_adaptively(
                source_path,
                frames_dir,
                duration_ms=media.duration_ms,
                total_frames=total_frames,
                fps=media.fps,
                config=adaptive_config,
                ocr_provider=ocr_provider,
                cache_dir=cache_dir,
            )
            ctx.frame_paths = result.representative_paths
            ctx.frame_timestamps_ms = [
                item.representative_timestamp_ms for item in result.intervals
            ]
            ctx.frame_interval_ms = None
            ctx.frame_ocr_cache = {
                item.frame_index: [
                    OcrLine.model_validate(line) for line in item.ocr_result.text_lines
                ]
                for item in result.observations
                if item.ocr_result is not None
            }
            for item in result.intervals:
                ctx.frame_ocr_cache[item.representative_frame_index] = [
                    OcrLine.model_validate(line) for line in item.combined_ocr_lines
                ]
            sampling_stats = asdict(result.stats)
            sampling_stats["extracted_frame_count"] = result.stats.actual_detected_frames
            manifest = {
                "mode": "adaptive",
                "cache_dir": str(cache_dir),
                "stats": sampling_stats,
                "intervals": [
                    {
                        "start_ms": item.start_ms,
                        "end_ms": item.end_ms,
                        "representative_timestamp_ms": item.representative_timestamp_ms,
                        "representative_frame_index": item.representative_frame_index,
                        "representative_path": str(
                            item.representative_path.relative_to(ctx.workspace.job_dir)
                        ).replace("\\", "/"),
                        "detected_timestamps_ms": item.detected_timestamps_ms,
                        "text_score": item.text_score,
                        "stability_score": item.stability_score,
                        "combined_ocr_lines": item.combined_ocr_lines,
                    }
                    for item in result.intervals
                ],
                "ocr_cache": [
                    {
                        "frame_index": item.frame_index,
                        "timestamp_ms": item.timestamp_ms,
                        "has_text": item.ocr_result.has_text,
                        "text": item.ocr_result.text,
                        "text_lines": item.ocr_result.text_lines,
                        "content_region": item.ocr_result.content_region,
                    }
                    for item in result.observations
                    if item.ocr_result is not None
                ],
                "frames": [
                    {
                        "index": item.representative_frame_index,
                        "timestamp_ms": item.representative_timestamp_ms,
                        "path": str(item.representative_path.relative_to(ctx.workspace.job_dir)).replace(
                            "\\", "/"
                        ),
                    }
                    for item in result.intervals
                ],
            }
            path = ctx.workspace.job_dir / REL_FRAME_MANIFEST
            atomic_write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            return [REL_FRAME_MANIFEST]

        from course_video_analyzer.media.frames import extract_preview_frames

        state = ctx.workspace.load_state()
        frame_paths = extract_preview_frames(
            Path(state.source_path),
            frames_dir,
            media=media,
            interval_ms=interval_ms,
            max_frames=max_frames,
        )
        ctx.frame_paths = list(frame_paths)
        ctx.frame_timestamps_ms = [index * interval_ms for index in range(len(frame_paths))]
        ctx.frame_interval_ms = interval_ms
        manifest = {
            "mode": "fixed",
            "interval_ms": interval_ms,
            "requested_interval_ms": requested_interval_ms,
            "max_frames": max_frames,
            "frames": [
                {
                    "index": index,
                    "timestamp_ms": index * interval_ms,
                    "path": str(path.relative_to(ctx.workspace.job_dir)).replace("\\", "/"),
                }
                for index, path in enumerate(frame_paths)
            ],
        }
        path = ctx.workspace.job_dir / REL_FRAME_MANIFEST
        atomic_write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        return [REL_FRAME_MANIFEST]

    def _stage_board_track(self, ctx: _RunContext) -> list[str]:
        media = _require_media(ctx)
        out_dir = ctx.workspace.job_dir / REL_BOARD_ARTIFACTS
        out_dir.mkdir(parents=True, exist_ok=True)
        segments_path = ctx.workspace.job_dir / REL_BOARD_SEGMENTS

        if not media.has_video:
            ctx.board_segments = []
            _write_json_list(segments_path, [])
            return [REL_BOARD_SEGMENTS]

        tracker = self.deps.board_tracker
        if tracker is None:
            raise RuntimeError("未配置课板跟踪适配器（BoardTracker）")

        samples = self._resolve_frame_samples(ctx)
        tracking = tracker.track(samples, output_dir=out_dir)
        segments = list(getattr(tracking, "segments", tracking))
        ctx.board_segments = segments
        _write_json_list(segments_path, segments)
        return [REL_BOARD_SEGMENTS]

    def _stage_board_ocr(self, ctx: _RunContext) -> list[str]:
        segments_path = ctx.workspace.job_dir / REL_BOARD_SEGMENTS
        if ctx.board_segments is None:
            ctx.board_segments = _load_model_list(segments_path, BoardSegment)

        if not ctx.board_segments:
            _write_json_list(segments_path, [])
            self._record_actual_ocr_count(ctx, 0)
            self._record_final_image_count(ctx, 0)
            adaptive_result_path = self._write_adaptive_ocr_results(ctx)
            return [
                item
                for item in (REL_BOARD_SEGMENTS, adaptive_result_path)
                if item is not None
            ]

        ocr = self.deps.board_ocr
        if ocr is None:
            raise RuntimeError("未配置课板 OCR 适配器（BoardOcr）")

        updated: list[BoardSegment] = []
        artifact_paths = [REL_BOARD_SEGMENTS]
        frame_ocr_cache = self._resolve_frame_ocr_cache(ctx)
        downstream_ocr_calls = 0
        downstream_cache_hits = 0
        for index, segment in enumerate(ctx.board_segments):
            version = segment.version_id or f"board_{index:04d}"
            ocr_dir = ctx.workspace.job_dir / REL_BOARD_ARTIFACTS / version
            ocr_dir.mkdir(parents=True, exist_ok=True)
            cached_lines = (
                frame_ocr_cache.get(segment.representative_frame_index)
                if segment.representative_frame_index is not None
                else None
            )
            if cached_lines is not None:
                lines = list(cached_lines)
                downstream_cache_hits += 1
                _write_reused_ocr_artifacts(ocr_dir, lines, segment)
            else:
                lines = list(ocr.recognize(Path(segment.image_path), ocr_dir))
                downstream_ocr_calls += 1
            updated.append(segment.model_copy(update={"text_lines": lines, "version_id": version}))
            rel = f"{REL_BOARD_ARTIFACTS}/{version}"
            artifact_paths.append(rel)

        ctx.board_segments = updated
        if bool(
            ctx.config.get(
                "ocr_dedup_enabled",
                ctx.config.get("adaptive_ocr_dedup", True),
            )
        ):
            from course_video_analyzer.vision.ocr_dedup import (
                OcrDedupConfig,
                deduplicate_ocr_board_segments,
            )

            ctx.board_segments = deduplicate_ocr_board_segments(
                ctx.board_segments,
                config=OcrDedupConfig(
                    text_similarity_threshold=float(
                        ctx.config.get(
                            "ocr_text_similarity_threshold",
                            ctx.config.get("adaptive_ocr_text_similarity_threshold", 0.92),
                        )
                    ),
                    image_supported_text_threshold=float(
                        ctx.config.get(
                            "ocr_image_text_similarity_threshold",
                            ctx.config.get(
                                "adaptive_ocr_image_text_similarity_threshold",
                                0.75,
                            ),
                        )
                    ),
                ),
            )
        _write_json_list(segments_path, ctx.board_segments)
        self._record_actual_ocr_count(
            ctx,
            downstream_ocr_calls,
            downstream_cache_hits=downstream_cache_hits,
        )
        self._record_final_image_count(ctx, len(ctx.board_segments))
        adaptive_result_path = self._write_adaptive_ocr_results(ctx)
        if adaptive_result_path is not None:
            artifact_paths.append(adaptive_result_path)
        # unique preserve order
        seen: set[str] = set()
        ordered: list[str] = []
        for item in artifact_paths:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

    def _stage_merge(self, ctx: _RunContext) -> list[str]:
        media = _require_media(ctx)
        if ctx.transcripts is None:
            ctx.transcripts = _load_model_list(
                ctx.workspace.job_dir / REL_TRANSCRIPT,
                TranscriptSegment,
            )
        if ctx.speaker_turns is None:
            ctx.speaker_turns = _load_model_list(
                ctx.workspace.job_dir / REL_SPEAKER_TURNS,
                SpeakerTurn,
            )
        if ctx.speech_segments is None:
            ctx.speech_segments = _load_speech_from_alignment(
                ctx.workspace.job_dir / REL_ALIGNMENT
            )
        if ctx.board_segments is None:
            ctx.board_segments = _load_model_list(
                ctx.workspace.job_dir / REL_BOARD_SEGMENTS,
                BoardSegment,
            )

        timeline = merge_timeline(ctx.speech_segments, ctx.board_segments)
        speakers: dict[str, str] = dict(ctx.speakers)
        if not speakers:
            speakers = _speaker_names_from_config(ctx.config)
            for seg in ctx.speech_segments:
                speakers.setdefault(seg.speaker_id, seg.speaker_name or seg.speaker_id)

        result = AnalysisResult(
            media=media,
            speakers=speakers,
            transcript_segments=list(ctx.transcripts),
            speaker_turns=list(ctx.speaker_turns),
            speech_segments=list(ctx.speech_segments),
            board_segments=list(ctx.board_segments),
            timeline=timeline,
            diagnostics={
                "stages": [s.value for s in PIPELINE_STAGES],
                "speech_count": len(ctx.speech_segments),
                "board_count": len(ctx.board_segments),
                "timeline_count": len(timeline),
            },
        )
        ctx.result = sort_analysis_result(result)
        # Persist a merge snapshot early so resume after merge can hydrate.
        export_analysis_json(ctx.result, ctx.workspace.job_dir / REL_ANALYSIS)
        export_timeline_json(ctx.result.timeline, ctx.workspace.job_dir / REL_TIMELINE)
        return [REL_ANALYSIS, REL_TIMELINE]

    def _stage_export(self, ctx: _RunContext) -> list[str]:
        if ctx.result is None:
            loaded = self.load_result(ctx.workspace)
            if loaded is None:
                raise RuntimeError("EXPORT 阶段缺少 AnalysisResult，请先完成 MERGE")
            ctx.result = loaded

        result = sort_analysis_result(ctx.result)
        job_dir = ctx.workspace.job_dir
        export_analysis_json(result, job_dir / REL_ANALYSIS)
        export_timeline_json(result.timeline, job_dir / REL_TIMELINE)
        export_txt(result, job_dir / REL_TXT)
        export_srt(result, job_dir / REL_SRT)
        export_boards_index(result, job_dir / REL_BOARDS_INDEX)
        ctx.result = result
        return [REL_ANALYSIS, REL_TIMELINE, REL_TXT, REL_SRT, REL_BOARDS_INDEX]

    def _resolve_frame_samples(self, ctx: _RunContext) -> list[Any]:
        if ctx.frame_paths is not None:
            cached_timestamps = ctx.frame_timestamps_ms
            if cached_timestamps is None:
                interval_ms = ctx.frame_interval_ms or int(ctx.config.get("interval_ms", 5000))
                cached_timestamps = [
                    _timestamp_from_frame_path(path, index, interval_ms)
                    for index, path in enumerate(ctx.frame_paths)
                ]
            return _build_frame_samples(ctx.frame_paths, timestamps_ms=cached_timestamps)

        manifest_path = ctx.workspace.job_dir / REL_FRAME_MANIFEST
        if manifest_path.exists():
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            interval_ms = int(payload.get("interval_ms", 5000))
            frames: list[Path] = []
            timestamps: list[int] = []
            for row in payload.get("frames") or []:
                rel = row.get("path")
                if rel:
                    frames.append(ctx.workspace.job_dir / str(rel))
                    timestamps.append(
                        int(
                            row.get(
                                "timestamp_ms",
                                _timestamp_from_frame_path(frames[-1], len(frames) - 1, interval_ms),
                            )
                        )
                    )
            return _build_frame_samples(frames, timestamps_ms=timestamps)

        interval_ms = int(ctx.config.get("interval_ms", 5000))
        frames = sorted(ctx.workspace.frames_dir.glob("preview-*.jpg"))
        return _build_frame_samples(frames, interval_ms=interval_ms)

    @staticmethod
    def _record_actual_ocr_count(
        ctx: _RunContext,
        count: int,
        *,
        downstream_cache_hits: int = 0,
    ) -> None:
        manifest_path = ctx.workspace.job_dir / REL_FRAME_MANIFEST
        if not manifest_path.exists():
            return
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        stats = payload.setdefault("stats", {})
        sampling_calls = int(stats.get("full_ocr_count", 0))
        stats["downstream_full_ocr_count"] = count
        stats["downstream_ocr_cache_hit_count"] = downstream_cache_hits
        stats["actual_full_ocr_count"] = sampling_calls + count
        atomic_write_text(
            manifest_path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )

    @staticmethod
    def _resolve_frame_ocr_cache(ctx: _RunContext) -> dict[int, list[OcrLine]]:
        if ctx.frame_ocr_cache is not None:
            return ctx.frame_ocr_cache
        manifest_path = ctx.workspace.job_dir / REL_FRAME_MANIFEST
        if not manifest_path.exists():
            return {}
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        cache: dict[int, list[OcrLine]] = {}
        for row in payload.get("ocr_cache") or []:
            frame_index = row.get("frame_index")
            if frame_index is None:
                continue
            cache[int(frame_index)] = [
                OcrLine.model_validate(line) for line in row.get("text_lines") or []
            ]
        for interval in payload.get("intervals") or []:
            frame_index = interval.get("representative_frame_index")
            if frame_index is None:
                continue
            combined = interval.get("combined_ocr_lines") or []
            if combined:
                cache[int(frame_index)] = [OcrLine.model_validate(line) for line in combined]
        ctx.frame_ocr_cache = cache
        return cache

    @staticmethod
    def _record_final_image_count(ctx: _RunContext, count: int) -> None:
        manifest_path = ctx.workspace.job_dir / REL_FRAME_MANIFEST
        if not manifest_path.exists():
            return
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        stats = payload.setdefault("stats", {})
        stats["final_image_count_after_ocr_dedup"] = count
        atomic_write_text(
            manifest_path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )

    @staticmethod
    def _write_adaptive_ocr_results(ctx: _RunContext) -> str | None:
        manifest_path = ctx.workspace.job_dir / REL_FRAME_MANIFEST
        if not manifest_path.exists() or ctx.board_segments is None:
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("mode") != "adaptive":
            return None
        intervals = list(manifest.get("intervals") or [])
        rows: list[dict[str, Any]] = []
        for segment in ctx.board_segments:
            matching = [
                item
                for item in intervals
                if segment.start_ms
                <= int(item.get("representative_timestamp_ms", -1))
                < segment.end_ms
            ]
            if not matching and intervals:
                matching = [
                    min(
                        intervals,
                        key=lambda item: abs(
                            int(item.get("representative_timestamp_ms", 0)) - segment.start_ms
                        ),
                    )
                ]
            rows.append(
                {
                    "version_id": segment.version_id,
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "board_image_path": str(segment.image_path),
                    "source_intervals": matching,
                    "ocr_lines": [line.model_dump(mode="json") for line in segment.text_lines],
                }
            )
        output_path = ctx.workspace.job_dir / REL_ADAPTIVE_RESULTS
        atomic_write_text(
            output_path,
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        )
        return REL_ADAPTIVE_RESULTS


@dataclass
class _RunContext:
    workspace: JobWorkspace
    config: dict[str, Any]
    media: MediaInfo | None = None
    transcripts: list[TranscriptSegment] | None = None
    speaker_turns: list[SpeakerTurn] | None = None
    speech_segments: list[SpeechSegment] | None = None
    board_segments: list[BoardSegment] | None = None
    speakers: dict[str, str] = field(default_factory=dict)
    frame_paths: list[Path] | None = None
    frame_timestamps_ms: list[int] | None = None
    frame_ocr_cache: dict[int, list[OcrLine]] | None = None
    frame_interval_ms: int | None = None
    result: AnalysisResult | None = None


def create_default_analysis_service(
    config: dict[str, Any] | None = None,
) -> AnalysisService:
    """Build a production service with lazily imported real adapters."""
    _ = config  # reserved for future device / model overrides
    media = _load_default_media_processor()
    recognizer = _load_default_recognizer()
    diarizer = _load_default_diarizer()
    tracker = _load_default_board_tracker()
    ocr = _load_default_board_ocr()
    return AnalysisService.from_dependencies(
        media_processor=media,
        recognizer=recognizer,
        diarizer=diarizer,
        board_tracker=tracker,
        board_ocr=ocr,
    )


def _load_default_media_processor() -> MediaProcessor:
    try:
        from course_video_analyzer.media.ffmpeg import FFmpegMediaProcessor
    except ImportError as exc:  # pragma: no cover - std lib always present
        raise RuntimeError(f"无法加载媒体处理器: {exc}") from exc
    return FFmpegMediaProcessor()


def _load_default_recognizer() -> SpeechRecognizer:
    try:
        from course_video_analyzer.audio.funasr_adapter import FunASRAdapter
    except ImportError as exc:
        raise RuntimeError(
            "未安装 FunASR 音频依赖。请执行 `uv sync --extra audio` 后重试。"
        ) from exc
    return FunASRAdapter()


def _load_default_diarizer() -> SpeakerDiarizer:
    try:
        from course_video_analyzer.audio.wespeaker_adapter import create_default_diarizer
    except ImportError as exc:
        raise RuntimeError(
            "未安装 WeSpeaker 音频依赖。请执行 `uv sync --extra audio` 后重试。"
        ) from exc
    return create_default_diarizer()


def _load_default_board_tracker() -> BoardTrackerProtocol:
    try:
        from course_video_analyzer.vision.tracking import BoardTracker
    except ImportError as exc:
        raise RuntimeError(
            "未安装视觉依赖。请执行 `uv sync --extra vision` 后重试。"
        ) from exc
    return BoardTracker()


def _load_default_board_ocr() -> BoardOcr:
    try:
        from course_video_analyzer.vision.ocr import PaddleBoardOcr
    except ImportError as exc:
        raise RuntimeError(
            "未安装 PaddleOCR 视觉依赖。请执行 `uv sync --extra vision` 后重试。"
        ) from exc
    return PaddleBoardOcr()


def _require_media(ctx: _RunContext) -> MediaInfo:
    if ctx.media is not None:
        return ctx.media
    media = ctx.workspace.load_media()
    if media is None:
        raise RuntimeError("缺少 media.json，请先完成 MEDIA 阶段")
    ctx.media = media
    return media


def _speaker_names_from_config(config: dict[str, Any]) -> dict[str, str]:
    raw = config.get("speaker_names") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def _write_json_list(path: Path, items: list[Any]) -> None:
    payload = [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in items
    ]
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _load_model_list(path: Path, model_cls: type[Any]) -> list[Any]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    return [model_cls.model_validate(item) for item in payload]


def _load_speech_from_alignment(path: Path) -> list[SpeechSegment]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("speech_segments") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    return [SpeechSegment.model_validate(item) for item in rows]


@dataclass
class _LiteFrameSample:
    """Minimal frame sample; compatible with ``BoardTracker.track`` path-based load."""

    frame_index: int
    timestamp_ms: int
    image_path: Path | None = None
    image_bgr: Any = None


def _write_reused_ocr_artifacts(
    artifact_dir: Path,
    lines: list[OcrLine],
    segment: BoardSegment,
) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        artifact_dir / "ocr_lines.json",
        json.dumps(
            [line.model_dump(mode="json") for line in lines],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    atomic_write_text(
        artifact_dir / "board_body.txt",
        "\n".join(line.corrected_text or line.text for line in lines),
    )
    atomic_write_text(
        artifact_dir / "ocr_meta.json",
        json.dumps(
            {
                "cache_reused": True,
                "representative_frame_index": segment.representative_frame_index,
                "representative_timestamp_ms": segment.representative_timestamp_ms,
                "line_count": len(lines),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )


def _build_frame_samples(
    frame_paths: list[Path],
    interval_ms: int = 5000,
    *,
    timestamps_ms: list[int] | None = None,
) -> list[Any]:
    """Build frame samples for the board tracker without importing cv2 at module import."""
    # Prefer real FrameSample when vision extra is installed (duck-type compatible).
    sample_cls: Any = _LiteFrameSample
    try:
        from course_video_analyzer.vision.tracking import FrameSample as RealFrameSample

        sample_cls = RealFrameSample
    except ImportError:
        pass

    samples: list[Any] = []
    for index, path in enumerate(frame_paths):
        ts = (
            timestamps_ms[index]
            if timestamps_ms is not None and index < len(timestamps_ms)
            else _timestamp_from_frame_path(path, index, interval_ms)
        )
        samples.append(
            sample_cls(
                frame_index=index,
                timestamp_ms=ts,
                image_path=Path(path),
            )
        )
    return samples


_FRAME_INDEX_RE = re.compile(r"(\d+)(?:\.[^.]+)?$")


def _timestamp_from_frame_path(path: Path, index: int, interval_ms: int) -> int:
    match = _FRAME_INDEX_RE.search(path.stem)
    if match:
        # ffmpeg preview-%04d.jpg is 1-based; convert to 0-based interval index when possible.
        n = int(match.group(1))
        if n >= 1:
            return (n - 1) * interval_ms
    return index * interval_ms


def _video_cache_key(source: Path) -> str:
    resolved = Path(source).resolve()
    stat = resolved.stat()
    payload = f"{resolved}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:20]
