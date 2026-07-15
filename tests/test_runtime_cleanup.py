from __future__ import annotations

import json
from pathlib import Path

import pytest

from course_video_analyzer.runtime_cleanup import (
    cleanup_disposable_artifacts,
    validate_json_output,
    validate_text_output,
)


def test_cleanup_removes_only_known_generated_directories(tmp_path: Path) -> None:
    output = tmp_path / "run"
    (output / "frames").mkdir(parents=True)
    (output / "frames" / "frame.jpg").write_bytes(b"image")
    (output / "ocr_cache").mkdir()
    (output / "ocr_cache" / "result.json").write_text("{}", encoding="utf-8")
    (output / "benchmark.json").write_text("{}", encoding="utf-8")
    (output / "notes.txt").write_text("keep", encoding="utf-8")

    report = cleanup_disposable_artifacts(output)

    assert not (output / "frames").exists()
    assert not (output / "ocr_cache").exists()
    assert (output / "benchmark.json").exists()
    assert (output / "notes.txt").read_text(encoding="utf-8") == "keep"
    assert report.removed_bytes == len(b"image") + len(b"{}")
    assert len(report.removed_paths) == 2


def test_cleanup_rejects_path_traversal_names(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()

    with pytest.raises(ValueError, match="直接子目录"):
        cleanup_disposable_artifacts(output, directory_names=["../outside"])


def test_final_outputs_must_be_non_empty_and_readable(tmp_path: Path) -> None:
    text_path = tmp_path / "result.txt"
    json_path = tmp_path / "result.json"
    text_path.write_text("完整结果", encoding="utf-8")
    json_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    assert validate_text_output(text_path) == text_path.resolve()
    assert validate_json_output(json_path) == json_path.resolve()

    empty = tmp_path / "empty.txt"
    empty.touch()
    with pytest.raises(RuntimeError, match="拒绝清理"):
        validate_text_output(empty)
