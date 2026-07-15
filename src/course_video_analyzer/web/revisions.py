"""Persist speaker mappings and OCR corrections without overwriting raw OCR text."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.models import AnalysisResult, BoardSegment, OcrLine

REVISION_FILENAME = "revisions.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class OcrLineCorrection(BaseModel):
    version_id: str = Field(min_length=1)
    line_index: int = Field(ge=0)
    corrected_text: str


class JobRevision(BaseModel):
    """User edits stored beside job artifacts; never mutates raw ``text`` fields."""

    version: int = 1
    speakers: dict[str, str] = Field(default_factory=dict)
    ocr_corrections: list[OcrLineCorrection] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now_iso)


def revision_path(job_dir: Path) -> Path:
    return Path(job_dir) / REVISION_FILENAME


def load_revision(job_dir: Path) -> JobRevision:
    path = revision_path(job_dir)
    if not path.exists():
        return JobRevision()
    return JobRevision.model_validate_json(path.read_text(encoding="utf-8"))


def save_revision(job_dir: Path, revision: JobRevision) -> Path:
    revision.updated_at = utc_now_iso()
    path = revision_path(job_dir)
    atomic_write_text(path, revision.model_dump_json(indent=2) + "\n")
    return path


def merge_speaker_mapping(
    revision: JobRevision,
    mapping: dict[str, str],
) -> JobRevision:
    speakers = dict(revision.speakers)
    for key, value in mapping.items():
        speaker_id = str(key).strip()
        name = str(value).strip()
        if not speaker_id:
            continue
        if name:
            speakers[speaker_id] = name
        else:
            speakers.pop(speaker_id, None)
    return revision.model_copy(update={"speakers": speakers})


def merge_ocr_corrections(
    revision: JobRevision,
    corrections: list[OcrLineCorrection | dict[str, Any]],
) -> JobRevision:
    by_key: dict[tuple[str, int], OcrLineCorrection] = {
        (item.version_id, item.line_index): item for item in revision.ocr_corrections
    }
    for raw in corrections:
        item = (
            raw
            if isinstance(raw, OcrLineCorrection)
            else OcrLineCorrection.model_validate(raw)
        )
        text = item.corrected_text.strip()
        key = (item.version_id, item.line_index)
        if text:
            by_key[key] = item.model_copy(update={"corrected_text": text})
        else:
            by_key.pop(key, None)
    ordered = sorted(by_key.values(), key=lambda c: (c.version_id, c.line_index))
    return revision.model_copy(update={"ocr_corrections": ordered})


def apply_revision_to_result(result: AnalysisResult, revision: JobRevision) -> AnalysisResult:
    """Return a display/export copy with speaker names and ``corrected_text`` overlays."""
    speakers = dict(result.speakers)
    speakers.update(revision.speakers)

    speech = []
    for segment in result.speech_segments:
        name = speakers.get(segment.speaker_id) or segment.speaker_name
        speech.append(segment.model_copy(update={"speaker_name": name}))

    corrections = {
        (c.version_id, c.line_index): c.corrected_text for c in revision.ocr_corrections
    }
    boards: list[BoardSegment] = []
    for board in result.board_segments:
        version = board.version_id or ""
        lines: list[OcrLine] = []
        for index, line in enumerate(board.text_lines):
            corrected = corrections.get((version, index))
            if corrected is None:
                lines.append(line)
            else:
                # Keep original ``text``; only update corrected_text.
                lines.append(line.model_copy(update={"corrected_text": corrected}))
        boards.append(board.model_copy(update={"text_lines": lines}))

    # Rebuild timeline references from updated speech/boards by id/path is hard;
    # re-attach by time overlap using merger keeps consistency for export preview.
    from course_video_analyzer.timeline.merger import merge_timeline

    timeline = merge_timeline(speech, boards)
    return result.model_copy(
        update={
            "speakers": speakers,
            "speech_segments": speech,
            "board_segments": boards,
            "timeline": timeline,
        }
    )
