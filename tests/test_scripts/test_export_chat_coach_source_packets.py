"""Tests for export_chat_coach_source_packets.py (v1.3.0)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import scripts.export_chat_coach_source_packets as exporter
from scripts.export_chat_coach_source_packets import (
    OUTPUT_FILES,
    _attach_rerun_hash_evidence,
    _escape_md,
    _export_course,
    _file_sha256,
    _find_latest_p02,
    _find_latest_p03,
    _format_ts,
    _is_excluded,
    _ordered_segments,
    _version_key,
    _write_global_report,
    main,
)


def _make_segments() -> list[dict]:
    roles = ["instructor_explanation", "actual_chat", "board", "student_question"]
    segments = []
    for index in range(10):
        role = roles[index % len(roles)]
        content_type = "board_ocr" if role == "board" else "speech"
        text = "课板聊天：你说呢" if role == "board" else f"text {index}"
        segments.append({
            "segment_id": f"SEG-C099-{index + 1:06d}",
            "start_ms": index * 1000,
            "end_ms": (index + 1) * 1000,
            "speaker": "speaker_0",
            "content_type": content_type,
            "raw_text": text,
            "normalized_text": f"{text}。",
            "source_role": role,
        })
    return segments


def _make_p02(segments: list[dict] | None = None, version: str = "v003") -> dict:
    return {
        "schema_version": "1.0",
        "prompt_version": f"knowledge-{version}-p02",
        "source_ids": ["C099"],
        "segments": segments if segments is not None else _make_segments(),
    }


def _make_p03(version: str = "v003") -> dict:
    return {
        "schema_version": "1.0",
        "prompt_version": f"knowledge-{version}-p03",
        "source_ids": ["C099"],
        "course_id": "C099",
        "cases": [{
            "case_id": "CASE-C099-001", "title": "Test",
            "start_segment_id": "SEG-C099-000001", "end_segment_id": "SEG-C099-000010",
            "completeness": "complete", "confidence": 0.8,
            "boundary_evidence": {"start_reason": "start", "end_reason": "end"},
        }],
        "uncertainties": [],
    }


def _setup_course(tmp_path: Path, *, p02: dict | None = None, p03: dict | None = None,
                  create_p03: bool = True) -> None:
    course_root = tmp_path / "data" / "courses" / "C099"
    p02_dir = course_root / "02_normalized"
    p02_dir.mkdir(parents=True)
    (p02_dir / "P02-knowledge-v003.json").write_text(
        json.dumps(p02 if p02 is not None else _make_p02(), ensure_ascii=False), encoding="utf-8",
    )
    if create_p03:
        p03_dir = course_root / "03_cases"
        p03_dir.mkdir()
        (p03_dir / "P03-knowledge-v003.json").write_text(
            json.dumps(p03 if p03 is not None else _make_p03(), ensure_ascii=False), encoding="utf-8",
        )


def _configure_roots(tmp_path: Path, monkeypatch) -> Path:
    output_root = tmp_path / "chat-coach" / "source-material"
    monkeypatch.setattr(exporter, "DATA_ROOT", tmp_path / "data" / "courses")
    monkeypatch.setattr(exporter, "OUTPUT_ROOT", output_root)
    return output_root


def _hashes(directory: Path) -> dict[str, str]:
    return {filename: _file_sha256(directory / filename) for filename in OUTPUT_FILES}


def test_format_ts() -> None:
    assert _format_ts(0) == "00:00:00.000"
    assert _format_ts(2_900) == "00:00:02.900"
    assert _format_ts(61_000) == "00:01:01.000"
    assert _format_ts(3_661_000) == "01:01:01.000"


def test_escape_md() -> None:
    assert _escape_md("# heading").startswith("\\")
    assert _escape_md("- list item").startswith("\\ ")
    assert _escape_md("* bullet").startswith("\\ ")
    assert _escape_md("微信：abc") == "微信：abc"


def test_exclusion_is_case_insensitive() -> None:
    excluded = [
        "P02-knowledge-v002-qa.json",
        "P02-knowledge-v002-QA.json",
        "P02-knowledge-v002-Baseline.json",
        "P02-knowledge-v002-INPUT.json",
        "P02-knowledge-v002-Review-Pack.json",
        "P02-knowledge-v002-REVIEW-DECISIONS.json",
        "P02-knowledge-v002.json.cursor-task.json",
    ]
    assert all(_is_excluded(filename) for filename in excluded)
    assert not _is_excluded("P02-knowledge-v010.json")


def test_version_key_and_p02_numeric_selection(tmp_path: Path) -> None:
    assert _version_key(Path("P02-knowledge-v010.json")) == (10,)
    p02_dir = tmp_path / "02_normalized"
    p02_dir.mkdir()
    for filename in ("P02-knowledge-v9.json", "P02-knowledge-v010.json", "P02-knowledge-v999-QA.json"):
        (p02_dir / filename).write_text("{}", encoding="utf-8")
    result = _find_latest_p02(tmp_path)
    assert result is not None
    assert result.name == "P02-knowledge-v010.json"


def test_p03_numeric_selection_and_exclusions(tmp_path: Path) -> None:
    (tmp_path / "02_normalized").mkdir()
    (tmp_path / "03_cases").mkdir()
    (tmp_path / "03_cases" / "P03-knowledge-v9.json").write_text("{}", encoding="utf-8")
    (tmp_path / "02_normalized" / "P03-knowledge-v010.json").write_text("{}", encoding="utf-8")
    (tmp_path / "03_cases" / "P03-knowledge-v999-INPUT.json").write_text("{}", encoding="utf-8")
    result = _find_latest_p03(tmp_path)
    assert result is not None
    assert result.name == "P03-knowledge-v010.json"


def test_export_blocks_without_formal_p02(tmp_path: Path, monkeypatch) -> None:
    _configure_roots(tmp_path, monkeypatch)
    course_dir = tmp_path / "data" / "courses" / "C099" / "02_normalized"
    course_dir.mkdir(parents=True)
    (course_dir / "P02-knowledge-v003-QA.json").write_text("{}", encoding="utf-8")
    result = _export_course("C099")
    assert result["status"] == "blocked"
    assert "P02" in result["reason"]


def test_export_blocks_without_formal_p03(tmp_path: Path, monkeypatch) -> None:
    _configure_roots(tmp_path, monkeypatch)
    _setup_course(tmp_path, create_p03=False)
    result = _export_course("C099")
    assert result["status"] == "blocked"
    assert "P03" in result["reason"]


def test_export_generates_and_rereads_all_seven_utf8_files(tmp_path: Path, monkeypatch) -> None:
    output_root = _configure_roots(tmp_path, monkeypatch)
    _setup_course(tmp_path)
    result = _export_course("C099")
    assert result["status"] == "ok"
    assert result["all_ok"] is True
    assert result["reason"] is None
    assert set(result["output_hashes"]) == set(OUTPUT_FILES)
    for filename in OUTPUT_FILES:
        assert (output_root / "C099" / filename).read_text(encoding="utf-8")


def test_full_segment_output_and_role_splitting(tmp_path: Path, monkeypatch) -> None:
    output_root = _configure_roots(tmp_path, monkeypatch)
    _setup_course(tmp_path)
    result = _export_course("C099")
    assert result["segment_count"] == 10
    course_output = output_root / "C099"
    course_text = (course_output / "课程原文.md").read_text(encoding="utf-8")
    assert course_text.count("## SEG-C099-") == 10
    assert "SEG-C099-000001" in (course_output / "讲师原话.md").read_text(encoding="utf-8")
    assert "SEG-C099-000002" in (course_output / "聊天原话.md").read_text(encoding="utf-8")
    assert "SEG-C099-000003" in (course_output / "课板原文.md").read_text(encoding="utf-8")
    assert result["checks"]["role_file_counts"]["passed"] is True


def test_markdown_special_characters_in_code_fence(tmp_path: Path, monkeypatch) -> None:
    output_root = _configure_roots(tmp_path, monkeypatch)
    segments = _make_segments()
    source = "# heading\n- item\n```nested```\n原样保留"
    segments[0]["raw_text"] = source
    segments[0]["normalized_text"] = source
    _setup_course(tmp_path, p02=_make_p02(segments))
    result = _export_course("C099")
    assert result["all_ok"] is True
    course_text = (output_root / "C099" / "课程原文.md").read_text(encoding="utf-8")
    assert "# heading" in course_text
    assert "原样保留" in course_text


def test_original_order_time_reversal_fails(tmp_path: Path, monkeypatch) -> None:
    output_root = _configure_roots(tmp_path, monkeypatch)
    segments = _make_segments()
    segments[4]["start_ms"] = 500
    segments[4]["end_ms"] = 900
    _setup_course(tmp_path, p02=_make_p02(segments))
    result = _export_course("C099")
    input_check = result["checks"]["time_monotonic_original_order"]
    assert input_check["passed"] is False
    assert input_check["violations"][0]["previous_segment_id"] == "SEG-C099-000004"
    assert input_check["violations"][0]["current_segment_id"] == "SEG-C099-000005"
    assert result["checks"]["exported_order_time_monotonic"]["passed"] is True
    assert result["checks"]["segment_set_preserved"]["passed"] is True
    assert result["status"] == "failed"
    assert result["reason"] == "one or more hard validation checks failed"
    assert result["warning_count"] == 0
    assert result["failed_checks_count"] >= 1
    ordered = _ordered_segments(segments)
    assert {s["segment_id"] for s in ordered} == {s["segment_id"] for s in segments}
    assert len(ordered) == len(segments)
    starts = [int(s["start_ms"]) for s in ordered]
    assert starts == sorted(starts)
    course_text = (output_root / "C099" / "课程原文.md").read_text(encoding="utf-8")
    assert course_text.index("## SEG-C099-000005") < course_text.index("## SEG-C099-000002")


def test_hard_gate_failure_sets_status_failed_and_cli_nonzero(
    tmp_path: Path, monkeypatch
) -> None:
    _configure_roots(tmp_path, monkeypatch)
    p03 = _make_p03()
    p03["cases"][0]["start_segment_id"] = "SEG-DOES-NOT-EXIST"
    _setup_course(tmp_path, p03=p03)
    result = _export_course("C099")
    assert result["status"] == "failed"
    assert result["reason"] == "one or more hard validation checks failed"
    assert result["failed_checks_count"] >= 1
    monkeypatch.setattr(
        "sys.argv",
        ["export_chat_coach_source_packets.py", "--courses", "C099", "--rerun-delay-seconds", "0"],
    )
    assert main() == 1


def test_original_order_failure_propagates_to_global_report(tmp_path: Path, monkeypatch) -> None:
    _configure_roots(tmp_path, monkeypatch)
    segments = _make_segments()
    segments[4]["start_ms"] = 500
    segments[4]["end_ms"] = 900
    _setup_course(tmp_path, p02=_make_p02(segments))
    first = _export_course("C099")
    time.sleep(1.1)
    second = _export_course("C099")
    results = _attach_rerun_hash_evidence([first], [second])
    report = json.loads(_write_global_report(results, 1.1).read_text(encoding="utf-8"))
    assert report["warning_count"] == 0
    assert report["failed_checks_count"] >= 1
    assert report["all_passed"] is False
    assert results[0]["status"] == "failed"
    assert results[0]["reason"] == "one or more hard validation checks failed"


def test_status_ok_never_has_failure_reason(tmp_path: Path, monkeypatch) -> None:
    _configure_roots(tmp_path, monkeypatch)
    _setup_course(tmp_path)
    result = _export_course("C099")
    assert result["status"] == "ok"
    assert result["reason"] is None


def test_p03_boundary_must_resolve_to_p02(tmp_path: Path, monkeypatch) -> None:
    _configure_roots(tmp_path, monkeypatch)
    p03 = _make_p03()
    p03["cases"][0]["start_segment_id"] = "SEG-DOES-NOT-EXIST"
    _setup_course(tmp_path, p03=p03)
    result = _export_course("C099")
    assert result["checks"]["p03_boundaries_in_p02"]["passed"] is False
    assert result["status"] == "failed"


def test_manifest_is_deterministic_and_has_no_current_time(tmp_path: Path, monkeypatch) -> None:
    output_root = _configure_roots(tmp_path, monkeypatch)
    _setup_course(tmp_path)
    _export_course("C099")
    manifest = (output_root / "C099" / "source-manifest.md").read_text(encoding="utf-8")
    assert "生成时间" not in manifest
    assert "deterministic-from-input" in manifest


def test_real_cross_second_disk_rerun_hashes_are_identical(tmp_path: Path, monkeypatch) -> None:
    output_root = _configure_roots(tmp_path, monkeypatch)
    _setup_course(tmp_path)
    _export_course("C099")
    first_hashes = _hashes(output_root / "C099")
    time.sleep(1.5)
    _export_course("C099")
    assert first_hashes == _hashes(output_root / "C099")


def test_machine_readable_report(tmp_path: Path, monkeypatch) -> None:
    _configure_roots(tmp_path, monkeypatch)
    _setup_course(tmp_path)
    first = _export_course("C099")
    time.sleep(1.5)
    second = _export_course("C099")
    results = _attach_rerun_hash_evidence([first], [second])
    report = json.loads(_write_global_report(results, 1.5).read_text(encoding="utf-8"))
    assert report["exported"] == 1
    assert report["all_passed"] is True
    assert report["failed_checks_count"] == 0
    assert report["warning_count"] == 0
    assert results[0]["status"] == "ok"
    assert results[0]["reason"] is None
