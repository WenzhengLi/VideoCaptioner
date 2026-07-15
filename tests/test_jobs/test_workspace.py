from pathlib import Path

from course_video_analyzer.jobs.workspace import JobWorkspace, atomic_write_text
from course_video_analyzer.models import JobStage, MediaInfo, StageStatus


def test_create_layout_and_atomic_state(tmp_path: Path) -> None:
    ws = JobWorkspace(tmp_path, job_id="demo123")
    state = ws.create(Path("lesson.mp4"), config={"interval_ms": 5000})
    assert ws.job_json.exists()
    assert ws.audio_dir.exists()
    assert state.stages[JobStage.MEDIA.value].status == StageStatus.PENDING

    media = MediaInfo(
        source_path=Path("lesson.mp4"),
        duration_ms=1000,
        width=640,
        height=360,
        fps=25,
    )
    ws.save_media(media)
    assert ws.load_media() is not None

    ws.mark_running(JobStage.MEDIA)
    ws.mark_completed(JobStage.MEDIA, artifact_paths=["media.json"])
    assert ws.should_skip(JobStage.MEDIA)

    ws.mark_failed(JobStage.TRANSCRIPT, "boom")
    failed = ws.load_state().stages[JobStage.TRANSCRIPT.value]
    assert failed.status == StageStatus.FAILED
    assert failed.error == "boom"


def test_atomic_write_replaces_file(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    atomic_write_text(path, '{"a":1}')
    atomic_write_text(path, '{"a":2}')
    assert path.read_text(encoding="utf-8") == '{"a":2}'
