"""Human-readable transcript export with speaker and active board body."""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.models import AnalysisResult, BoardSegment, SpeechSegment, TimelineEntry
from course_video_analyzer.vision.ocr_parser import board_body_text


def export_txt(result: AnalysisResult, path: Path) -> Path:
    """Write ``transcript.txt`` with speaker labels and current board text."""
    path = Path(path)
    lines: list[str] = []
    lines.append("# 课程视频分析转录")
    lines.append(f"source: {result.media.source_path}")
    lines.append(f"duration_ms: {result.media.duration_ms}")
    lines.append("")
    seen_board_lines: set[str] = set()

    timeline = sorted(result.timeline, key=lambda e: (e.start_ms, e.end_ms))
    if not timeline:
        # Fall back to raw speech / boards when merge produced nothing.
        for seg in sorted(
            result.speech_segments,
            key=lambda s: (s.start_ms, s.end_ms, s.speaker_id, s.text),
        ):
            lines.extend(_speech_block(seg, boards=[]))
            lines.append("")
        for board in sorted(
            result.board_segments,
            key=lambda b: (b.start_ms, b.end_ms, b.version_id or ""),
        ):
            block = _board_delta_block(board, seen_board_lines)
            if block:
                lines.extend(block)
                lines.append("")
    else:
        # Timeline entries attach the active board to every overlapping speech
        # segment.  Repeating the same OCR body after every short ASR sentence
        # makes a real course transcript enormous and hard to compare/read.
        # Emit each board version once, at its first timeline appearance.
        emitted_boards: set[str] = set()
        for entry in timeline:
            for board in entry.boards:
                key = _board_key(board)
                if key in emitted_boards:
                    continue
                emitted_boards.add(key)
                block = _board_delta_block(board, seen_board_lines)
                if block:
                    lines.extend(block)
                    lines.append("")
            for seg in entry.speech:
                lines.extend(_speech_block(seg, boards=None))
                lines.append("")

    # Trim trailing blank line for stable file end.
    while lines and lines[-1] == "":
        lines.pop()
    lines.append("")
    atomic_write_text(path, "\n".join(lines))
    return path


def _format_entry(entry: TimelineEntry) -> list[str]:
    if entry.speech:
        blocks: list[str] = []
        for seg in entry.speech:
            blocks.extend(_speech_block(seg, boards=entry.boards))
        return blocks
    if entry.boards:
        out: list[str] = []
        for board in entry.boards:
            out.extend(_board_only_block(board))
        return out
    return [f"[{_fmt_ms(entry.start_ms)} -> {_fmt_ms(entry.end_ms)}] (空)"]


def _speech_block(
    seg: SpeechSegment,
    *,
    boards: list[BoardSegment] | None,
) -> list[str]:
    speaker = seg.speaker_name or seg.speaker_id
    header = f"[{_fmt_ms(seg.start_ms)} -> {_fmt_ms(seg.end_ms)}] {speaker}"
    body = [header, seg.text]
    if boards:
        for board in boards:
            version = board.version_id or Path(board.image_path).stem
            board_text = board_body_text(board.text_lines, prefer_corrected=True)
            body.append(f"  课板[{version}]:")
            if board_text:
                for line in board_text.splitlines():
                    body.append(f"    {line}")
            else:
                body.append("    (无文字)")
    elif boards == []:
        body.append("  课板: (无)")
    return body


def _board_only_block(board: BoardSegment) -> list[str]:
    version = board.version_id or Path(board.image_path).stem
    board_text = board_body_text(board.text_lines, prefer_corrected=True)
    lines = [
        f"[{_fmt_ms(board.start_ms)} -> {_fmt_ms(board.end_ms)}] 课板[{version}]",
    ]
    if board_text:
        lines.extend(board_text.splitlines())
    else:
        lines.append("(无文字)")
    return lines


def _board_delta_block(board: BoardSegment, seen_lines: set[str]) -> list[str]:
    """Emit only OCR lines not already shown by an earlier board version.

    Scrolling chat/course boards repeat most visible lines in every sampled
    frame.  The full OCR stays in JSON and board artifacts; the human TXT
    should record the newly revealed information instead of duplicating the
    whole viewport hundreds of times.
    """
    body = board_body_text(board.text_lines, prefer_corrected=True)
    new_lines: list[str] = []
    for line in body.splitlines():
        key = re.sub(r"[\W_]+", "", line, flags=re.UNICODE).casefold()
        if not key or _is_repeated_board_line(key, seen_lines):
            continue
        seen_lines.add(key)
        new_lines.append(line)
    if not new_lines:
        return []
    version = board.version_id or Path(board.image_path).stem
    return [f"[{_fmt_ms(board.start_ms)} -> {_fmt_ms(board.end_ms)}] 课板[{version}]", *new_lines]


def _is_repeated_board_line(key: str, seen_lines: set[str]) -> bool:
    if key in seen_lines:
        return True
    if len(key) < 6:
        return False
    for old in seen_lines:
        if len(old) < 6:
            continue
        ratio = difflib.SequenceMatcher(None, key, old, autojunk=False).ratio()
        if ratio >= 0.90:
            return True
    return False


def _board_key(board: BoardSegment) -> str:
    return board.version_id or str(Path(board.image_path))


def _fmt_ms(ms: int) -> str:
    total_sec, millis = divmod(ms, 1000)
    hours, rem = divmod(total_sec, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
