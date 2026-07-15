"""P04 case bundle construction and deterministic evidence validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text


def build_p04_case_input(
    course_id: str,
    case_id: str,
    p02_path: Path,
    p03_path: Path,
    output_path: Path,
) -> Path:
    p02 = json.loads(Path(p02_path).read_text(encoding="utf-8"))
    p03 = json.loads(Path(p03_path).read_text(encoding="utf-8"))
    segments = p02.get("segments")
    cases = p03.get("cases")
    if not isinstance(segments, list) or not isinstance(cases, list):
        raise ValueError("P02/P03 结构无效")
    case = next((item for item in cases if item.get("case_id") == case_id), None)
    if case is None:
        raise ValueError(f"未找到案例: {case_id}")
    index_by_id = {item["segment_id"]: index for index, item in enumerate(segments)}
    start = index_by_id[case["start_segment_id"]]
    end = index_by_id[case["end_segment_id"]]
    compact_segments = []
    for item in segments[start : end + 1]:
        compact_segments.append(
            {
                "segment_id": item["segment_id"],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
                "speaker": item["speaker"],
                "content_type": item["content_type"],
                "source_role": item["source_role"],
                "epistemic_type": item["epistemic_type"],
                "relevance": item["relevance"],
                "text": item["normalized_text"],
            }
        )
    payload = {
        "schema_version": "1.0",
        "prompt_version": "knowledge-v002-p04-input",
        "source_ids": [course_id],
        "course_id": course_id,
        "case": case,
        "segment_count": len(compact_segments),
        "segments": compact_segments,
    }
    atomic_write_text(output_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return Path(output_path)


def validate_p04_output(
    course_id: str,
    case_id: str,
    case_input_path: Path,
    output_path: Path,
    *,
    expected_prompt_version: str = "knowledge-v002-p04",
) -> dict[str, Any]:
    source = json.loads(Path(case_input_path).read_text(encoding="utf-8"))
    output = json.loads(Path(output_path).read_text(encoding="utf-8"))
    valid_ids = {item["segment_id"] for item in source.get("segments", [])}
    invalid_evidence: list[str] = []
    missing_evidence: list[str] = []

    def check_items(field: str, evidence_field: str = "evidence_segment_ids") -> None:
        items = output.get(field)
        if not isinstance(items, list):
            missing_evidence.append(field)
            return
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                missing_evidence.append(f"{field}[{index}]")
                continue
            evidence = item.get(evidence_field)
            if not isinstance(evidence, list) or not evidence:
                missing_evidence.append(f"{field}[{index}].{evidence_field}")
                continue
            invalid_evidence.extend(
                f"{field}[{index}]:{segment_id}"
                for segment_id in evidence
                if segment_id not in valid_ids
            )

    for field in ("participants", "timeline", "observations", "instructor_claims", "outcomes", "quoted_expressions"):
        check_items(field)
    check_items("alternative_explanations", "basis_evidence_segment_ids")
    evidence_spans = output.get("evidence_spans")
    evidence_ids: list[str] = []
    if isinstance(evidence_spans, list):
        for index, item in enumerate(evidence_spans):
            if not isinstance(item, dict) or not str(item.get("evidence_id", "")):
                missing_evidence.append(f"evidence_spans[{index}].evidence_id")
                continue
            evidence_ids.append(str(item["evidence_id"]))
            segment_ids = item.get("segment_ids")
            if not isinstance(segment_ids, list) or not segment_ids:
                missing_evidence.append(f"evidence_spans[{index}].segment_ids")
            else:
                invalid_evidence.extend(
                    f"evidence_spans[{index}]:{segment_id}"
                    for segment_id in segment_ids
                    if segment_id not in valid_ids
                )
    else:
        missing_evidence.append("evidence_spans")
    confidence = output.get("confidence")
    checks = {
        "schema_version": output.get("schema_version") == "1.0",
        "prompt_version": output.get("prompt_version") == expected_prompt_version,
        "identity": output.get("source_ids") == [course_id]
        and output.get("course_id") == course_id
        and output.get("case_id") == case_id,
        "summary_present": bool(str(output.get("summary", "")).strip()),
        "evidence_present": not missing_evidence,
        "evidence_in_case_range": not invalid_evidence,
        "evidence_ids_unique": len(evidence_ids) == len(set(evidence_ids)),
        "uncertainties_contract": isinstance(output.get("uncertainties"), list),
        "confidence_contract": isinstance(confidence, (int, float)) and 0 <= confidence <= 1,
    }
    return {
        "schema_version": "1.0",
        "course_id": course_id,
        "case_id": case_id,
        "stage": "P04",
        "status": "pass" if all(checks.values()) else "needs_review",
        "checks": checks,
        "metrics": {
            "case_segment_count": len(valid_ids),
            "evidence_span_count": len(evidence_spans) if isinstance(evidence_spans, list) else 0,
            "missing_evidence_count": len(missing_evidence),
            "invalid_evidence_count": len(invalid_evidence),
        },
        "samples": {
            "missing_evidence": missing_evidence[:20],
            "invalid_evidence": invalid_evidence[:20],
        },
    }


def write_p04_qa(
    course_id: str,
    case_id: str,
    case_input_path: Path,
    output_path: Path,
    report_path: Path,
) -> Path:
    report = validate_p04_output(course_id, case_id, case_input_path, output_path)
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    return Path(report_path)
