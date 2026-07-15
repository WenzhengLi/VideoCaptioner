import json
from pathlib import Path

from course_video_analyzer.knowledge.cleaning_qa import validate_p02_output


def test_validate_p02_preserves_p01_fields_and_checks_classification(tmp_path: Path) -> None:
    base_segment = {
        "segment_id": "SEG-C001-000001",
        "start_ms": 0,
        "end_ms": 1000,
        "speaker": "teacher_a",
        "content_type": "speech",
        "raw_text": "这是测试,",
        "normalized_text": "这是测试，",
        "edit_notes": ["punctuation_normalized"],
        "confidence": 0.9,
    }
    p01 = tmp_path / "p01.json"
    p01.write_text(json.dumps({"segments": [base_segment]}, ensure_ascii=False), encoding="utf-8")
    p02 = tmp_path / "p02.json"
    p02.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "prompt_version": "knowledge-v002-p02",
                "source_ids": ["C001"],
                "segments": [
                    {
                        **base_segment,
                        "source_role": "instructor_explanation",
                        "epistemic_type": "instructor_claim",
                        "relevance": "core",
                        "classification_reasons": ["讲师作出判断"],
                        "classification_confidence": 0.9,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = validate_p02_output("C001", p01, p02)

    assert report["status"] == "pass"
    assert report["metrics"]["preservation_mismatch_count"] == 0
