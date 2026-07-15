"""Deterministic completeness checks for Cursor-normalized transcript JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text

BLOCK_RE = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2}\.\d{3})\s+->\s+"
    r"(\d{2}:\d{2}:\d{2}\.\d{3})]\s+([^\r\n]+)\r?\n"
    r"(.*?)(?=\r?\n\r?\n|\Z)",
    re.MULTILINE | re.DOTALL,
)
ALLOWED_SPEAKERS = {
    "teacher_a",
    "teacher_b",
    "student",
    "chat_male",
    "chat_female",
    "unknown",
}
ALLOWED_CONTENT_TYPES = {"speech", "board_ocr", "pdf_text", "image_ocr"}


def _timestamp_ms(value: str) -> int:
    hours, minutes, seconds_ms = value.split(":")
    seconds, millis = seconds_ms.split(".")
    return (
        ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000
        + int(millis)
    )


def parse_transcript_blocks(path: Path) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    return [
        {
            "start_ms": _timestamp_ms(match.group(1)),
            "end_ms": _timestamp_ms(match.group(2)),
            "label": match.group(3).strip(),
            "text": match.group(4).strip(),
        }
        for match in BLOCK_RE.finditer(text)
    ]


def validate_p01_output(
    course_id: str,
    transcript_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source_blocks = parse_transcript_blocks(transcript_path)
    payload = json.loads(Path(output_path).read_text(encoding="utf-8"))
    segments = payload.get("segments")
    if not isinstance(segments, list):
        segments = []

    ids = [str(item.get("segment_id", "")) for item in segments if isinstance(item, dict)]
    raw_mismatches: list[int] = []
    timestamp_mismatches: list[int] = []
    invalid_speakers: list[int] = []
    invalid_content_types: list[int] = []
    empty_normalized: list[int] = []
    for index, (source, item) in enumerate(zip(source_blocks, segments, strict=False)):
        if not isinstance(item, dict):
            raw_mismatches.append(index)
            continue
        if str(item.get("raw_text", "")).strip() != source["text"]:
            raw_mismatches.append(index)
        if item.get("start_ms") != source["start_ms"] or item.get("end_ms") != source["end_ms"]:
            timestamp_mismatches.append(index)
        if item.get("speaker") not in ALLOWED_SPEAKERS:
            invalid_speakers.append(index)
        if item.get("content_type") not in ALLOWED_CONTENT_TYPES:
            invalid_content_types.append(index)
        if not str(item.get("normalized_text", "")).strip():
            empty_normalized.append(index)

    uncertainties = payload.get("uncertainties")
    uncertainty_count = len(uncertainties) if isinstance(uncertainties, list) else 0
    checks = {
        "schema_version": payload.get("schema_version") == "1.0",
        "prompt_version": payload.get("prompt_version") == "knowledge-v001-p01",
        "source_id": payload.get("source_ids") == [course_id],
        "segment_count": len(segments) == len(source_blocks) and len(source_blocks) > 0,
        "unique_segment_ids": len(ids) == len(set(ids)) and all(ids),
        "raw_text_preserved": not raw_mismatches,
        "timestamps_preserved": not timestamp_mismatches,
        "speaker_contract": not invalid_speakers,
        "content_type_contract": not invalid_content_types,
        "normalized_text_non_empty": not empty_normalized,
    }
    return {
        "schema_version": "1.0",
        "course_id": course_id,
        "stage": "P01",
        "status": "pass" if all(checks.values()) else "needs_review",
        "checks": checks,
        "metrics": {
            "input_segment_count": len(source_blocks),
            "output_segment_count": len(segments),
            "uncertainty_count": uncertainty_count,
            "uncertainty_rate": uncertainty_count / len(segments) if segments else 0.0,
            "raw_mismatch_count": len(raw_mismatches),
            "timestamp_mismatch_count": len(timestamp_mismatches),
            "invalid_speaker_count": len(invalid_speakers),
            "invalid_content_type_count": len(invalid_content_types),
            "empty_normalized_count": len(empty_normalized),
        },
        "samples": {
            "raw_mismatch_indexes": raw_mismatches[:20],
            "timestamp_mismatch_indexes": timestamp_mismatches[:20],
            "invalid_speaker_indexes": invalid_speakers[:20],
            "invalid_content_type_indexes": invalid_content_types[:20],
            "empty_normalized_indexes": empty_normalized[:20],
        },
        "note": "该报告验证结构和完整保留，不替代错字修复质量与说话人语义抽检。",
    }


def write_p01_qa(
    course_id: str,
    transcript_path: Path,
    output_path: Path,
    report_path: Path,
) -> Path:
    report = validate_p01_output(course_id, transcript_path, output_path)
    atomic_write_text(
        report_path,
        json.dumps(report, ensure_ascii=False, indent=2),
    )
    return Path(report_path)
