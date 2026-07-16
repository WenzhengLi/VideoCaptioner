from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_knowledge_quality_report.py"
_SPEC = importlib.util.spec_from_file_location("build_knowledge_quality_report", _SCRIPT)
assert _SPEC and _SPEC.loader
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
analyze_course = _MOD.analyze_course


def test_analyze_course_uses_segmentation_metrics_and_top_level_safety(
    tmp_path: Path,
) -> None:
    course = tmp_path / "courses" / "C099"
    (course / "02_normalized").mkdir(parents=True)
    (course / "03_cases").mkdir(parents=True)
    (course / "04_knowledge" / "P05-knowledge-v003").mkdir(parents=True)
    (course / "05_tidy" / "P06-knowledge-v003").mkdir(parents=True)
    (course / "05_tidy" / "markdown-knowledge-v003").mkdir(parents=True)
    (course / "qa").mkdir(parents=True)

    (course / "02_normalized" / "P01-knowledge-v003.json").write_text(
        json.dumps(
            {
                "segments": [
                    {"segment_id": "SEG-C099-000001", "speaker": "speaker_0"},
                    {"segment_id": "SEG-C099-000002", "speaker": "unknown"},
                    {"segment_id": "SEG-C099-000003", "speaker": "speaker_1"},
                    {"segment_id": "SEG-C099-000004", "speaker": "speaker_0"},
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
                        "case_id": "CASE-C099-001",
                        "start_segment_id": "SEG-C099-000001",
                        "end_segment_id": "SEG-C099-000003",
                    }
                ],
                "unassigned_segment_ids": ["SEG-C099-000004"],
                "segmentation_metrics": {
                    "input_segment_count": 4,
                    "case_count": 1,
                    "assigned_segment_count": 3,
                    "unassigned_segment_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    (course / "04_knowledge" / "P05-knowledge-v003" / "CASE-C099-001.json").write_text(
        json.dumps(
            {
                "case_id": "CASE-C099-001",
                "evidence_reviews": [{"target_id": "CLM-001", "status": "supported"}],
                "safety_flags": [
                    {"type": "explicit_refusal_or_pause", "severity": "high"},
                    {"type": "age_uncertainty", "severity": "medium"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (course / "05_tidy" / "P06-knowledge-v003" / "CASE-C099-001.json").write_text(
        json.dumps({"entries": [{"id": "KNOW-C099-CASE001-001"}, {"id": "x"}]}),
        encoding="utf-8",
    )
    (course / "05_tidy" / "markdown-knowledge-v003" / "a.md").write_text("x", encoding="utf-8")
    (course / "qa" / "P03-knowledge-v003-qa.json").write_text(
        json.dumps({"status": "pass"}),
        encoding="utf-8",
    )

    result = analyze_course(tmp_path, "C099", "knowledge-v003")
    assert result["segment_count"] == 4
    assert result["unknown_ratio"] == 0.25
    assert result["unassigned_ratio"] == 0.25
    assert result["p05_risk_count"] == 2
    assert result["p05_risk_types"]["explicit_refusal_or_pause"] == 1
    assert result["p06_entry_count"] == 2
    assert result["markdown_count"] == 1
    assert result["qa"]["P03"] == "pass"
