from __future__ import annotations

import json
from pathlib import Path

import pytest

from course_video_analyzer.knowledge.afeng_experiment import (
    BaselineCase,
    BaselineCourse,
    EvidenceBaseline,
    load_evidence_baseline,
    prepare_afeng_pilot,
    write_manual_review_template,
)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _course(data_root: Path) -> None:
    course = data_root / "courses" / "C003"
    _write(course / "source.json", {"title": "第三课"})
    segment = {
        "segment_id": "SEG-C003-000001",
        "start_ms": 100,
        "end_ms": 200,
        "speaker": "speaker_0",
        "content_type": "speech",
        "source_role": "instructor_explanation",
        "epistemic_type": "instructor_claim",
        "text": "微信号 testabc，课程说明先观察。",
    }
    _write(
        course
        / "04_knowledge"
        / "P04-input-knowledge-v003"
        / "CASE-C003-001.json",
        {
            "course_id": "C003",
            "case": {"case_id": "CASE-C003-001"},
            "segments": [segment],
        },
    )
    _write(
        course / "04_knowledge" / "P04-knowledge-v003" / "CASE-C003-001.json",
        {
            "prompt_version": "knowledge-v003-p04",
            "course_id": "C003",
            "case_id": "CASE-C003-001",
            "case_title": "案例",
            "summary": "摘要",
            "observations": [],
            "instructor_claims": [
                {
                    "id": "CLM-001",
                    "text": "先观察",
                    "evidence_segment_ids": ["SEG-C003-000001"],
                }
            ],
            "alternative_explanations": [],
            "outcomes": [],
            "quoted_expressions": [],
            "uncertainties": [],
        },
    )


def test_baseline_rejects_nonpassing_case(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    _write(
        path,
        {
            "courses": [
                {
                    "course_id": "C003",
                    "p01_version": "v",
                    "p02_version": "v",
                    "p03_version": "v",
                    "cases": [
                        {"case_id": "CASE-C003-001", "p04_version": "v", "qa_status": "failed"}
                    ],
                }
            ]
        },
    )
    with pytest.raises(ValueError, match="non-passing"):
        load_evidence_baseline(path)


def test_prepare_pilot_builds_redacted_ready_manifest(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    _course(data_root)
    baseline = EvidenceBaseline(
        courses=[
            BaselineCourse(
                course_id="C003",
                p01_version="knowledge-v002",
                p02_version="knowledge-v002",
                p03_version="knowledge-v003",
                cases=[
                    BaselineCase(
                        case_id="CASE-C003-001",
                        p04_version="knowledge-v003",
                        qa_status="pass",
                    )
                ],
            )
        ]
    )
    manifest = prepare_afeng_pilot(
        baseline,
        tmp_path / "baseline.json",
        data_root,
        tmp_path / "pilots",
        pilot_id="pilot",
        course_ids=["C003"],
        historical_p05_version=None,
    )
    assert manifest.status == "ready"
    assert len(manifest.cases) == 1
    assert manifest.cases[0].external_payload_safe is True
    assert manifest.cases[0].pii_finding_count == 1
    assert manifest.cases[0].required_evidence_coverage == 1.0
    review_json, review_md = write_manual_review_template(
        manifest, tmp_path / "review.json", tmp_path / "review.md"
    )
    assert "CASE-C003-001" in review_json.read_text(encoding="utf-8")
    assert "evidence ID" in review_md.read_text(encoding="utf-8")
