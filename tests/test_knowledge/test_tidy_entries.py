import json
from pathlib import Path

from course_video_analyzer.knowledge.tidy_entries import (
    export_tidy_markdown,
    validate_p06_output,
)


def test_p06_qa_and_markdown_export(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "extraction": {"evidence_spans": [{"segment_ids": ["SEG-C001-000001"]}]},
                "review": {"review_status": "pass"},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "p06.json"
    entry = {
        "id": "KNOW-C001-CASE001-001",
        "title": "原则",
        "type": "principle",
        "source_ids": ["C001"],
        "case_id": "CASE-C001-001",
        "evidence_spans": ["SEG-C001-000001"],
        "relationship_stage": [],
        "scenario": [],
        "observations": ["事实"],
        "instructor_claims": [],
        "alternative_explanations": [],
        "principles": ["原则"],
        "applicability": [],
        "contraindications": [],
        "risks": [],
        "safety_flags": [],
        "response_options": [],
        "confidence": 0.8,
    }
    output.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "prompt_version": "knowledge-v002-p06",
                "source_ids": ["C001"],
                "course_id": "C001",
                "case_id": "CASE-C001-001",
                "entries": [entry],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = validate_p06_output("C001", "CASE-C001-001", source, output)
    paths = export_tidy_markdown(output, tmp_path / "tidy")

    assert report["status"] == "pass"
    assert len(paths) == 1
    assert "# 原则" in paths[0].read_text(encoding="utf-8")
