"""Tests for export_chat_coach_source_packets.py."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


from scripts.export_chat_coach_source_packets import (
    _export_course,
    _find_latest_p02,
    _find_latest_p03,
    _format_ts,
    _escape_md,
)


def test_format_ts() -> None:
    assert _format_ts(0) == "00:00:00.000"
    assert _format_ts(1000) == "00:00:01.000"
    assert _format_ts(61000) == "00:01:01.000"
    assert _format_ts(3661000) == "01:01:01.000"
    assert _format_ts(2900) == "00:00:02.900"


def test_escape_md() -> None:
    assert _escape_md("# heading").startswith("\\")
    assert _escape_md("- list item").startswith("\\")
    assert _escape_md("normal text") == "normal text"
    assert _escape_md("* bullet").startswith("\\")
    assert _escape_md("微信：abc") == "微信：abc"


def test_find_latest_p02_skips_qa(tmp_path: Path) -> None:
    """P02 finder must skip qa/baseline/input/review files."""
    p02_dir = tmp_path / "02_normalized"
    p02_dir.mkdir()
    # Create files
    (p02_dir / "P02-knowledge-v002.json").write_text("{}", encoding="utf-8")
    (p02_dir / "P02-knowledge-v002-qa.json").write_text("{}", encoding="utf-8")
    (p02_dir / "P02-knowledge-v002-baseline.json").write_text("{}", encoding="utf-8")
    (p02_dir / "P02-knowledge-v002-input.json").write_text("{}", encoding="utf-8")
    (p02_dir / "P02-knowledge-v002-review-pack.json").write_text("{}", encoding="utf-8")
    (p02_dir / "P02-knowledge-v002.cursor-task.json").write_text("{}", encoding="utf-8")

    result = _find_latest_p02(tmp_path)
    assert result is not None
    assert result.name == "P02-knowledge-v002.json"


def test_find_latest_p02_returns_none_when_no_valid(tmp_path: Path) -> None:
    """Returns None when only qa/baseline files exist."""
    p02_dir = tmp_path / "02_normalized"
    p02_dir.mkdir()
    (p02_dir / "P02-knowledge-v002-qa.json").write_text("{}", encoding="utf-8")
    assert _find_latest_p02(tmp_path) is None


def test_find_latest_p03_checks_both_dirs(tmp_path: Path) -> None:
    """P03 finder checks both 02_normalized and 03_cases."""
    # 03_cases has older version
    p03_dir = tmp_path / "03_cases"
    p03_dir.mkdir()
    (p03_dir / "P03-knowledge-v002.json").write_text("{}", encoding="utf-8")

    # 02_normalized has newer version
    p02_dir = tmp_path / "02_normalized"
    p02_dir.mkdir()
    (p02_dir / "P03-knowledge-v003.json").write_text("{}", encoding="utf-8")

    result = _find_latest_p03(tmp_path)
    assert result is not None
    assert "v003" in result.name


def test_export_course_blocked_without_p02(tmp_path: Path) -> None:
    """Course without P02 must be blocked."""
    course_dir = tmp_path / "data" / "courses" / "C099"
    course_dir.mkdir(parents=True)
    # Monkey-patch DATA_ROOT and OUTPUT_ROOT
    import scripts.export_chat_coach_source_packets as mod
    old_data = mod.DATA_ROOT
    old_output = mod.OUTPUT_ROOT
    mod.DATA_ROOT = tmp_path / "data" / "courses"
    mod.OUTPUT_ROOT = tmp_path / "chat-coach" / "source-material"
    try:
        result = _export_course("C099")
        assert result["status"] == "blocked"
        assert "P02" in result.get("reason", "")
    finally:
        mod.DATA_ROOT = old_data
        mod.OUTPUT_ROOT = old_output


def test_export_course_generates_all_files(tmp_path: Path) -> None:
    """Export must generate all 6 required files."""
    # Create minimal P02
    course_dir = tmp_path / "data" / "courses" / "C099" / "02_normalized"
    course_dir.mkdir(parents=True)
    p02 = {
        "schema_version": "1.0",
        "prompt_version": "knowledge-v003-p02",
        "source_ids": ["C099"],
        "segments": [
            {
                "segment_id": "SEG-C099-000001",
                "start_ms": 1000,
                "end_ms": 2000,
                "speaker": "speaker_0",
                "content_type": "speech",
                "raw_text": "hello world",
                "normalized_text": "hello world.",
                "source_role": "instructor_explanation",
            },
            {
                "segment_id": "SEG-C099-000002",
                "start_ms": 3000,
                "end_ms": 4000,
                "speaker": "speaker_0",
                "content_type": "speech",
                "raw_text": "她说你好",
                "normalized_text": "她说你好。",
                "source_role": "actual_chat",
            },
        ],
    }
    (course_dir / "P02-knowledge-v003.json").write_text(
        json.dumps(p02, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    import scripts.export_chat_coach_source_packets as mod
    old_data = mod.DATA_ROOT
    old_output = mod.OUTPUT_ROOT
    mod.DATA_ROOT = tmp_path / "data" / "courses"
    mod.OUTPUT_ROOT = tmp_path / "chat-coach" / "source-material"
    try:
        result = _export_course("C099")
        assert result["status"] == "ok"
        assert result["segment_count"] == 2

        out_dir = tmp_path / "chat-coach" / "source-material" / "C099"
        assert (out_dir / "source-manifest.md").exists()
        assert (out_dir / "课程原文.md").exists()
        assert (out_dir / "聊天原话.md").exists()
        assert (out_dir / "讲师原话.md").exists()
        assert (out_dir / "课板原文.md").exists()
        assert (out_dir / "案例边界.md").exists()
        assert (out_dir / "提取校验.md").exists()
    finally:
        mod.DATA_ROOT = old_data
        mod.OUTPUT_ROOT = old_output


def test_export_course_segment_count_matches(tmp_path: Path) -> None:
    """课程原文.md segment count must equal P02 segment count."""
    course_dir = tmp_path / "data" / "courses" / "C099" / "02_normalized"
    course_dir.mkdir(parents=True)
    segs = []
    for i in range(10):
        segs.append({
            "segment_id": f"SEG-C099-{i+1:06d}",
            "start_ms": i * 1000,
            "end_ms": (i + 1) * 1000,
            "speaker": "speaker_0",
            "content_type": "speech",
            "raw_text": f"text {i}",
            "normalized_text": f"text {i}.",
            "source_role": "instructor_explanation",
        })
    p02 = {"schema_version": "1.0", "prompt_version": "v", "source_ids": ["C099"], "segments": segs}
    (course_dir / "P02-knowledge-v003.json").write_text(
        json.dumps(p02, ensure_ascii=False), encoding="utf-8"
    )

    import scripts.export_chat_coach_source_packets as mod
    old_data = mod.DATA_ROOT
    old_output = mod.OUTPUT_ROOT
    mod.DATA_ROOT = tmp_path / "data" / "courses"
    mod.OUTPUT_ROOT = tmp_path / "chat-coach" / "source-material"
    try:
        _export_course("C099")
        md = (tmp_path / "chat-coach" / "source-material" / "C099" / "课程原文.md").read_text(encoding="utf-8")
        assert md.count("## SEG-C099-") == 10
    finally:
        mod.DATA_ROOT = old_data
        mod.OUTPUT_ROOT = old_output


def test_export_course_role_splitting(tmp_path: Path) -> None:
    """Segments must be split by source_role into correct files."""
    course_dir = tmp_path / "data" / "courses" / "C099" / "02_normalized"
    course_dir.mkdir(parents=True)
    segs = [
        {"segment_id": "SEG-001", "start_ms": 0, "end_ms": 1000, "speaker": "s0", "content_type": "speech",
         "raw_text": "讲师说", "normalized_text": "讲师说。", "source_role": "instructor_explanation"},
        {"segment_id": "SEG-002", "start_ms": 1000, "end_ms": 2000, "speaker": "s0", "content_type": "speech",
         "raw_text": "她说好", "normalized_text": "她说好。", "source_role": "actual_chat"},
        {"segment_id": "SEG-003", "start_ms": 2000, "end_ms": 3000, "speaker": "s0", "content_type": "board_ocr",
         "raw_text": "课板文字", "normalized_text": "课板文字", "source_role": "board"},
    ]
    p02 = {"schema_version": "1.0", "prompt_version": "v", "source_ids": ["C099"], "segments": segs}
    (course_dir / "P02-knowledge-v003.json").write_text(
        json.dumps(p02, ensure_ascii=False), encoding="utf-8"
    )

    import scripts.export_chat_coach_source_packets as mod
    old_data = mod.DATA_ROOT
    old_output = mod.OUTPUT_ROOT
    mod.DATA_ROOT = tmp_path / "data" / "courses"
    mod.OUTPUT_ROOT = tmp_path / "chat-coach" / "source-material"
    try:
        _export_course("C099")
        out = tmp_path / "chat-coach" / "source-material" / "C099"
        instructor = (out / "讲师原话.md").read_text(encoding="utf-8")
        assert "SEG-001" in instructor
        assert "SEG-002" not in instructor

        chat = (out / "聊天原话.md").read_text(encoding="utf-8")
        assert "SEG-002" in chat

        board = (out / "课板原文.md").read_text(encoding="utf-8")
        assert "SEG-003" in board
    finally:
        mod.DATA_ROOT = old_data
        mod.OUTPUT_ROOT = old_output


def test_export_course_idempotent(tmp_path: Path) -> None:
    """Running twice must produce identical output."""
    course_dir = tmp_path / "data" / "courses" / "C099" / "02_normalized"
    course_dir.mkdir(parents=True)
    segs = [
        {"segment_id": "SEG-001", "start_ms": 0, "end_ms": 1000, "speaker": "s0", "content_type": "speech",
         "raw_text": "text", "normalized_text": "text.", "source_role": "instructor_explanation"},
    ]
    p02 = {"schema_version": "1.0", "prompt_version": "v", "source_ids": ["C099"], "segments": segs}
    (course_dir / "P02-knowledge-v003.json").write_text(
        json.dumps(p02, ensure_ascii=False), encoding="utf-8"
    )

    import scripts.export_chat_coach_source_packets as mod
    old_data = mod.DATA_ROOT
    old_output = mod.OUTPUT_ROOT
    mod.DATA_ROOT = tmp_path / "data" / "courses"
    mod.OUTPUT_ROOT = tmp_path / "chat-coach" / "source-material"
    try:
        _export_course("C099")
        hashes1 = {}
        out = tmp_path / "chat-coach" / "source-material" / "C099"
        for f in sorted(out.glob("*.md")):
            hashes1[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()

        _export_course("C099")
        for f in sorted(out.glob("*.md")):
            assert hashlib.sha256(f.read_bytes()).hexdigest() == hashes1[f.name]
    finally:
        mod.DATA_ROOT = old_data
        mod.OUTPUT_ROOT = old_output
