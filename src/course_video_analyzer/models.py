"""Shared domain models used by audio, vision, timeline, and web layers."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TimeRange(BaseModel):
    """Half-open millisecond interval ``[start_ms, end_ms)``."""

    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> TimeRange:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


class JobStage(str, Enum):
    MEDIA = "media"
    TRANSCRIPT = "transcript"
    DIARIZATION = "diarization"
    ALIGNMENT = "alignment"
    BOARD_DETECT = "board_detect"
    BOARD_TRACK = "board_track"
    BOARD_OCR = "board_ocr"
    MERGE = "merge"
    EXPORT = "export"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class MediaInfo(BaseModel):
    source_path: Path
    duration_ms: int = Field(gt=0)
    width: int = Field(ge=0, default=0)
    height: int = Field(ge=0, default=0)
    fps: float = Field(ge=0, default=0.0)
    has_video: bool = True
    has_audio: bool = True
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None


class TranscriptSegment(TimeRange):
    """FunASR raw text interval without speaker identity."""

    text: str = Field(min_length=1)
    raw_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    words: list[dict[str, Any]] = Field(default_factory=list)
    source: Literal["funasr"] = "funasr"


class SpeakerTurn(TimeRange):
    """WeSpeaker/CAM++ raw speaker interval without transcript text."""

    speaker_id: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: Literal["wespeaker", "campplus"] = "wespeaker"


class SpeechSegment(TimeRange):
    """Aligned speaker + transcript segment ready for timeline export."""

    text: str = Field(min_length=1)
    speaker_id: str = "unknown"
    speaker_name: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    match_ratio: float | None = Field(default=None, ge=0, le=1)
    inferred: bool = False
    source: str = "aligned"


class BoardRegion(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @property
    def area(self) -> int:
        return self.width * self.height

    def as_xyxy(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.x + self.width, self.y + self.height


class BoardCandidate(BaseModel):
    region: BoardRegion
    score: float = Field(ge=0, le=1)
    area_ratio: float = Field(ge=0, le=1, default=0)
    rectangularity: float = Field(ge=0, le=1, default=0)
    text_density: float = Field(ge=0, le=1, default=0)
    stability: float = Field(ge=0, le=1, default=0)
    occlusion_ratio: float = Field(ge=0, le=1, default=0)
    frame_index: int | None = None
    timestamp_ms: int | None = Field(default=None, ge=0)
    debug: dict[str, Any] = Field(default_factory=dict)


class OcrLine(BaseModel):
    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    corrected_text: str | None = None
    bbox: list[list[float]] | None = None
    low_confidence: bool = False


class BoardSegment(TimeRange):
    region: BoardRegion
    image_path: Path
    text_lines: list[OcrLine] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    version_id: str | None = None
    track_status: Literal["tracked", "redetected", "lost"] | None = None
    page_change_reason: str | None = None
    enhanced_image_path: Path | None = None
    representative_frame_index: int | None = Field(default=None, ge=0)
    representative_timestamp_ms: int | None = Field(default=None, ge=0)
    source: str = "board"


class TimelineEntry(TimeRange):
    speech: list[SpeechSegment] = Field(default_factory=list)
    boards: list[BoardSegment] = Field(default_factory=list)


class StageState(BaseModel):
    stage: JobStage
    status: StageStatus = StageStatus.PENDING
    error: str | None = None
    artifact_paths: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None


class JobState(BaseModel):
    job_id: str
    source_path: Path
    workspace: Path
    stages: dict[str, StageState] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    config: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    media: MediaInfo
    speakers: dict[str, str] = Field(default_factory=dict)
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)
    speaker_turns: list[SpeakerTurn] = Field(default_factory=list)
    speech_segments: list[SpeechSegment] = Field(default_factory=list)
    board_segments: list[BoardSegment] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
