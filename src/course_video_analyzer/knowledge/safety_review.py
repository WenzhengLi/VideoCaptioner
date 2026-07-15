"""P05 evidence/safety review bundle and structural QA."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text

REVIEW_TARGET_FIELDS = {
    "observations": "observation",
    "instructor_claims": "instructor_claim",
    "alternative_explanations": "alternative_explanation",
    "outcomes": "outcome",
    "quoted_expressions": "quoted_expression",
}
ALLOWED_REVIEW_STATUS = {"supported", "partially_supported", "unsupported", "contradicted"}
ALLOWED_CASE_REVIEW_STATUS = {"pass", "needs_revision", "blocked"}


def build_p05_input(
    course_id: str,
    case_id: str,
    case_input_path: Path,
    p04_path: Path,
    output_path: Path,
) -> Path:
    case_input = json.loads(Path(case_input_path).read_text(encoding="utf-8"))
    p04 = json.loads(Path(p04_path).read_text(encoding="utf-8"))
    payload = {
        "schema_version": "1.0",
        "prompt_version": "knowledge-v002-p05-input",
        "source_ids": [course_id],
        "course_id": course_id,
        "case_id": case_id,
        "case_segments": case_input.get("segments", []),
        "extraction": p04,
    }
    atomic_write_text(output_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return Path(output_path)


def validate_p05_output(
    course_id: str,
    case_id: str,
    input_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source = json.loads(Path(input_path).read_text(encoding="utf-8"))
    output = json.loads(Path(output_path).read_text(encoding="utf-8"))
    extraction = source.get("extraction") or {}
    valid_segment_ids = {item["segment_id"] for item in source.get("case_segments", [])}
    expected_targets: set[tuple[str, str]] = set()
    for field, target_type in REVIEW_TARGET_FIELDS.items():
        for item in extraction.get(field, []):
            item_id = str(item.get("id", ""))
            if item_id:
                expected_targets.add((target_type, item_id))
    actual_targets: set[tuple[str, str]] = set()
    invalid_reviews: list[int] = []
    invalid_evidence: list[str] = []
    reviews = output.get("evidence_reviews")
    if not isinstance(reviews, list):
        reviews = []
    for index, item in enumerate(reviews):
        if not isinstance(item, dict):
            invalid_reviews.append(index)
            continue
        target = (str(item.get("target_type", "")), str(item.get("target_id", "")))
        actual_targets.add(target)
        if item.get("status") not in ALLOWED_REVIEW_STATUS:
            invalid_reviews.append(index)
        evidence = item.get("supported_by_segment_ids")
        if not isinstance(evidence, list):
            invalid_reviews.append(index)
        else:
            invalid_evidence.extend(
                f"evidence_reviews[{index}]:{segment_id}"
                for segment_id in evidence
                if segment_id not in valid_segment_ids
            )
    for field in ("safety_flags", "unsafe_recommendation_candidates", "missing_context"):
        items = output.get(field)
        if not isinstance(items, list):
            invalid_reviews.append(-1)
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                invalid_reviews.append(index)
                continue
            evidence = item.get("evidence_segment_ids", [])
            if not isinstance(evidence, list):
                invalid_reviews.append(index)
                continue
            invalid_evidence.extend(
                f"{field}[{index}]:{segment_id}"
                for segment_id in evidence
                if segment_id not in valid_segment_ids
            )
    confidence = output.get("confidence")
    checks = {
        "schema_version": output.get("schema_version") == "1.0",
        "prompt_version": output.get("prompt_version") == "knowledge-v002-p05",
        "identity": output.get("source_ids") == [course_id]
        and output.get("course_id") == course_id
        and output.get("case_id") == case_id,
        "all_extracted_items_reviewed": expected_targets == actual_targets,
        "review_contract": not invalid_reviews,
        "evidence_in_case_range": not invalid_evidence,
        "required_corrections_contract": isinstance(output.get("required_corrections"), list),
        "review_status_contract": output.get("review_status") in ALLOWED_CASE_REVIEW_STATUS,
        "confidence_contract": isinstance(confidence, (int, float)) and 0 <= confidence <= 1,
    }
    return {
        "schema_version": "1.0",
        "course_id": course_id,
        "case_id": case_id,
        "stage": "P05",
        "status": "pass" if all(checks.values()) else "needs_review",
        "checks": checks,
        "metrics": {
            "expected_review_count": len(expected_targets),
            "actual_review_count": len(actual_targets),
            "safety_flag_count": len(output.get("safety_flags", []))
            if isinstance(output.get("safety_flags"), list)
            else 0,
            "invalid_evidence_count": len(invalid_evidence),
        },
        "samples": {
            "missing_targets": sorted(expected_targets - actual_targets)[:20],
            "extra_targets": sorted(actual_targets - expected_targets)[:20],
            "invalid_evidence": invalid_evidence[:20],
        },
    }


def write_p05_qa(
    course_id: str,
    case_id: str,
    input_path: Path,
    output_path: Path,
    report_path: Path,
) -> Path:
    report = validate_p05_output(course_id, case_id, input_path, output_path)
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    return Path(report_path)
