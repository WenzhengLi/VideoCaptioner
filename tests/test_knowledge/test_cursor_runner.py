import json
from pathlib import Path

import pytest

from course_video_analyzer.knowledge.cursor_runner import (
    CursorStageConfig,
    run_cursor_stage,
)


def test_cursor_stage_refuses_existing_output(tmp_path: Path) -> None:
    prompts = tmp_path / "prompts/knowledge-v001"
    prompts.mkdir(parents=True)
    (prompts / "P01-normalize.md").write_text("rules", encoding="utf-8")
    source = tmp_path / "input.txt"
    source.write_text("input", encoding="utf-8")
    output = tmp_path / "output.json"
    output.write_text(json.dumps({"old": True}), encoding="utf-8")
    agent = tmp_path / "cursor-agent.cmd"
    agent.write_text("stub", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run_cursor_stage(
            "C001",
            "P01",
            source,
            output,
            tmp_path,
            config=CursorStageConfig(cursor_agent=agent),
        )


def test_cursor_stage_rejects_unknown_stage(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_cursor_stage("C001", "P99", tmp_path / "in", tmp_path / "out", tmp_path)


def test_cursor_instruction_source_avoids_multiline_windows_prompt() -> None:
    source = Path(__file__).parents[2] / "src/course_video_analyzer/knowledge/cursor_runner.py"
    text = source.read_text(encoding="utf-8")

    assert "cursor-task.json" in text
    assert "single physical line" in text
