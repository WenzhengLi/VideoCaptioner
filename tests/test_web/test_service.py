"""Web layer unit tests with a fake AnalysisService (no Gradio server)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from course_video_analyzer.web.revisions import load_revision
from course_video_analyzer.web.service import WebAnalysisFacade, probe_dependencies
from course_video_analyzer.web.validation import VideoValidationError, validate_video_path


@dataclass
class FakeMediaProcessor:
    media: MediaInfo

    def inspect(self, source: Path) -> MediaInfo:
        return self.media.model_copy(update={"source_path": Path(source).resolve()})

    def extract_wav(self, source: Path, output_wav: Path) -> Path:
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        output_wav.write_bytes(b"RIFF....WAVEfmt ")
        return output_wav


class FakeRecognizer:
    def transcribe(self, wav_path: Path, artifact_dir: Path) -> list[TranscriptSegment]:
        segments = [
            TranscriptSegment(start_ms=1000, end_ms=2000, text="你好", source="funasr"),
        ]
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "transcript.json").write_text(
            json.dumps([s.model_dump(mode="json") for s in segments], ensure_ascii=False),
            encoding="utf-8",
        )
        return segments


class FakeDiarizer:
    def diarize(self, wav_path: Path, artifact_dir: Path) -> list[SpeakerTurn]:
        turns = [
            SpeakerTurn(start_ms=0, end_ms=3000, speaker_id="spk_0", source="wespeaker"),
        ]
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "speaker_turns.json").write_text(
            json.dumps([t.model_dump(mode="json") for t in turns], ensure_ascii=False),
            encoding="utf-8",
        )
        return turns


@dataclass
class _TrackingResult:
    segments: list[BoardSegment]
    observations: list[Any]
    diagnostics: dict[str, Any]


class FakeBoardTracker:
    def track(self, frames: list[Any], *, output_dir: Path, initial_region: Any | None = None):
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = output_dir / "v1_crop.jpg"
        image_path.write_bytes(b"img")
        segment = BoardSegment(
            start_ms=0,
            end_ms=5000,
            region=BoardRegion(x=0, y=0, width=100, height=80),
            image_path=image_path,
            version_id="v1",
            track_status="tracked",
        )
        return _TrackingResult(segments=[segment], observations=[], diagnostics={})


class FakeBoardOcr:
    def recognize(self, image_path: Path, artifact_dir: Path) -> list[OcrLine]:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return [OcrLine(text="原始课板", confidence=0.9)]


def _fake_service(tmp_path: Path) -> tuple[AnalysisService, Path]:
    source = tmp_path / "lesson.mp4"
    source.write_bytes(b"fake-video-bytes")
    media = MediaInfo(
        source_path=source,
        duration_ms=8000,
        width=640,
        height=360,
        fps=25.0,
        has_audio=True,
        has_video=True,
    )
    service = AnalysisService.from_dependencies(
        media_processor=FakeMediaProcessor(media),
        recognizer=FakeRecognizer(),
        diarizer=FakeDiarizer(),
        board_tracker=FakeBoardTracker(),
        board_ocr=FakeBoardOcr(),
    )
    return service, source


def _seed_frames(frames_dir: Path, n: int = 2) -> None:
    frames_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        (frames_dir / f"preview-{i:04d}.jpg").write_bytes(b"jpg")


def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met before timeout")


def test_validate_video_path_rejects_bad_suffix(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(VideoValidationError, match="不支持"):
        validate_video_path(path)


def test_validate_video_path_rejects_missing() -> None:
    with pytest.raises(VideoValidationError, match="不存在"):
        validate_video_path("Z:/definitely-missing/video.mp4")


def test_web_facade_fake_pipeline_and_revisions(tmp_path: Path) -> None:
    service, source = _fake_service(tmp_path)
    facade = WebAnalysisFacade(tmp_path / "jobs", analysis_service=service)

    state = facade.create_job(source, interval_ms=1000, start=False)
    workspace = facade.open_workspace(state.job_id)
    assert workspace.load_state().config["processing_profile"] == "complete-v1"
    _seed_frames(workspace.frames_dir)
    facade.start_job(state.job_id)

    _wait_until(
        lambda: facade.get_state(state.job_id).stages[JobStage.EXPORT.value].status
        == StageStatus.COMPLETED
    )

    progress = facade.format_progress(state.job_id)
    assert "export" in progress
    assert "completed" in progress

    facade.save_speaker_mapping(state.job_id, {"spk_0": "导师"})
    facade.save_ocr_corrections(
        state.job_id,
        [{"version_id": "v1", "line_index": 0, "corrected_text": "修订课后板书"}],
    )

    revision = load_revision(workspace.job_dir)
    assert revision.speakers["spk_0"] == "导师"
    assert revision.ocr_corrections[0].corrected_text == "修订课后板书"

    # Reload as if the page refreshed.
    facade2 = WebAnalysisFacade(tmp_path / "jobs", analysis_service=service)
    preview = facade2.preview_payload(state.job_id)
    assert preview["ready"] is True
    assert preview["speakers"]["spk_0"] == "导师"
    assert preview["boards"][0]["lines"][0]["text"] == "原始课板"
    assert preview["boards"][0]["lines"][0]["corrected_text"] == "修订课后板书"

    raw = AnalysisResult.model_validate_json(
        (workspace.job_dir / "artifacts" / "analysis.json").read_text(encoding="utf-8")
    )
    assert raw.board_segments[0].text_lines[0].text == "原始课板"

    bundle = facade2.download_bundle(state.job_id)
    assert bundle.analysis_json is not None and bundle.analysis_json.exists()
    assert bundle.transcript_txt is not None and bundle.transcript_txt.exists()
    assert bundle.transcript_srt is not None and bundle.transcript_srt.exists()
    assert bundle.boards_zip is not None and bundle.boards_zip.exists()

    jobs = facade2.list_jobs()
    assert any(j.job_id == state.job_id and j.status == "completed" for j in jobs)


# 测试依赖徽章横幅不崩溃
def test_dependency_banner_never_crashes() -> None:
    deps = probe_dependencies()
    assert isinstance(deps.messages, list)
    facade = WebAnalysisFacade(Path("jobs"))
    text = facade.dependency_banner()
    assert "依赖" in text


def test_build_app_smoke() -> None:
    gradio = pytest.importorskip("gradio")
    assert gradio is not None
    from course_video_analyzer.web import build_app

    app = build_app(jobs_root=Path("jobs"))
    assert app is not None
