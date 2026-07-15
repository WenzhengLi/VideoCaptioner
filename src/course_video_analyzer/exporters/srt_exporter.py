"""SRT subtitle export for speech only (no board body text)."""

from __future__ import annotations

from pathlib import Path

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.models import AnalysisResult, SpeechSegment


def export_srt(result: AnalysisResult, path: Path) -> Path:
    """Write ``transcript.srt`` containing only speech cues."""
    path = Path(path)
    segments = sorted(
        result.speech_segments,
        key=lambda s: (s.start_ms, s.end_ms, s.speaker_id, s.text),
    )
    blocks: list[str] = []
    for index, seg in enumerate(segments, start=1):
        blocks.append(_cue_block(index, seg))
    content = "\n".join(blocks)
    if content:
        content += "\n"
    atomic_write_text(path, content)
    return path


def _cue_block(index: int, seg: SpeechSegment) -> str:
    speaker = seg.speaker_name or seg.speaker_id
    text = f"{speaker}: {seg.text}"
    return "\n".join(
        [
            str(index),
            f"{_srt_ts(seg.start_ms)} --> {_srt_ts(seg.end_ms)}",
            text,
            "",
        ]
    )


def _srt_ts(ms: int) -> str:
    if ms < 0:
        ms = 0
    total_sec, millis = divmod(ms, 1000)
    hours, rem = divmod(total_sec, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
