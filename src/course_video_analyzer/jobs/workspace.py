"""Recoverable per-job workspace with atomic JSON writes."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_video_analyzer.models import JobStage, JobState, MediaInfo, StageState, StageStatus


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(content, encoding=encoding)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


class JobWorkspace:
    """Create and manage ``jobs/<job-id>/`` layouts."""

    def __init__(self, root: Path, job_id: str | None = None) -> None:
        self.root = Path(root)
        self.job_id = job_id or uuid.uuid4().hex[:12]
        self.job_dir = self.root / self.job_id
        self.audio_dir = self.job_dir / "audio"
        self.frames_dir = self.job_dir / "frames"
        self.artifacts_dir = self.job_dir / "artifacts"
        self.logs_dir = self.job_dir / "logs"
        self.job_json = self.job_dir / "job.json"
        self.media_json = self.job_dir / "media.json"

    def ensure_layout(self) -> None:
        for path in (
            self.job_dir,
            self.audio_dir,
            self.frames_dir,
            self.artifacts_dir,
            self.logs_dir,
            self.artifacts_dir / "audio",
            self.artifacts_dir / "boards",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def create(self, source_path: Path, config: dict[str, Any] | None = None) -> JobState:
        self.ensure_layout()
        now = utc_now_iso()
        stages = {
            stage.value: StageState(stage=stage, status=StageStatus.PENDING)
            for stage in JobStage
        }
        state = JobState(
            job_id=self.job_id,
            source_path=Path(source_path).resolve(),
            workspace=self.job_dir.resolve(),
            stages=stages,
            created_at=now,
            updated_at=now,
            config=config or {},
        )
        self.save_state(state)
        return state

    def load_state(self) -> JobState:
        if not self.job_json.exists():
            raise FileNotFoundError(f"任务状态不存在: {self.job_json}")
        return JobState.model_validate_json(self.job_json.read_text(encoding="utf-8"))

    def save_state(self, state: JobState) -> None:
        state.updated_at = utc_now_iso()
        atomic_write_text(self.job_json, state.model_dump_json(indent=2))

    def save_media(self, media: MediaInfo) -> None:
        atomic_write_text(self.media_json, media.model_dump_json(indent=2))

    def load_media(self) -> MediaInfo | None:
        if not self.media_json.exists():
            return None
        return MediaInfo.model_validate_json(self.media_json.read_text(encoding="utf-8"))

    def mark_running(self, stage: JobStage) -> JobState:
        state = self.load_state()
        stage_state = state.stages[stage.value]
        stage_state.status = StageStatus.RUNNING
        stage_state.error = None
        stage_state.started_at = utc_now_iso()
        self.save_state(state)
        return state

    def mark_completed(
        self,
        stage: JobStage,
        *,
        artifact_paths: list[str] | None = None,
    ) -> JobState:
        state = self.load_state()
        stage_state = state.stages[stage.value]
        stage_state.status = StageStatus.COMPLETED
        stage_state.error = None
        stage_state.finished_at = utc_now_iso()
        if artifact_paths is not None:
            stage_state.artifact_paths = artifact_paths
        self.save_state(state)
        return state

    def mark_failed(self, stage: JobStage, error: str) -> JobState:
        state = self.load_state()
        stage_state = state.stages[stage.value]
        stage_state.status = StageStatus.FAILED
        stage_state.error = error
        stage_state.finished_at = utc_now_iso()
        self.save_state(state)
        return state

    def is_completed(self, stage: JobStage) -> bool:
        state = self.load_state()
        return state.stages[stage.value].status == StageStatus.COMPLETED

    def should_skip(self, stage: JobStage) -> bool:
        return self.is_completed(stage)

    def write_json(self, relative_path: str, payload: Any) -> Path:
        path = self.job_dir / relative_path
        if hasattr(payload, "model_dump_json"):
            content = payload.model_dump_json(indent=2)
        elif isinstance(payload, (dict, list)):
            content = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        else:
            content = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        atomic_write_text(path, content)
        return path

    def audio_wav_path(self) -> Path:
        return self.audio_dir / "audio.wav"
