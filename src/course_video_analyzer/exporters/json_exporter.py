"""JSON exporters for full analysis and timeline slices."""

from __future__ import annotations

import json
from pathlib import Path

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.models import AnalysisResult, TimelineEntry


def sort_analysis_result(result: AnalysisResult) -> AnalysisResult:
    """Return a copy with stable list ordering for deterministic exports."""
    return AnalysisResult(
        media=result.media,
        speakers=dict(sorted(result.speakers.items(), key=lambda kv: kv[0])),
        transcript_segments=sorted(
            result.transcript_segments,
            key=lambda s: (s.start_ms, s.end_ms, s.text),
        ),
        speaker_turns=sorted(
            result.speaker_turns,
            key=lambda t: (t.start_ms, t.end_ms, t.speaker_id),
        ),
        speech_segments=sorted(
            result.speech_segments,
            key=lambda s: (s.start_ms, s.end_ms, s.speaker_id, s.text),
        ),
        board_segments=sorted(
            result.board_segments,
            key=lambda b: (b.start_ms, b.end_ms, b.version_id or "", str(b.image_path)),
        ),
        timeline=sorted(
            result.timeline,
            key=lambda e: (e.start_ms, e.end_ms, _timeline_key(e)),
        ),
        diagnostics=result.diagnostics,
    )


def export_analysis_json(result: AnalysisResult, path: Path) -> Path:
    """Write ``analysis.json`` preserving raw/corrected OCR, confidence, and source."""
    path = Path(path)
    sorted_result = sort_analysis_result(result)
    # mode="json" keeps Path as string; full field set includes OCR corrected_text.
    payload = sorted_result.model_dump(mode="json")
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def export_timeline_json(timeline: list[TimelineEntry], path: Path) -> Path:
    """Write ``timeline.json`` as a stable-ordered list of timeline entries."""
    path = Path(path)
    ordered = sorted(timeline, key=lambda e: (e.start_ms, e.end_ms, _timeline_key(e)))
    payload = [entry.model_dump(mode="json") for entry in ordered]
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def _timeline_key(entry: TimelineEntry) -> tuple[str, str]:
    speech_key = entry.speech[0].text if entry.speech else ""
    board_key = ""
    if entry.boards:
        board = entry.boards[0]
        board_key = board.version_id or str(board.image_path)
    return speech_key, board_key
