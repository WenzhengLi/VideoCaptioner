import json
from pathlib import Path

from course_video_analyzer.knowledge.extraction import (
    build_p04_case_input,
    validate_p04_output,
)


def test_p04_bundle_and_evidence_qa(tmp_path: Path) -> None:
    p02 = tmp_path / "p02.json"
    p03 = tmp_path / "p03.json"
    segments = []
    for index in range(1, 51):
        segments.append(
            {
                "segment_id": f"SEG-C001-{index:06d}",
                "start_ms": index * 1000,
                "end_ms": (index + 1) * 1000,
                "speaker": "speaker_0",
                "content_type": "speech",
                "source_role": "instructor_explanation",
                "epistemic_type": "instructor_claim",
                "relevance": "core",
                "normalized_text": f"内容{index}",
            }
        )
    p02.write_text(json.dumps({"segments": segments}, ensure_ascii=False), encoding="utf-8")
    p03.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "CASE-C001-001",
                        "title": "案例",
                        "start_segment_id": "SEG-C001-000001",
                        "end_segment_id": "SEG-C001-000050",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    case_input = tmp_path / "case-input.json"
    build_p04_case_input("C001", "CASE-C001-001", p02, p03, case_input)
    output = tmp_path / "p04.json"
    evidence = [f"SEG-C001-{i:06d}" for i in range(1, 51)]
    output.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "prompt_version": "knowledge-v002-p04",
                "source_ids": ["C001"],
                "course_id": "C001",
                "case_id": "CASE-C001-001",
                "summary": "摘要",
                "participants": [{"evidence_segment_ids": evidence[:5]}],
                "timeline": [{"evidence_segment_ids": [evidence[i]]} for i in range(10)],
                "observations": [{"evidence_segment_ids": [evidence[i]]} for i in range(8)],
                "instructor_claims": [{"evidence_segment_ids": [evidence[i]]} for i in range(8)],
                "alternative_explanations": [{"basis_evidence_segment_ids": evidence[:3]}],
                "outcomes": [{"evidence_segment_ids": evidence[:3]}],
                "quoted_expressions": [{"evidence_segment_ids": [evidence[i]]} for i in range(8)],
                "evidence_spans": [
                    {"evidence_id": f"EVD-{i:03d}", "segment_ids": [evidence[i]], "quote": f"引用{i}"}
                    for i in range(15)
                ],
                "uncertainties": [],
                "confidence": 0.8,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = validate_p04_output("C001", "CASE-C001-001", case_input, output)

    assert report["status"] == "pass"


def test_p04_qa_accepts_v003_prompt_version(tmp_path: Path) -> None:
    case_input = tmp_path / "case-input.json"
    segments = [{"segment_id": f"SEG-C003-{i:06d}"} for i in range(1, 51)]
    case_input.write_text(
        json.dumps({"segments": segments}, ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "p04.json"
    evidence = [f"SEG-C003-{i:06d}" for i in range(1, 51)]
    output.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "prompt_version": "knowledge-v003-p04",
                "source_ids": ["C003"],
                "course_id": "C003",
                "case_id": "CASE-C003-001",
                "summary": "摘要",
                "participants": [{"evidence_segment_ids": evidence[:5]}],
                "timeline": [{"evidence_segment_ids": [evidence[i]]} for i in range(10)],
                "observations": [{"evidence_segment_ids": [evidence[i]]} for i in range(8)],
                "instructor_claims": [{"evidence_segment_ids": [evidence[i]]} for i in range(8)],
                "alternative_explanations": [{"basis_evidence_segment_ids": evidence[:3]}],
                "outcomes": [{"evidence_segment_ids": evidence[:3]}],
                "quoted_expressions": [{"evidence_segment_ids": [evidence[i]]} for i in range(8)],
                "evidence_spans": [
                    {"evidence_id": f"EVD-{i:03d}", "segment_ids": [evidence[i]], "quote": f"引用{i}"}
                    for i in range(15)
                ],
                "uncertainties": [],
                "confidence": 0.8,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = validate_p04_output(
        "C003",
        "CASE-C003-001",
        case_input,
        output,
        expected_prompt_version="knowledge-v003-p04",
    )

    assert report["status"] == "pass"
    assert report["checks"]["prompt_version"] is True

