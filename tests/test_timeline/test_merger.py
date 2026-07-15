"""Unit tests for pure timeline merger."""

from __future__ import annotations

from pathlib import Path

from course_video_analyzer.models import BoardRegion, BoardSegment, OcrLine, SpeechSegment
from course_video_analyzer.timeline.merger import intervals_overlap, merge_timeline


def _speech(
    start: int,
    end: int,
    text: str = "你好",
    speaker_id: str = "spk_0",
) -> SpeechSegment:
    return SpeechSegment(
        start_ms=start,
        end_ms=end,
        text=text,
        speaker_id=speaker_id,
        source="aligned",
    )


def _board(
    start: int,
    end: int,
    version_id: str,
    image: str = "board.jpg",
) -> BoardSegment:
    return BoardSegment(
        start_ms=start,
        end_ms=end,
        region=BoardRegion(x=0, y=0, width=100, height=80),
        image_path=Path(image),
        version_id=version_id,
        text_lines=[OcrLine(text="标题", corrected_text="标题修订", confidence=0.9)],
        source="board",
    )


def test_intervals_overlap_half_open() -> None:
    assert intervals_overlap(0, 1000, 999, 2000)
    assert not intervals_overlap(0, 1000, 1000, 2000)
    assert intervals_overlap(0, 1000, 500, 600)


def test_merge_speech_attaches_overlapping_board() -> None:
    board = _board(0, 10_000, "v1")
    s1 = _speech(1000, 2000, "第一句")
    s2 = _speech(3000, 4000, "第二句")
    timeline = merge_timeline([s1, s2], [board])
    assert len(timeline) == 2
    assert timeline[0].speech[0].text == "第一句"
    assert timeline[1].speech[0].text == "第二句"
    # Same board version referenced by both speeches.
    assert timeline[0].boards[0].version_id == "v1"
    assert timeline[1].boards[0].version_id == "v1"
    assert timeline[0].boards[0] is board
    assert timeline[1].boards[0] is board


def test_merge_no_speech_keeps_boards() -> None:
    board = _board(0, 5000, "v2")
    timeline = merge_timeline([], [board])
    assert len(timeline) == 1
    assert timeline[0].speech == []
    assert timeline[0].boards[0].version_id == "v2"


def test_merge_no_boards_keeps_speech() -> None:
    s1 = _speech(0, 1000)
    timeline = merge_timeline([s1], [])
    assert len(timeline) == 1
    assert timeline[0].boards == []
    assert timeline[0].speech[0].text == "你好"


def test_merge_both_empty() -> None:
    assert merge_timeline([], []) == []


def test_merge_orphan_board_outside_speech() -> None:
    s1 = _speech(0, 1000)
    board_a = _board(0, 1000, "overlap")
    board_b = _board(5000, 6000, "orphan")
    timeline = merge_timeline([s1], [board_a, board_b])
    assert len(timeline) == 2
    speech_entry = next(e for e in timeline if e.speech)
    board_entry = next(e for e in timeline if not e.speech)
    assert speech_entry.boards[0].version_id == "overlap"
    assert board_entry.boards[0].version_id == "orphan"


def test_merge_stable_order() -> None:
    s_late = _speech(3000, 4000, "后")
    s_early = _speech(1000, 2000, "前")
    timeline = merge_timeline([s_late, s_early], [])
    assert [e.speech[0].text for e in timeline] == ["前", "后"]
