from pathlib import Path

import cv2
import numpy as np

from course_video_analyzer.models import BoardRegion, BoardSegment, OcrLine
from course_video_analyzer.vision.ocr_dedup import deduplicate_ocr_board_segments


def _segment(
    start_ms: int,
    end_ms: int,
    path: Path,
    text: str,
) -> BoardSegment:
    return BoardSegment(
        start_ms=start_ms,
        end_ms=end_ms,
        region=BoardRegion(x=0, y=0, width=100, height=80),
        image_path=path,
        text_lines=[OcrLine(text=text, confidence=0.9)],
    )


def test_merges_adjacent_ocr_text_duplicates_and_extends_time(tmp_path: Path) -> None:
    image = np.full((80, 100, 3), 240, dtype=np.uint8)
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    cv2.imwrite(str(first_path), image)
    cv2.imwrite(str(second_path), image)
    result = deduplicate_ocr_board_segments(
        [
            _segment(0, 1_000, first_path, "课程 第一章"),
            _segment(1_000, 2_000, second_path, "课程第一章"),
        ]
    )

    assert len(result) == 1
    assert result[0].start_ms == 0
    assert result[0].end_ms == 2_000


def test_keeps_semantically_different_ocr_pages(tmp_path: Path) -> None:
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    cv2.imwrite(str(first_path), np.zeros((80, 100, 3), dtype=np.uint8))
    cv2.imwrite(str(second_path), np.full((80, 100, 3), 255, dtype=np.uint8))
    result = deduplicate_ocr_board_segments(
        [
            _segment(0, 1_000, first_path, "第一章 基础知识"),
            _segment(1_000, 2_000, second_path, "第二章 实战案例"),
        ]
    )

    assert len(result) == 2
