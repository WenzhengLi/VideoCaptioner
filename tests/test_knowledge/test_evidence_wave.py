from __future__ import annotations

import json
from pathlib import Path

import pytest

from course_video_analyzer.knowledge.evidence_wave import (
    assert_evidence_only,
    build_evidence_baseline,
    enabled_stages,
    finalize_evidence_wave,
)


def test_enabled_stages_stops_at_p04() -> None:
    assert enabled_stages("P04") == ["P01", "P02", "P03", "P04"]
    assert enabled_stages("P02") == ["P01", "P02"]
    assert_evidence_only("P04")
    with pytest.raises(ValueError):
        enabled_stages("P05")


def test_finalize_evidence_wave_writes_marker_without_p05(tmp_path: Path) -> None:
    batch_id = "BATCH-TEST"
    wave_id = "C016-C020"
    for ordinal in (16, 17):
        course_id = f"C{ordinal:03d}"
        course = tmp_path / "courses" / course_id
        (course / "03_cases").mkdir(parents=True)
        (course / "qa").mkdir(parents=True)
        (course / "qa" / "RUN-20260715-001-V001.json").write_text(
            json.dumps({"status": "pass"}), encoding="utf-8"
        )
        for stage in ("P01", "P02", "P03"):
            (course / "qa" / f"{stage}-knowledge-v003-qa.json").write_text(
                json.dumps({"status": "pass"}), encoding="utf-8"
            )
        cases = [
            {
                "case_id": f"CASE-{course_id}-001",
                "start_segment_id": f"SEG-{course_id}-000001",
                "end_segment_id": f"SEG-{course_id}-000010",
            }
        ]
        (course / "03_cases" / "P03-knowledge-v003.json").write_text(
            json.dumps({"cases": cases}),
            encoding="utf-8",
        )
        (course / "qa" / f"P04-CASE-{course_id}-001-knowledge-v003-qa.json").write_text(
            json.dumps({"status": "pass"}),
            encoding="utf-8",
        )

    marker = finalize_evidence_wave(
        tmp_path,
        batch_id,
        wave_id,
        start_ordinal=16,
        end_ordinal=17,
        output_version="knowledge-v003",
        through_stage="P04",
    )
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["status"] == "complete"
    assert payload["through_stage"] == "P04"
    assert payload["forbidden_stages"] == ["P05", "P06"]
    assert "P05" not in payload["enabled_stages"]
    assert payload["failed_courses"] == []
    assert marker.name == "evidence-pipeline-C016-C020-complete.json"


def test_build_evidence_baseline_marks_changed_cases(tmp_path: Path) -> None:
    course = tmp_path / "courses" / "C003"
    (course / "03_cases").mkdir(parents=True)
    (course / "qa").mkdir(parents=True)
    (course / "03_cases" / "P03-knowledge-v002.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "CASE-C003-001",
                        "start_segment_id": "SEG-C003-000001",
                        "end_segment_id": "SEG-C003-000100",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (course / "03_cases" / "P03-knowledge-v003.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "CASE-C003-001",
                        "start_segment_id": "SEG-C003-000001",
                        "end_segment_id": "SEG-C003-000180",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (course / "qa" / "P04-CASE-C003-001-knowledge-v003-qa.json").write_text(
        json.dumps({"status": "pass"}),
        encoding="utf-8",
    )
    payload = build_evidence_baseline(
        tmp_path,
        start_ordinal=3,
        end_ordinal=3,
        p01_version="knowledge-v002",
        p02_version="knowledge-v002",
        p03_version="knowledge-v003",
        p04_version="knowledge-v003",
        previous_p03_version="knowledge-v002",
    )
    case = payload["courses"][0]["cases"][0]
    assert case["source_case_changed"] is True
    assert case["qa_status"] == "pass"
