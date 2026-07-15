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
ALLOWED_CASE_COMPLETENESS = {"complete", "partial", "uncertain"}


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


def validate_p03_output(
    course_id: str,
    p02_path: Path,
    output_path: Path,
    *,
    expected_prompt_version: str = "knowledge-v002-p03",
) -> dict[str, Any]:
    source = json.loads(Path(p02_path).read_text(encoding="utf-8"))
    output = json.loads(Path(output_path).read_text(encoding="utf-8"))
    source_segments = source.get("segments") if isinstance(source.get("segments"), list) else []
    source_ids = [
        str(item.get("segment_id", ""))
        for item in source_segments
        if isinstance(item, dict)
    ]
    index_by_id = {segment_id: index for index, segment_id in enumerate(source_ids)}
    cases = output.get("cases") if isinstance(output.get("cases"), list) else []
    unassigned = (
        output.get("unassigned_segment_ids")
        if isinstance(output.get("unassigned_segment_ids"), list)
        else []
    )
    invalid_case_indexes: list[int] = []
    invalid_boundary_indexes: list[int] = []
    overlapping_case_indexes: list[int] = []
    covered: set[str] = set()
    case_ids: list[str] = []
    last_end = -1
    expected_case_prefix = f"CASE-{course_id}-"
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            invalid_case_indexes.append(index)
            continue
        case_id = str(case.get("case_id", ""))
        case_ids.append(case_id)
        confidence = case.get("confidence")
        structurally_valid = (
            case_id.startswith(expected_case_prefix)
            and bool(str(case.get("title", "")).strip())
            and case.get("completeness") in ALLOWED_CASE_COMPLETENESS
            and isinstance(case.get("participant_roles"), list)
            and isinstance(case.get("boundary_evidence"), dict)
            and isinstance(confidence, (int, float))
            and 0 <= confidence <= 1
        )
        if not structurally_valid:
            invalid_case_indexes.append(index)
        start_id = str(case.get("start_segment_id", ""))
        end_id = str(case.get("end_segment_id", ""))
        if start_id not in index_by_id or end_id not in index_by_id:
            invalid_boundary_indexes.append(index)
            continue
        start = index_by_id[start_id]
        end = index_by_id[end_id]
        if start > end:
            invalid_boundary_indexes.append(index)
            continue
        if start <= last_end:
            overlapping_case_indexes.append(index)
        last_end = max(last_end, end)
        for segment_id in source_ids[start : end + 1]:
            if segment_id in covered:
                if index not in overlapping_case_indexes:
                    overlapping_case_indexes.append(index)
            covered.add(segment_id)

    unassigned_ids = [str(value) for value in unassigned]
    invalid_unassigned = [
        index for index, segment_id in enumerate(unassigned_ids) if segment_id not in index_by_id
    ]
    duplicate_unassigned = len(unassigned_ids) != len(set(unassigned_ids))
    case_unassigned_overlap = sorted(covered.intersection(unassigned_ids))
    represented = covered.union(unassigned_ids)
    missing_ids = [segment_id for segment_id in source_ids if segment_id not in represented]
    extra_ids = [segment_id for segment_id in represented if segment_id not in index_by_id]
    metrics = output.get("segmentation_metrics")
    metrics_consistent = isinstance(metrics, dict) and (
        metrics.get("input_segment_count") == len(source_ids)
        and metrics.get("case_count") == len(cases)
        and metrics.get("assigned_segment_count") == len(covered)
        and metrics.get("unassigned_segment_count") == len(unassigned_ids)
    )
    checks = {
        "schema_version": output.get("schema_version") == "1.0",
        "prompt_version": output.get("prompt_version") == expected_prompt_version,
        "source_id": output.get("source_ids") == [course_id]
        and output.get("course_id") == course_id,
        "source_segment_ids_valid": len(source_ids) == len(source_segments)
        and len(source_ids) == len(set(source_ids))
        and all(source_ids),
        "case_contract": not invalid_case_indexes and len(case_ids) == len(set(case_ids)),
        "case_boundaries_valid": not invalid_boundary_indexes,
        "cases_do_not_overlap": not overlapping_case_indexes,
        "unassigned_contract": not invalid_unassigned and not duplicate_unassigned,
        "case_unassigned_disjoint": not case_unassigned_overlap,
        "complete_segment_coverage": not missing_ids and not extra_ids and bool(source_ids),
        "segmentation_metrics_consistent": metrics_consistent,
    }
    return {
        "schema_version": "1.0",
        "course_id": course_id,
        "stage": "P03",
        "status": "pass" if all(checks.values()) else "needs_review",
        "checks": checks,
        "metrics": {
            "input_segment_count": len(source_ids),
            "case_count": len(cases),
            "assigned_segment_count": len(covered),
            "unassigned_segment_count": len(unassigned_ids),
            "missing_segment_count": len(missing_ids),
            "overlap_count": len(case_unassigned_overlap) + len(overlapping_case_indexes),
        },
        "samples": {
            "invalid_case_indexes": invalid_case_indexes[:20],
            "invalid_boundary_indexes": invalid_boundary_indexes[:20],
            "overlapping_case_indexes": overlapping_case_indexes[:20],
            "invalid_unassigned_indexes": invalid_unassigned[:20],
            "case_unassigned_overlap_ids": case_unassigned_overlap[:20],
            "missing_segment_ids": missing_ids[:20],
            "extra_segment_ids": extra_ids[:20],
        },
    }


def write_p03_qa(
    course_id: str,
    p02_path: Path,
    output_path: Path,
    report_path: Path,
    *,
    expected_prompt_version: str = "knowledge-v002-p03",
) -> Path:
    report = validate_p03_output(
        course_id,
        p02_path,
        output_path,
        expected_prompt_version=expected_prompt_version,
    )
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    return Path(report_path)
