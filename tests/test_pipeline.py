"""Fake end-to-end pipeline tests (no real models)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from course_video_analyzer.models import (
    AnalysisResult,
    BoardRegion,
    BoardSegment,
    JobStage,
    MediaInfo,
    OcrLine,
    SpeakerTurn,
    StageStatus,
    TranscriptSegment,
)
from course_video_analyzer.pipeline import AnalysisService


@dataclass
class FakeMediaProcessor:
    media: MediaInfo
    fail_on_extract: bool = False

    def inspect(self, source: Path) -> MediaInfo:
        return self.media.model_copy(update={"source_path": Path(source).resolve()})

    def extract_wav(self, source: Path, output_wav: Path) -> Path:
        if self.fail_on_extract:
            raise RuntimeError("simulated wav extract failure")
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        output_wav.write_bytes(b"RIFF....WAVEfmt ")
        return output_wav


class FakeRecognizer:
    def __init__(self, segments: list[TranscriptSegment] | None = None) -> None:
        self.segments = segments or [
            TranscriptSegment(start_ms=1000, end_ms=2000, text="第一句", source="funasr"),
            TranscriptSegment(start_ms=3000, end_ms=4000, text="第二句", source="funasr"),
        ]
        self.calls = 0

    def transcribe(self, wav_path: Path, artifact_dir: Path) -> list[TranscriptSegment]:
        self.calls += 1
        assert wav_path.exists()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        payload = [s.model_dump(mode="json") for s in self.segments]
        (artifact_dir / "transcript.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return list(self.segments)


class FakeDiarizer:
    def __init__(self, turns: list[SpeakerTurn] | None = None) -> None:
        self.turns = turns or [
            SpeakerTurn(start_ms=0, end_ms=2500, speaker_id="spk_0", source="wespeaker"),
            SpeakerTurn(start_ms=2500, end_ms=5000, speaker_id="spk_1", source="wespeaker"),
        ]
        self.calls = 0

    def diarize(self, wav_path: Path, artifact_dir: Path) -> list[SpeakerTurn]:
        self.calls += 1
        assert wav_path.exists()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        payload = [t.model_dump(mode="json") for t in self.turns]
        (artifact_dir / "speaker_turns.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return list(self.turns)


@dataclass
class _TrackingResult:
    segments: list[BoardSegment]
    observations: list[Any]
    diagnostics: dict[str, Any]


class FakeBoardTracker:
    def __init__(self, segments: list[BoardSegment] | None = None) -> None:
        self._segments = segments
        self.calls = 0
        self.last_frames: list[Any] = []

    def track(
        self,
        frames: list[Any],
        *,
        output_dir: Path,
        initial_region: Any | None = None,
    ) -> _TrackingResult:
        self.calls += 1
        self.last_frames = list(frames)
        output_dir.mkdir(parents=True, exist_ok=True)
        if self._segments is not None:
            return _TrackingResult(segments=list(self._segments), observations=[], diagnostics={})

        if not frames:
            return _TrackingResult(segments=[], observations=[], diagnostics={})

        # One board covering full sampled span.
        first = frames[0]
        last = frames[-1]
        start_ms = int(getattr(first, "timestamp_ms", 0))
        end_ms = int(getattr(last, "timestamp_ms", 0)) + 1000
        image_path = output_dir / "v1_crop.jpg"
        image_path.write_bytes(b"fake-image")
        segment = BoardSegment(
            start_ms=start_ms,
            end_ms=max(end_ms, start_ms + 1),
            region=BoardRegion(x=0, y=0, width=200, height=100),
            image_path=image_path,
            version_id="v1",
            track_status="tracked",
            representative_frame_index=int(getattr(first, "frame_index", 0)),
            representative_timestamp_ms=start_ms,
            source="board",
        )
        return _TrackingResult(segments=[segment], observations=[], diagnostics={})


class FakeBoardOcr:
    def __init__(self) -> None:
        self.calls = 0

    def recognize(self, image_path: Path, artifact_dir: Path) -> list[OcrLine]:
        self.calls += 1
        artifact_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            OcrLine(text="课板原文", corrected_text="课板修订", confidence=0.91),
        ]
        (artifact_dir / "ocr_lines.json").write_text(
            json.dumps([line.model_dump(mode="json") for line in lines], ensure_ascii=False),
            encoding="utf-8",
        )
        return lines


class ExplodingOcr(FakeBoardOcr):
    def recognize(self, image_path: Path, artifact_dir: Path) -> list[OcrLine]:
        raise RuntimeError("ocr boom")


def _service(
    tmp_path: Path,
    *,
    has_audio: bool = True,
    has_video: bool = True,
    media_fail: bool = False,
    ocr: FakeBoardOcr | None = None,
    tracker: FakeBoardTracker | None = None,
    recognizer: FakeRecognizer | None = None,
    diarizer: FakeDiarizer | None = None,
) -> tuple[AnalysisService, MediaInfo]:
    source = tmp_path / "lesson.mp4"
    source.write_bytes(b"fake-video")
    media = MediaInfo(
        source_path=source,
        duration_ms=10_000,
        width=640,
        height=360,
        fps=25.0,
        has_audio=has_audio,
        has_video=has_video,
    )
    # Seed a couple of preview frames for board detect skip-resume paths.
    service = AnalysisService.from_dependencies(
        media_processor=FakeMediaProcessor(media, fail_on_extract=media_fail),
        recognizer=recognizer or FakeRecognizer(),
        diarizer=diarizer or FakeDiarizer(),
        board_tracker=tracker or FakeBoardTracker(),
        board_ocr=ocr or FakeBoardOcr(),
    )
    return service, media


def _seed_frames(workspace_frames: Path, n: int = 3) -> None:
    workspace_frames.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        (workspace_frames / f"preview-{i:04d}.jpg").write_bytes(b"jpg")


def test_fake_e2e_pipeline(tmp_path: Path) -> None:
    service, _media = _service(tmp_path)
    source = tmp_path / "lesson.mp4"
    jobs_root = tmp_path / "jobs"
    workspace = service.create_job(
        source,
        jobs_root,
        config={"interval_ms": 1000, "max_frames": 3, "speaker_names": {"spk_0": "导师"}},
    )
    # Avoid calling real ffmpeg: plant preview frames before BOARD_DETECT.
    # Monkeypatch extract by writing frames that extract_preview_frames would reuse.
    _seed_frames(workspace.frames_dir)

    result = service.run(workspace, resume=True)
    assert isinstance(result, AnalysisResult)
    assert len(result.speech_segments) >= 1
    assert len(result.board_segments) == 1
    assert result.board_segments[0].text_lines[0].corrected_text == "课板修订"
    assert result.timeline
    # Same board version attached to overlapping speech.
    board_versions = {
        b.version_id for entry in result.timeline for b in entry.boards if entry.speech
    }
    assert "v1" in board_versions

    analysis_path = workspace.job_dir / "artifacts" / "analysis.json"
    assert analysis_path.exists()
    reloaded = AnalysisResult.model_validate_json(analysis_path.read_text(encoding="utf-8"))
    assert reloaded.speech_segments[0].text
    assert (workspace.job_dir / "artifacts" / "transcript.txt").exists()
    assert (workspace.job_dir / "artifacts" / "transcript.srt").exists()
    assert (workspace.job_dir / "artifacts" / "boards" / "index.json").exists()
    assert (workspace.job_dir / "artifacts" / "timeline.json").exists()

    state = workspace.load_state()
    for stage in JobStage:
        assert state.stages[stage.value].status == StageStatus.COMPLETED


def test_adaptive_manifest_preserves_representative_timestamps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from course_video_analyzer.vision.adaptive_sampling import (
        AdaptiveSamplingConfig,
        AdaptiveSamplingResult,
        AdaptiveSamplingStats,
        AdaptiveTextInterval,
    )

    tracker = FakeBoardTracker()
    service, _ = _service(tmp_path, tracker=tracker)
    source = tmp_path / "lesson.mp4"
    workspace = service.create_job(source, tmp_path / "jobs", config={"adaptive_sampling": True})

    def fake_sample(source_path: Path, output_dir: Path, **kwargs: Any) -> AdaptiveSamplingResult:
        del source_path, kwargs
        paths = [output_dir / "adaptive-0001.jpg", output_dir / "adaptive-0002.jpg"]
        for path in paths:
            path.write_bytes(b"jpg")
        intervals = [
            AdaptiveTextInterval(2_000, 7_000, 3_250, 81, paths[0]),
            AdaptiveTextInterval(7_000, 9_500, 8_750, 219, paths[1]),
        ]
        stats = AdaptiveSamplingStats(
            video_duration_ms=10_000,
                video_total_frames=250,
                actual_detected_frames=9,
                image_comparison_count=12,
                full_ocr_count=2,
                ocr_request_count=5,
                ocr_cache_hit_count=3,
                disk_frame_cache_hit_count=0,
                disk_ocr_cache_hit_count=0,
                peak_memory_image_count=0,
            intro_filtered_range_ms=(0, 2_000),
            outro_filtered_range_ms=(9_500, 10_000),
            valid_interval_count=2,
            final_image_count=2,
            max_recursion_depth_reached=3,
            config=AdaptiveSamplingConfig().__dict__,
        )
        return AdaptiveSamplingResult(intervals=intervals, observations=[], stats=stats)

    monkeypatch.setattr(
        "course_video_analyzer.vision.adaptive_sampling.sample_video_adaptively",
        fake_sample,
    )
    service.run(workspace)

    assert [frame.timestamp_ms for frame in tracker.last_frames] == [3_250, 8_750]
    manifest = json.loads((workspace.frames_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "adaptive"
    assert [row["timestamp_ms"] for row in manifest["frames"]] == [3_250, 8_750]
    assert manifest["stats"]["actual_detected_frames"] == 9
    assert manifest["stats"]["actual_full_ocr_count"] == 3
    adaptive_rows = json.loads(
        (workspace.job_dir / "artifacts" / "boards" / "adaptive_results.json").read_text(
            encoding="utf-8"
        )
    )
    assert adaptive_rows[0]["ocr_lines"]
    assert adaptive_rows[0]["source_intervals"][0]["representative_frame_index"] == 81


def test_adaptive_pipeline_reuses_source_frame_ocr_cache(tmp_path: Path) -> None:
    ocr = FakeBoardOcr()
    tracker = FakeBoardTracker()
    service, _ = _service(tmp_path, ocr=ocr, tracker=tracker)
    source = tmp_path / "lesson.mp4"
    writer = cv2.VideoWriter(
        str(source),
        getattr(cv2, "VideoWriter_fourcc")(*"mp4v"),
        5.0,
        (320, 180),
    )
    assert writer.isOpened()
    frame = np.full((180, 320, 3), 240, dtype=np.uint8)
    cv2.putText(frame, "BOARD TEXT", (30, 95), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    for _ in range(55):
        writer.write(frame)
    writer.release()

    workspace = service.create_job(
        source,
        tmp_path / "jobs",
        config={
            "adaptive_sampling": True,
            "adaptive_initial_stride_ms": 30_000,
            "adaptive_ocr_presence_min_lines": 1,
        },
    )
    service.run(workspace)

    manifest = json.loads((workspace.frames_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["stats"]["full_ocr_count"] == 2
    assert manifest["stats"]["downstream_full_ocr_count"] == 0
    assert manifest["stats"]["downstream_ocr_cache_hit_count"] == 1
    assert manifest["stats"]["actual_full_ocr_count"] == 2
    assert ocr.calls == 2
    reused_meta = workspace.job_dir / "artifacts" / "boards" / "v1" / "ocr_meta.json"
    assert json.loads(reused_meta.read_text(encoding="utf-8"))["cache_reused"] is True


def test_resume_after_mid_failure(tmp_path: Path) -> None:
    exploding = ExplodingOcr()
    service, _ = _service(tmp_path, ocr=exploding)
    source = tmp_path / "lesson.mp4"
    workspace = service.create_job(source, tmp_path / "jobs", config={"interval_ms": 1000})
    _seed_frames(workspace.frames_dir)

    with pytest.raises(RuntimeError, match="ocr boom"):
        service.run(workspace, resume=True)

    state = workspace.load_state()
    assert state.stages[JobStage.BOARD_OCR.value].status == StageStatus.FAILED
    assert state.stages[JobStage.BOARD_OCR.value].error == "ocr boom"
    assert state.stages[JobStage.ALIGNMENT.value].status == StageStatus.COMPLETED
    assert state.stages[JobStage.BOARD_TRACK.value].status == StageStatus.COMPLETED

    # Swap in healthy OCR and resume.
    healthy = FakeBoardOcr()
    service.deps.board_ocr = healthy
    result = service.run(workspace, resume=True)
    assert healthy.calls >= 1
    assert result.board_segments[0].text_lines
    assert workspace.load_state().stages[JobStage.EXPORT.value].status == StageStatus.COMPLETED


def test_no_audio_still_exports_boards(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, has_audio=False)
    source = tmp_path / "lesson.mp4"
    workspace = service.create_job(source, tmp_path / "jobs", config={"interval_ms": 1000})
    _seed_frames(workspace.frames_dir)
    result = service.run(workspace)
    assert result.speech_segments == []
    assert result.transcript_segments == []
    assert len(result.board_segments) == 1
    assert result.timeline
    assert all(not entry.speech for entry in result.timeline)
    loaded = service.load_result(workspace)
    assert loaded is not None
    assert loaded.speech_segments == []


def test_no_video_still_exports_speech(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, has_video=False)
    source = tmp_path / "lesson.mp4"
    workspace = service.create_job(source, tmp_path / "jobs")
    result = service.run(workspace)
    assert result.board_segments == []
    assert len(result.speech_segments) >= 1
    assert all(e.boards == [] for e in result.timeline if e.speech)


def test_skip_completed_stages_on_resume(tmp_path: Path) -> None:
    recognizer = FakeRecognizer()
    diarizer = FakeDiarizer()
    tracker = FakeBoardTracker()
    service, _ = _service(
        tmp_path,
        recognizer=recognizer,
        diarizer=diarizer,
        tracker=tracker,
    )
    source = tmp_path / "lesson.mp4"
    workspace = service.create_job(source, tmp_path / "jobs", config={"interval_ms": 1000})
    _seed_frames(workspace.frames_dir)
    service.run(workspace)
    first_calls = (recognizer.calls, diarizer.calls, tracker.calls)

    service.run(workspace, resume=True)
    assert (recognizer.calls, diarizer.calls, tracker.calls) == first_calls
