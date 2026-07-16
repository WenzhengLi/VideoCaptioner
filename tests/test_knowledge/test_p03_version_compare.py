from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "compare_p03_versions.py"
_SPEC = importlib.util.spec_from_file_location("compare_p03_versions", _SCRIPT)
assert _SPEC and _SPEC.loader
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
compare_course = _MOD.compare_course
decide_adoption = _MOD.decide_adoption


def _write_p03(path: Path, *, cases: list[dict], unassigned: list[str], prompt: str) -> None:
    # derive assigned via indexes in ids list later; store metrics explicitly
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "prompt_version": prompt,
                "source_ids": ["C003"],
                "course_id": "C003",
                "cases": cases,
                "unassigned_segment_ids": unassigned,
                "segmentation_metrics": {
                    "input_segment_count": 10,
                    "case_count": len(cases),
                    "assigned_segment_count": 10 - len(unassigned),
                    "unassigned_segment_count": len(unassigned),
                },
            }
        ),
        encoding="utf-8",
    )


def test_compare_course_detects_unassigned_improvement(tmp_path: Path) -> None:
    course = tmp_path / "courses" / "C003"
    (course / "02_normalized").mkdir(parents=True)
    (course / "03_cases").mkdir(parents=True)
    (course / "qa").mkdir(parents=True)
    segments = [
        {
            "segment_id": f"SEG-C003-{i:06d}",
            "normalized_text": "案例正文" if i < 8 else "今天先到这 加微信优惠",
        }
        for i in range(1, 11)
    ]
    (course / "02_normalized" / "P02-knowledge-v002.json").write_text(
        json.dumps({"segments": segments}),
        encoding="utf-8",
    )
    _write_p03(
        course / "03_cases" / "P03-knowledge-v002.json",
        cases=[
            {
                "case_id": "CASE-C003-001",
                "title": "案例A",
                "start_segment_id": "SEG-C003-000001",
                "end_segment_id": "SEG-C003-000006",
                "completeness": "complete",
                "boundary_evidence": {"evidence_segment_ids": ["SEG-C003-000001"]},
            }
        ],
        unassigned=[f"SEG-C003-{i:06d}" for i in range(7, 11)],
        prompt="knowledge-v002-p03",
    )
    _write_p03(
        course / "03_cases" / "P03-knowledge-v003.json",
        cases=[
            {
                "case_id": "CASE-C003-001",
                "title": "案例A",
                "start_segment_id": "SEG-C003-000001",
                "end_segment_id": "SEG-C003-000008",
                "completeness": "complete",
                "boundary_evidence": {"evidence_segment_ids": ["SEG-C003-000001"]},
            }
        ],
        unassigned=["SEG-C003-000009", "SEG-C003-000010"],
        prompt="knowledge-v003-p03",
    )
    (course / "qa" / "P03-knowledge-v003-qa.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "checks": {
                    "complete_segment_coverage": True,
                    "cases_do_not_overlap": True,
                },
            }
        ),
        encoding="utf-8",
    )

    result = compare_course(
        "C003",
        course / "02_normalized" / "P02-knowledge-v002.json",
        course / "03_cases" / "P03-knowledge-v002.json",
        course / "03_cases" / "P03-knowledge-v003.json",
        None,
        course / "qa" / "P03-knowledge-v003-qa.json",
    )
    assert result["delta"]["unassigned_ratio"] == -0.2
    assert result["newly_assigned_count"] == 2
    assert result["suspicious_forced_ad_or_chatter"]  # SEG 000008 looks like ad/chatter
    recommendation, notes = decide_adoption([result])
    assert recommendation == "keep_v002_pending_prompt_fix" or recommendation.startswith(
        "adopt_v003"
    )
    # With only 1 soft heuristic hit, adoption should not hard-block.
    assert recommendation == "adopt_v003_hybrid"
    assert "soft ad/chatter" in notes
