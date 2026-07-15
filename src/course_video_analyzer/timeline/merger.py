"""Pure timeline merger: associate speech with overlapping board versions."""

from __future__ import annotations

from course_video_analyzer.models import BoardSegment, SpeechSegment, TimelineEntry


def intervals_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    """Half-open intervals ``[start, end)`` overlap when ranges share any instant."""
    return start_a < end_b and start_b < end_a


def merge_timeline(
    speech: list[SpeechSegment],
    boards: list[BoardSegment],
) -> list[TimelineEntry]:
    """Build timeline entries from speech and board interval overlap.

    Rules:
    - Each speech segment becomes one entry whose ``boards`` are overlapping versions.
    - Multiple speeches overlapping the same board keep the same board object/version.
    - Boards with no overlapping speech become board-only entries.
    - Empty speech and/or boards are supported (returns ``[]`` when both empty).
    """
    speech_sorted = sorted(speech, key=lambda s: (s.start_ms, s.end_ms, s.speaker_id, s.text))
    boards_sorted = sorted(
        boards,
        key=lambda b: (b.start_ms, b.end_ms, b.version_id or "", str(b.image_path)),
    )

    entries: list[TimelineEntry] = []
    boards_with_speech: set[int] = set()

    for seg in speech_sorted:
        overlapping = [
            board
            for board in boards_sorted
            if intervals_overlap(seg.start_ms, seg.end_ms, board.start_ms, board.end_ms)
        ]
        for board in overlapping:
            boards_with_speech.add(id(board))
        entries.append(
            TimelineEntry(
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                speech=[seg],
                boards=list(overlapping),
            )
        )

    for board in boards_sorted:
        if id(board) in boards_with_speech:
            continue
        entries.append(
            TimelineEntry(
                start_ms=board.start_ms,
                end_ms=board.end_ms,
                speech=[],
                boards=[board],
            )
        )

    entries.sort(key=lambda e: (e.start_ms, e.end_ms, _entry_sort_key(e)))
    return entries


def _entry_sort_key(entry: TimelineEntry) -> tuple[str, str]:
    speech_key = entry.speech[0].text if entry.speech else ""
    board_key = ""
    if entry.boards:
        board = entry.boards[0]
        board_key = board.version_id or str(board.image_path)
    return speech_key, board_key
