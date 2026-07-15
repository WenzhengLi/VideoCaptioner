"""Boards index exporter: ``artifacts/boards/index.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.models import AnalysisResult, BoardSegment
from course_video_analyzer.vision.ocr_parser import board_body_text


def export_boards_index(result: AnalysisResult, path: Path) -> Path:
    """Write a stable board catalog for download / Web preview."""
    path = Path(path)
    boards = sorted(
        result.board_segments,
        key=lambda b: (b.start_ms, b.end_ms, b.version_id or "", str(b.image_path)),
    )
    payload = {
        "count": len(boards),
        "boards": [_board_row(board) for board in boards],
    }
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def _board_row(board: BoardSegment) -> dict[str, Any]:
    body = board_body_text(board.text_lines, prefer_corrected=True)
    return {
        "version_id": board.version_id,
        "start_ms": board.start_ms,
        "end_ms": board.end_ms,
        "image_path": str(board.image_path),
        "enhanced_image_path": (
            str(board.enhanced_image_path) if board.enhanced_image_path is not None else None
        ),
        "confidence": board.confidence,
        "track_status": board.track_status,
        "page_change_reason": board.page_change_reason,
        "source": board.source,
        "region": board.region.model_dump(mode="json"),
        "text_lines": [line.model_dump(mode="json") for line in board.text_lines],
        "body_text": body,
    }
