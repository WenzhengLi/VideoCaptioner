"""Manifest schema: paths + annotations only; media files stay outside Git."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ScenarioKind(str, Enum):
    SINGLE_SPEAKER = "single_speaker"
    TWO_SPEAKER = "two_speaker"
    MULTI_SPEAKER = "multi_speaker"
    SHORT_AFFIRMATION = "short_affirmation"
    OVERLAP_SPEECH = "overlap_speech"
    BGM_ECHO = "bgm_echo"
    BOARD_LEFT = "board_left"
    BOARD_RIGHT = "board_right"
    BOARD_SWAP = "board_swap"
    LAYOUT_SWITCH = "layout_switch"
    OCCLUSION = "occlusion"
    SLIDE_BLACKBOARD_WHITEBOARD = "slide_blackboard_whiteboard"
    END_TO_END = "end_to_end"


class TimeInterval(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def _validate(self) -> TimeInterval:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        return self


class TranscriptRef(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str


class SpeakerTurnRef(BaseModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    speaker_id: str


class BoardRegionRef(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    timestamp_ms: int | None = Field(default=None, ge=0)


class BoardPageRef(BaseModel):
    version_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = ""
    region: BoardRegionRef | None = None


class SampleAnnotations(BaseModel):
    transcript: list[TranscriptRef] = Field(default_factory=list)
    speaker_turns: list[SpeakerTurnRef] = Field(default_factory=list)
    board_regions: list[BoardRegionRef] = Field(default_factory=list)
    board_pages: list[BoardPageRef] = Field(default_factory=list)
    ocr_text: str | None = None


class BenchmarkSample(BaseModel):
    sample_id: str = Field(min_length=1)
    scenario: ScenarioKind
    description: str = ""
    # Relative to media_root or absolute; may be missing locally.
    media_path: str
    annotations_path: str | None = None
    annotations: SampleAnnotations = Field(default_factory=SampleAnnotations)
    tags: list[str] = Field(default_factory=list)
    optional: bool = True


class BenchmarkManifest(BaseModel):
    version: int = 1
    name: str = "course-video-benchmark"
    media_root: str = ""
    samples: list[BenchmarkSample] = Field(default_factory=list)
    notes: str = ""
    diarizers: list[Literal["wespeaker", "campplus"]] = Field(
        default_factory=lambda: ["wespeaker", "campplus"]
    )

    def resolve_media_path(self, sample: BenchmarkSample) -> Path:
        path = Path(sample.media_path)
        if path.is_absolute():
            return path
        if self.media_root:
            return Path(self.media_root) / path
        return path


def load_manifest(path: Path) -> BenchmarkManifest:
    return BenchmarkManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def manifest_to_dict(manifest: BenchmarkManifest) -> dict[str, Any]:
    return manifest.model_dump(mode="json")
