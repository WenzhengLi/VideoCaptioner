"""Exporter unit tests (stable order / round-trip / formats)."""

from __future__ import annotations

import json
from pathlib import Path

from course_video_analyzer.exporters.boards_index import export_boards_index
from course_video_analyzer.exporters.json_exporter import (
    export_analysis_json,
    export_timeline_json,
)
from course_video_analyzer.exporters.srt_exporter import export_srt
from course_video_analyzer.exporters.txt_exporter import export_txt
from course_video_analyzer.models import (
    AnalysisResult,
    BoardRegion,
    BoardSegment,
    MediaInfo,
    OcrLine,
    SpeechSegment,
)
from course_video_analyzer.timeline.merger import merge_timeline


def _sample_result() -> AnalysisResult:
    media = MediaInfo(
        source_path=Path("lesson.mp4"),
        duration_ms=20_000,
        width=1280,
        height=720,
        fps=25.0,
    )
    s2 = SpeechSegment(
        start_ms=3000,
        end_ms=4000,
        text="第二句",
        speaker_id="spk_1",
        speaker_name="助教",
        confidence=0.8,
        source="aligned",
    )
    s1 = SpeechSegment(
        start_ms=1000,
        end_ms=2000,
        text="第一句",
        speaker_id="spk_0",
        speaker_name="导师",
        confidence=0.9,
        source="aligned",
    )
    board = BoardSegment(
        start_ms=0,
        end_ms=10_000,
        region=BoardRegion(x=10, y=20, width=400, height=300),
        image_path=Path("artifacts/boards/v1/crop.jpg"),
        version_id="v1",
        text_lines=[
            OcrLine(text="原文字", corrected_text="修订文字", confidence=0.95),
        ],
        confidence=0.7,
        source="board",
    )
    speech = [s2, s1]
    boards = [board]
    timeline = merge_timeline(speech, boards)
    return AnalysisResult(
        media=media,
        speakers={"spk_0": "导师", "spk_1": "助教"},
        speech_segments=speech,
        board_segments=boards,
        timeline=timeline,
    )


def test_analysis_json_roundtrip(tmp_path: Path) -> None:
    result = _sample_result()
    path = tmp_path / "analysis.json"
    export_analysis_json(result, path)
    loaded = AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded.media.duration_ms == result.media.duration_ms
    assert len(loaded.speech_segments) == 2
    assert loaded.speech_segments[0].text == "第一句"  # stable sort
    assert loaded.board_segments[0].text_lines[0].text == "原文字"
    assert loaded.board_segments[0].text_lines[0].corrected_text == "修订文字"
    assert loaded.board_segments[0].text_lines[0].confidence == 0.95
    assert loaded.board_segments[0].source == "board"


def test_timeline_json_stable(tmp_path: Path) -> None:
    result = _sample_result()
    path = tmp_path / "timeline.json"
    export_timeline_json(result.timeline, path)
    export_timeline_json(result.timeline, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert payload[0]["speech"][0]["text"] == "第一句"


def test_txt_prefers_corrected_board_text(tmp_path: Path) -> None:
    result = _sample_result()
    path = tmp_path / "transcript.txt"
    export_txt(result, path)
    text = path.read_text(encoding="utf-8")
    assert "导师" in text
    assert "第一句" in text
    assert "修订文字" in text
    assert "课板[v1]" in text
    assert text.count("课板[v1]") == 1


def test_srt_speech_only_no_board_body(tmp_path: Path) -> None:
    result = _sample_result()
    path = tmp_path / "transcript.srt"
    export_srt(result, path)
    text = path.read_text(encoding="utf-8")
    assert "第一句" in text
    assert "导师:" in text
    assert "修订文字" not in text
    assert "原文字" not in text
    assert "-->" in text


def test_boards_index(tmp_path: Path) -> None:
    result = _sample_result()
    path = tmp_path / "boards" / "index.json"
    export_boards_index(result, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert payload["boards"][0]["version_id"] == "v1"
    assert payload["boards"][0]["body_text"] == "修订文字"
    assert payload["boards"][0]["text_lines"][0]["text"] == "原文字"


def test_export_empty_speech_and_boards(tmp_path: Path) -> None:
    result = AnalysisResult(
        media=MediaInfo(source_path=Path("a.mp4"), duration_ms=1000),
        timeline=[],
    )
    export_analysis_json(result, tmp_path / "analysis.json")
    export_txt(result, tmp_path / "transcript.txt")
    export_srt(result, tmp_path / "transcript.srt")
    export_boards_index(result, tmp_path / "boards" / "index.json")
    loaded = AnalysisResult.model_validate_json(
        (tmp_path / "analysis.json").read_text(encoding="utf-8")
    )
    assert loaded.speech_segments == []
    assert loaded.board_segments == []


def test_txt_skips_empty_board_versions(tmp_path: Path) -> None:
    result = _sample_result()
    empty = result.board_segments[0].model_copy(
        update={"version_id": "empty", "text_lines": []}
    )
    result.board_segments.append(empty)
    result.timeline = merge_timeline(result.speech_segments, result.board_segments)
    path = tmp_path / "transcript.txt"
    export_txt(result, path)
    text = path.read_text(encoding="utf-8")
    assert "课板[empty]" not in text


def test_txt_emits_repeated_board_line_only_once(tmp_path: Path) -> None:
    result = _sample_result()
    repeated = result.board_segments[0].model_copy(
        update={
            "start_ms": 10_000,
            "end_ms": 15_000,
            "version_id": "v2",
            "text_lines": [OcrLine(text="原文字", corrected_text="修订文字")],
        }
    )
    result.board_segments.append(repeated)
    result.timeline = merge_timeline(result.speech_segments, result.board_segments)
    path = tmp_path / "transcript.txt"
    export_txt(result, path)
    text = path.read_text(encoding="utf-8")
    assert text.count("修订文字") == 1
    assert "课板[v2]" not in text


def test_txt_fuzzy_dedupes_long_ocr_typo(tmp_path: Path) -> None:
    result = _sample_result()
    first = result.board_segments[0].model_copy(
        update={
            "version_id": "v1",
            "text_lines": [OcrLine(text="现在我们可以开始聊天了")],
        }
    )
    typo = first.model_copy(
        update={
            "start_ms": 10_000,
            "end_ms": 15_000,
            "version_id": "v2",
            "text_lines": [OcrLine(text="现在我们可以开始聊夭了")],
        }
    )
    result.board_segments = [first, typo]
    result.timeline = merge_timeline(result.speech_segments, result.board_segments)
    path = tmp_path / "transcript.txt"
    export_txt(result, path)
    text = path.read_text(encoding="utf-8")
    assert "课板[v1]" in text
    assert "课板[v2]" not in text
