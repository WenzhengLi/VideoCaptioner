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
    case_segment_count = len(valid_ids)
    invalid_evidence: list[str] = []
    missing_evidence: list[str] = []

    # Collect all unique evidence IDs
    all_evidence_ids: set[str] = set()

    def check_items(field: str, evidence_field: str = "evidence_segment_ids") -> bool:
        """Return True if field has non-empty items with valid evidence."""
        items = output.get(field)
        if not isinstance(items, list) or not items:
            return False
        has_valid = False
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                missing_evidence.append(f"{field}[{index}]")
                continue
            evidence = item.get(evidence_field)
            if not isinstance(evidence, list) or not evidence:
                missing_evidence.append(f"{field}[{index}].{evidence_field}")
                continue
            all_evidence_ids.update(evidence)
            invalid = [
                sid for sid in evidence if sid not in valid_ids
            ]
            if invalid:
                invalid_evidence.extend(f"{field}[{index}]:{sid}" for sid in invalid)
            has_valid = True
        return has_valid

    # Check each field - empty list counts as missing
    check_items("participants")
    timeline_ok = check_items("timeline")
    observations_ok = check_items("observations")
    instructor_claims_ok = check_items("instructor_claims")
    outcomes_ok = check_items("outcomes")
    quoted_expressions_ok = check_items("quoted_expressions")
    check_items("alternative_explanations", "basis_evidence_segment_ids")

    # evidence_spans: must be non-empty list
    evidence_spans = output.get("evidence_spans")
    evidence_ids: list[str] = []
    evidence_spans_ok = False
    if isinstance(evidence_spans, list) and evidence_spans:
        evidence_spans_ok = True
        for index, item in enumerate(evidence_spans):
            if not isinstance(item, dict) or not str(item.get("evidence_id", "")):
                missing_evidence.append(f"evidence_spans[{index}].evidence_id")
                evidence_spans_ok = False
                continue
            evidence_ids.append(str(item["evidence_id"]))
            segment_ids = item.get("segment_ids")
            if not isinstance(segment_ids, list) or not segment_ids:
                missing_evidence.append(f"evidence_spans[{index}].segment_ids")
                evidence_spans_ok = False
            else:
                all_evidence_ids.update(segment_ids)
                invalid = [sid for sid in segment_ids if sid not in valid_ids]
                if invalid:
                    invalid_evidence.extend(f"evidence_spans[{index}]:{sid}" for sid in invalid)
            # quote must be non-empty
            if not str(item.get("quote", "")).strip():
                missing_evidence.append(f"evidence_spans[{index}].quote")
                evidence_spans_ok = False
    elif isinstance(evidence_spans, list):
        # Empty list
        missing_evidence.append("evidence_spans:empty")
    else:
        missing_evidence.append("evidence_spans")

    # At least one content field must be non-empty
    has_any_content = any([
        observations_ok,
        instructor_claims_ok,
        quoted_expressions_ok,
        outcomes_ok,
        timeline_ok,
    ])

    # Compute unique evidence segment count
    unique_evidence_segment_count = len(all_evidence_ids)

    # Compute temporal quartile coverage
    source_segments = source.get("segments", [])
    if source_segments and all_evidence_ids:
        segment_positions = {}
        for i, seg in enumerate(source_segments):
            segment_positions[seg["segment_id"]] = i
        evidence_positions = [
            segment_positions[sid] for sid in all_evidence_ids if sid in segment_positions
        ]
        if evidence_positions:
            quartile_counts = [0, 0, 0, 0]
            for pos in evidence_positions:
                q = min(3, pos * 4 // case_segment_count) if case_segment_count > 0 else 0
                quartile_counts[q] += 1
            quartiles_covered = sum(1 for c in quartile_counts if c > 0)
        else:
            quartiles_covered = 0
    else:
        quartiles_covered = 0

    # Minimum thresholds based on mature case baseline (40 cases, C001-C020)
    # Baseline distribution (min values): evidence=73, spans=7, timeline=13, obs=3, claims=8, quotes=11
    # Use 50% of baseline minimums as absolute floor
    # For small cases (segment_count < 200), scale down proportionally but not below floor
    _scale = min(1.0, case_segment_count / 200) if case_segment_count > 0 else 0.1

    def _floor(absolute: int) -> int:
        return max(2, int(absolute * max(0.3, _scale)))

    min_evidence = _floor(36)   # 73 * 0.5 = 36
    min_spans = _floor(4)       # 7 * 0.5 rounded up
    min_timeline = _floor(7)    # 13 * 0.5 rounded up
    min_observations = _floor(2)  # 3 * 0.5 rounded up
    min_claims = _floor(4)      # 8 * 0.5
    min_quotes = _floor(6)      # 11 * 0.5 rounded up

    evidence_sufficient = unique_evidence_segment_count >= min_evidence
    spans_sufficient = len(evidence_spans) >= min_spans if isinstance(evidence_spans, list) else False
    timeline_sufficient = len(output.get("timeline", [])) >= min_timeline
    observations_sufficient = len(output.get("observations", [])) >= min_observations
    claims_sufficient = len(output.get("instructor_claims", [])) >= min_claims
    quotes_sufficient = len(output.get("quoted_expressions", [])) >= min_quotes

    confidence = output.get("confidence")
    checks = {
        "schema_version": output.get("schema_version") == "1.0",
        "prompt_version": output.get("prompt_version") == expected_prompt_version,
        "identity": output.get("source_ids") == [course_id]
        and output.get("course_id") == course_id
        and output.get("case_id") == case_id,
        "summary_present": bool(str(output.get("summary", "")).strip()),
        "evidence_spans_non_empty": evidence_spans_ok,
        "has_any_content": has_any_content,
        "evidence_present": not missing_evidence,
        "evidence_in_case_range": not invalid_evidence,
        "evidence_ids_unique": len(evidence_ids) == len(set(evidence_ids)),
        "evidence_sufficient": evidence_sufficient,
        "spans_sufficient": spans_sufficient,
        "timeline_sufficient": timeline_sufficient,
        "observations_sufficient": observations_sufficient,
        "claims_sufficient": claims_sufficient,
        "quotes_sufficient": quotes_sufficient,
        "temporal_coverage": quartiles_covered >= 2,
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
            "case_segment_count": case_segment_count,
            "unique_evidence_segment_count": unique_evidence_segment_count,
            "evidence_span_count": len(evidence_spans) if isinstance(evidence_spans, list) else 0,
            "timeline_count": len(output.get("timeline", [])),
            "observations_count": len(output.get("observations", [])),
            "instructor_claims_count": len(output.get("instructor_claims", [])),
            "quoted_expressions_count": len(output.get("quoted_expressions", [])),
            "quartiles_covered": quartiles_covered,
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
    *,
    expected_prompt_version: str = "knowledge-v002-p04",
) -> Path:
    report = validate_p04_output(
        course_id,
        case_id,
        case_input_path,
        output_path,
        expected_prompt_version=expected_prompt_version,
    )
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    return Path(report_path)
