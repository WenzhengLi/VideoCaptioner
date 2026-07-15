import json
from pathlib import Path

from course_video_analyzer.knowledge.cleaning_qa import validate_p03_output


def _write_p02(path: Path) -> None:
    path.write_text(
        json.dumps(
            {"segments": [{"segment_id": f"SEG-C001-{i:06d}"} for i in range(1, 6)]}
        ),
        encoding="utf-8",
    )


def test_p03_qa_requires_exact_non_overlapping_coverage(tmp_path: Path) -> None:
    p02 = tmp_path / "p02.json"
    output = tmp_path / "p03.json"
    _write_p02(p02)
    output.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "prompt_version": "knowledge-v002-p03",
                "source_ids": ["C001"],
                "course_id": "C001",
                "cases": [
                    {
                        "case_id": "CASE-C001-001",
                        "title": "第一个案例",
                        "start_segment_id": "SEG-C001-000002",
                        "end_segment_id": "SEG-C001-000004",
                        "participant_roles": ["teacher_a"],
                        "boundary_evidence": {
                            "start_reason": "明确开始",
                            "end_reason": "明确结束",
                            "evidence_segment_ids": ["SEG-C001-000002"],
                        },
                        "completeness": "complete",
                        "confidence": 0.9,
                    }
                ],
                "unassigned_segment_ids": ["SEG-C001-000001", "SEG-C001-000005"],
                "uncertainties": [],
                "segmentation_metrics": {
                    "input_segment_count": 5,
                    "case_count": 1,
                    "assigned_segment_count": 3,
                    "unassigned_segment_count": 2,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = validate_p03_output("C001", p02, output)

    assert report["status"] == "pass"


def test_p03_qa_rejects_missing_and_overlapping_segments(tmp_path: Path) -> None:
    p02 = tmp_path / "p02.json"
    output = tmp_path / "p03.json"
    _write_p02(p02)
    output.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "prompt_version": "knowledge-v002-p03",
                "source_ids": ["C001"],
                "course_id": "C001",
                "cases": [
                    {
                        "case_id": "CASE-C001-001",
                        "title": "重叠案例",
                        "start_segment_id": "SEG-C001-000002",
                        "end_segment_id": "SEG-C001-000004",
                        "participant_roles": [],
                        "boundary_evidence": {},
                        "completeness": "partial",
                        "confidence": 0.5,
                    }
                ],
                "unassigned_segment_ids": ["SEG-C001-000004"],
                "segmentation_metrics": {
                    "input_segment_count": 5,
                    "case_count": 1,
                    "assigned_segment_count": 3,
                    "unassigned_segment_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )

    report = validate_p03_output("C001", p02, output)

    assert report["status"] == "needs_review"
    assert not report["checks"]["case_unassigned_disjoint"]
    assert not report["checks"]["complete_segment_coverage"]
