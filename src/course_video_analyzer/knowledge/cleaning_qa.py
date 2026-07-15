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
ALLOWED_SOURCE_ROLES = {
    "instructor_explanation",
    "actual_chat",
    "student_question",
    "board",
    "pdf",
    "marketing",
    "unknown",
}
ALLOWED_EPISTEMIC_TYPES = {
    "observation",
    "instructor_claim",
    "quoted_statement",
    "model_inference",
    "unknown",
}
ALLOWED_RELEVANCE = {"core", "supporting", "boilerplate", "uncertain"}


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
    *,
    expected_prompt_version: str = "knowledge-v001-p01",
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
    changed_segment_count = 0
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
        if str(item.get("normalized_text", "")) != str(item.get("raw_text", "")):
            changed_segment_count += 1

    uncertainties = payload.get("uncertainties")
    uncertainty_count = len(uncertainties) if isinstance(uncertainties, list) else 0
    quality_metrics = payload.get("quality_metrics")
    reported_changed = (
        quality_metrics.get("changed_segment_count")
        if isinstance(quality_metrics, dict)
        else None
    )
    requires_effective_normalization = expected_prompt_version == "knowledge-v002-p01"
    checks = {
        "schema_version": payload.get("schema_version") == "1.0",
        "prompt_version": payload.get("prompt_version") == expected_prompt_version,
        "source_id": payload.get("source_ids") == [course_id],
        "segment_count": len(segments) == len(source_blocks) and len(source_blocks) > 0,
        "unique_segment_ids": len(ids) == len(set(ids)) and all(ids),
        "raw_text_preserved": not raw_mismatches,
        "timestamps_preserved": not timestamp_mismatches,
        "speaker_contract": not invalid_speakers,
        "content_type_contract": not invalid_content_types,
        "normalized_text_non_empty": not empty_normalized,
        "effective_normalization": (
            changed_segment_count > 0 if requires_effective_normalization else True
        ),
        "quality_metrics_consistent": (
            reported_changed == changed_segment_count
            if requires_effective_normalization
            else True
        ),
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
            "changed_segment_count": changed_segment_count,
            "reported_changed_segment_count": reported_changed,
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
    *,
    expected_prompt_version: str = "knowledge-v001-p01",
) -> Path:
    report = validate_p01_output(
        course_id,
        transcript_path,
        output_path,
        expected_prompt_version=expected_prompt_version,
    )
    atomic_write_text(
        report_path,
        json.dumps(report, ensure_ascii=False, indent=2),
    )
    return Path(report_path)


def validate_p02_output(
    course_id: str,
    p01_path: Path,
    output_path: Path,
    *,
    expected_prompt_version: str = "knowledge-v002-p02",
) -> dict[str, Any]:
    source = json.loads(Path(p01_path).read_text(encoding="utf-8"))
    output = json.loads(Path(output_path).read_text(encoding="utf-8"))
    source_segments = source.get("segments") if isinstance(source.get("segments"), list) else []
    output_segments = output.get("segments") if isinstance(output.get("segments"), list) else []
    preserved_fields = (
        "segment_id",
        "start_ms",
        "end_ms",
        "speaker",
        "content_type",
        "raw_text",
        "normalized_text",
        "edit_notes",
        "confidence",
    )
    preservation_mismatches: list[int] = []
    invalid_source_roles: list[int] = []
    invalid_epistemic_types: list[int] = []
    invalid_relevance: list[int] = []
    invalid_confidence: list[int] = []
    missing_reasons: list[int] = []
    for index, (before, after) in enumerate(zip(source_segments, output_segments, strict=False)):
        if not isinstance(before, dict) or not isinstance(after, dict):
            preservation_mismatches.append(index)
            continue
        if any(before.get(field) != after.get(field) for field in preserved_fields):
            preservation_mismatches.append(index)
        if after.get("source_role") not in ALLOWED_SOURCE_ROLES:
            invalid_source_roles.append(index)
        if after.get("epistemic_type") not in ALLOWED_EPISTEMIC_TYPES:
            invalid_epistemic_types.append(index)
        if after.get("relevance") not in ALLOWED_RELEVANCE:
            invalid_relevance.append(index)
        confidence = after.get("classification_confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            invalid_confidence.append(index)
        reasons = after.get("classification_reasons")
        if not isinstance(reasons, list) or not reasons:
            missing_reasons.append(index)
    checks = {
        "schema_version": output.get("schema_version") == "1.0",
        "prompt_version": output.get("prompt_version") == expected_prompt_version,
        "source_id": output.get("source_ids") == [course_id],
        "segment_count": len(source_segments) == len(output_segments) and len(source_segments) > 0,
        "p01_fields_preserved": not preservation_mismatches,
        "source_role_contract": not invalid_source_roles,
        "epistemic_type_contract": not invalid_epistemic_types,
        "relevance_contract": not invalid_relevance,
        "classification_confidence_contract": not invalid_confidence,
        "classification_reasons_present": not missing_reasons,
    }
    return {
        "schema_version": "1.0",
        "course_id": course_id,
        "stage": "P02",
        "status": "pass" if all(checks.values()) else "needs_review",
        "checks": checks,
        "metrics": {
            "input_segment_count": len(source_segments),
            "output_segment_count": len(output_segments),
            "preservation_mismatch_count": len(preservation_mismatches),
            "invalid_source_role_count": len(invalid_source_roles),
            "invalid_epistemic_type_count": len(invalid_epistemic_types),
            "invalid_relevance_count": len(invalid_relevance),
            "invalid_classification_confidence_count": len(invalid_confidence),
            "missing_classification_reasons_count": len(missing_reasons),
        },
        "samples": {
            "preservation_mismatch_indexes": preservation_mismatches[:20],
            "invalid_source_role_indexes": invalid_source_roles[:20],
            "invalid_epistemic_type_indexes": invalid_epistemic_types[:20],
            "invalid_relevance_indexes": invalid_relevance[:20],
            "invalid_classification_confidence_indexes": invalid_confidence[:20],
            "missing_classification_reasons_indexes": missing_reasons[:20],
        },
    }


def write_p02_qa(
    course_id: str,
    p01_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    expected_prompt_version: str = "knowledge-v002-p02",
) -> Path:
    report = validate_p02_output(
        course_id,
        p01_path,
        output_path,
        expected_prompt_version=expected_prompt_version,
    )
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    return Path(report_path)
