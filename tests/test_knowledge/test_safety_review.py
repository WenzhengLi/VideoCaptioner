import json
from pathlib import Path

from course_video_analyzer.knowledge.safety_review import validate_p05_output


def test_p05_qa_requires_review_for_each_extracted_item(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "case_segments": [{"segment_id": "SEG-C001-000001"}],
                "extraction": {
                    "observations": [{"id": "OBS-001"}],
                    "instructor_claims": [],
                    "alternative_explanations": [],
                    "outcomes": [],
                    "quoted_expressions": [],
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "p05.json"
    output.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "prompt_version": "knowledge-v002-p05",
                "source_ids": ["C001"],
                "course_id": "C001",
                "case_id": "CASE-C001-001",
                "evidence_reviews": [
                    {
                        "target_type": "observation",
                        "target_id": "OBS-001",
                        "status": "supported",
                        "supported_by_segment_ids": ["SEG-C001-000001"],
                    }
                ],
                "safety_flags": [],
                "unsafe_recommendation_candidates": [],
                "missing_context": [],
                "required_corrections": [],
                "review_status": "pass",
                "confidence": 0.9,
            }
        ),
        encoding="utf-8",
    )

    report = validate_p05_output("C001", "CASE-C001-001", source, output)

    assert report["status"] == "pass"
