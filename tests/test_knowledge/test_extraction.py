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


def _make_valid_p04(evidence_count: int = 50, timeline_descs: list[str] | None = None) -> dict:
    """Helper to create a valid P04 output."""
    evidence = [f"SEG-C001-{i:06d}" for i in range(1, evidence_count + 1)]
    if timeline_descs is None:
        timeline_descs = [
            "讲师引入案例",
            "展示聊天记录",
            "分析互动模式",
            "关键转折点",
            "方法总结",
            "结果展示",
            "案例收尾",
        ]
    return {
        "schema_version": "1.0",
        "prompt_version": "knowledge-v002-p04",
        "source_ids": ["C001"],
        "course_id": "C001",
        "case_id": "CASE-C001-001",
        "case_title": "测试案例",
        "summary": "讲师通过分析聊天记录展示互动技巧",
        "participants": [{"evidence_segment_ids": evidence[:5]}],
        "timeline": [{"evidence_segment_ids": [evidence[i]], "description": desc} for i, desc in enumerate(timeline_descs)],
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
    }


def _make_case_input(count: int = 50) -> dict:
    """Helper to create a case input."""
    return {"segments": [{"segment_id": f"SEG-C001-{i:06d}"} for i in range(1, count + 1)]}


def test_p04_placeholder_timeline_fails(tmp_path: Path) -> None:
    """Placeholder timeline descriptions must fail."""
    case_input = tmp_path / "case-input.json"
    case_input.write_text(json.dumps(_make_case_input()), encoding="utf-8")
    output = tmp_path / "p04.json"
    p04 = _make_valid_p04(timeline_descs=["案例阶段 1", "案例阶段 2", "案例阶段 3", "案例阶段 4", "案例阶段 5", "案例阶段 6", "案例阶段 7"])
    output.write_text(json.dumps(p04, ensure_ascii=False), encoding="utf-8")
    report = validate_p04_output("C001", "CASE-C001-001", case_input, output)
    assert report["status"] == "needs_review"
    assert report["checks"]["timeline_content_ok"] is False


def test_p04_content_timeline_passes(tmp_path: Path) -> None:
    """Content-based timeline descriptions must pass."""
    case_input = tmp_path / "case-input.json"
    case_input.write_text(json.dumps(_make_case_input()), encoding="utf-8")
    output = tmp_path / "p04.json"
    p04 = _make_valid_p04()
    output.write_text(json.dumps(p04, ensure_ascii=False), encoding="utf-8")
    report = validate_p04_output("C001", "CASE-C001-001", case_input, output)
    assert report["status"] == "pass"
    assert report["checks"]["timeline_content_ok"] is True


def test_p04_mechanical_summary_fails(tmp_path: Path) -> None:
    """Summary that just repeats case title must fail."""
    case_input = tmp_path / "case-input.json"
    case_input.write_text(json.dumps(_make_case_input()), encoding="utf-8")
    output = tmp_path / "p04.json"
    p04 = _make_valid_p04()
    p04["summary"] = "讲师分析测试案例"
    output.write_text(json.dumps(p04, ensure_ascii=False), encoding="utf-8")
    report = validate_p04_output("C001", "CASE-C001-001", case_input, output)
    assert report["status"] == "needs_review"
    assert report["checks"]["summary_ok"] is False


def test_p04_thresholds_in_metrics(tmp_path: Path) -> None:
    """Metrics must include applied thresholds."""
    case_input = tmp_path / "case-input.json"
    case_input.write_text(json.dumps(_make_case_input()), encoding="utf-8")
    output = tmp_path / "p04.json"
    p04 = _make_valid_p04()
    output.write_text(json.dumps(p04, ensure_ascii=False), encoding="utf-8")
    report = validate_p04_output("C001", "CASE-C001-001", case_input, output)
    metrics = report["metrics"]
    assert "required_min_evidence" in metrics
    assert "required_min_spans" in metrics
    assert "required_min_timeline" in metrics
    assert metrics["required_min_evidence"] > 0


def test_p04_small_case_threshold_scaling(tmp_path: Path) -> None:
    """Small cases (segment_count < 200) should have scaled-down thresholds."""
    case_input = tmp_path / "case-input.json"
    case_input.write_text(json.dumps(_make_case_input(count=50)), encoding="utf-8")
    output = tmp_path / "p04.json"
    p04 = _make_valid_p04(evidence_count=20, timeline_descs=["开场", "聊天展示", "分析", "方法", "结果", "复盘", "收尾"])
    output.write_text(json.dumps(p04, ensure_ascii=False), encoding="utf-8")
    report = validate_p04_output("C001", "CASE-C001-001", case_input, output)
    # With 50 segments, scale = 50/200 = 0.25, floor = max(2, int(36 * max(0.3, 0.25))) = max(2, 10) = 10
    assert report["metrics"]["required_min_evidence"] <= 20  # Should pass with scaled threshold

