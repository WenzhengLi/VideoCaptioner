"""Post-OCR deduplication for adjacent board versions."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

import cv2

from course_video_analyzer.models import BoardSegment
from course_video_analyzer.vision.dedup import BoardPageDeduper
from course_video_analyzer.vision.ocr_parser import board_body_text


@dataclass(frozen=True)
class OcrDedupConfig:
    text_similarity_threshold: float = 0.92
    image_supported_text_threshold: float = 0.75


def deduplicate_ocr_board_segments(
    segments: list[BoardSegment],
    *,
    config: OcrDedupConfig | None = None,
    image_deduper: BoardPageDeduper | None = None,
) -> list[BoardSegment]:
    """Merge consecutive versions when OCR text and/or board image agree.

    Full OCR remains preserved in each artifact directory.  This function only
    reduces the final timeline/index representation after OCR has supplied a
    semantic similarity signal.
    """
    if not segments:
        return []
    cfg = config or OcrDedupConfig()
    deduper = image_deduper or BoardPageDeduper()
    ordered = sorted(segments, key=lambda item: (item.start_ms, item.end_ms))
    output = [ordered[0]]
    for current in ordered[1:]:
        previous = output[-1]
        text_similarity = _text_similarity(previous, current)
        image_same = _images_same(previous.image_path, current.image_path, deduper)
        duplicate = text_similarity >= cfg.text_similarity_threshold or (
            image_same and text_similarity >= cfg.image_supported_text_threshold
        )
        if not duplicate:
            output.append(current)
            continue
        preferred = _prefer_richer_segment(previous, current)
        output[-1] = preferred.model_copy(
            update={
                "start_ms": previous.start_ms,
                "end_ms": max(previous.end_ms, current.end_ms),
            }
        )
    return output


def _text_similarity(first: BoardSegment, second: BoardSegment) -> float:
    first_text = _normalize(board_body_text(first.text_lines, prefer_corrected=True))
    second_text = _normalize(board_body_text(second.text_lines, prefer_corrected=True))
    if not first_text or not second_text:
        return 0.0
    return difflib.SequenceMatcher(None, first_text, second_text, autojunk=False).ratio()


def _images_same(first_path: Path, second_path: Path, deduper: BoardPageDeduper) -> bool:
    first = cv2.imread(str(first_path), cv2.IMREAD_COLOR)
    second = cv2.imread(str(second_path), cv2.IMREAD_COLOR)
    if first is None or second is None:
        return False
    return deduper.is_same_page(first, second)


def _prefer_richer_segment(first: BoardSegment, second: BoardSegment) -> BoardSegment:
    def score(segment: BoardSegment) -> tuple[int, float]:
        text_length = len(_normalize(board_body_text(segment.text_lines, prefer_corrected=True)))
        confidence = sum(line.confidence or 0.0 for line in segment.text_lines)
        return text_length, confidence

    return second if score(second) > score(first) else first


def _normalize(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()
