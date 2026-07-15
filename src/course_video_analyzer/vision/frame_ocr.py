"""Reusable board-region OCR provider for adaptive frame scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2

from course_video_analyzer.vision.adaptive_sampling import FrameOcrResult
from course_video_analyzer.vision.base import BoardOcr
from course_video_analyzer.vision.detection import BoardDetectorConfig, OpenCvBoardDetector


@dataclass
class CachedBoardFrameOcrProvider:
    """Detect a padded content region, OCR it, and return cacheable source-frame data."""

    ocr: BoardOcr
    probe_dir: Path
    artifact_dir: Path
    min_confidence: float = 0.20
    min_lines: int = 2
    region_padding_ratio: float = 0.08
    detector_min_score: float = 0.25

    def recognize_frame(
        self,
        frame_index: int,
        timestamp_ms: int,
        image_bgr: Any,
    ) -> FrameOcrResult:
        self.probe_dir.mkdir(parents=True, exist_ok=True)
        key = f"frame-{frame_index:08d}-{timestamp_ms:010d}"
        probe_path = self.probe_dir / f"{key}.jpg"
        if not cv2.imwrite(str(probe_path), image_bgr):
            raise OSError(f"无法写入 OCR 探测帧: {probe_path}")
        ocr_input_path, content_region = extract_padded_board_region(
            probe_path,
            image_bgr,
            self.probe_dir / f"{key}-board.jpg",
            padding_ratio=self.region_padding_ratio,
            detector_min_score=self.detector_min_score,
        )
        lines = list(self.ocr.recognize(ocr_input_path, self.artifact_dir / key))
        qualifying = [
            line
            for line in lines
            if line.confidence is None or line.confidence >= self.min_confidence
        ]
        text = "\n".join(line.corrected_text or line.text for line in qualifying).strip()
        confidences = [line.confidence for line in qualifying if line.confidence is not None]
        score = sum(confidences) / len(confidences) if confidences else float(bool(qualifying))
        return FrameOcrResult(
            has_text=bool(text) and len(qualifying) >= self.min_lines,
            text=text,
            text_lines=[line.model_dump(mode="json") for line in lines],
            score=float(score),
            content_region=content_region,
        )


def extract_padded_board_region(
    full_frame_path: Path,
    image_bgr: Any,
    output_path: Path,
    *,
    padding_ratio: float = 0.08,
    detector_min_score: float = 0.25,
) -> tuple[Path, tuple[int, int, int, int] | None]:
    """Locate left/right/fullscreen content and preserve a safety margin around it."""
    detector = OpenCvBoardDetector(
        BoardDetectorConfig(
            top_k=1,
            min_score=detector_min_score,
            keep_low_confidence=True,
        )
    )
    candidates = detector.detect(full_frame_path)
    if not candidates:
        return full_frame_path, None
    x1, y1, x2, y2 = candidates[0].region.as_xyxy()
    raw_region = (x1, y1, x2, y2)
    height, width = image_bgr.shape[:2]
    pad_x = round((x2 - x1) * padding_ratio)
    pad_y = round((y2 - y1) * padding_ratio)
    crop_x1 = max(0, x1 - pad_x)
    crop_y1 = max(0, y1 - pad_y)
    crop_x2 = min(width, x2 + pad_x)
    crop_y2 = min(height, y2 + pad_y)
    crop = image_bgr[crop_y1:crop_y2, crop_x1:crop_x2]
    if crop.size == 0 or not cv2.imwrite(str(output_path), crop):
        return full_frame_path, None
    return output_path, raw_region
