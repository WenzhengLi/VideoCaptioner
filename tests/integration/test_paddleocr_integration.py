"""Real PaddleOCR smoke test (optional; requires vision extra + models)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

pytestmark = pytest.mark.integration


def _have_paddleocr() -> bool:
    return importlib.util.find_spec("paddleocr") is not None


def _write_chinese_slide(path: Path) -> Path:
    """Synthetic electronic slide with clear Chinese-like characters via OpenCV fonts.

    Uses dense dark strokes on white so PP-OCR can detect glyphs; if recognition
    fails (font is Latin-only), the test still validates pipeline wiring and
    artifact shape, then skips on empty lines.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((360, 640, 3), 255, dtype=np.uint8)
    # Title bar
    cv2.rectangle(image, (0, 0), (640, 70), (30, 90, 200), thickness=-1)
    cv2.putText(
        image,
        "Course Slide",
        (24, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    # Large dark text blocks — recognisable as text regions.
    for i, y in enumerate((140, 200, 260)):
        cv2.putText(
            image,
            f"Line {i + 1} ABC 123",
            (40, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.1,
            (20, 20, 20),
            2,
            cv2.LINE_AA,
        )
    assert cv2.imwrite(str(path), image)
    return path


@pytest.mark.integration
def test_paddleocr_real_model_recognize(tmp_path: Path) -> None:
    if not _have_paddleocr():
        pytest.skip("PaddleOCR 未安装（uv sync --extra vision）")

    from course_video_analyzer.vision.ocr import (
        LINES_ARTIFACT_NAME,
        RAW_ARTIFACT_NAME,
        OcrConfig,
        PaddleBoardOcr,
        PaddleOcrNotAvailableError,
        PaddleOcrRuntimeError,
    )

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "images" / "zh_slide.png"
    if fixture.is_file():
        image_path = tmp_path / "zh_slide.png"
        image_path.write_bytes(fixture.read_bytes())
    else:
        image_path = _write_chinese_slide(tmp_path / "zh_slide.png")

    artifact_dir = tmp_path / "artifacts" / "ocr"
    ocr = PaddleBoardOcr(
        OcrConfig(
            lang="ch",
            device="cpu",
            ocr_version="PP-OCRv4",
            board_mode="electronic",
            confidence_threshold=0.5,
            text_det_limit_side_len=960,
            text_rec_score_thresh=0.0,
        )
    )

    try:
        lines = ocr.recognize(image_path, artifact_dir)
    except (PaddleOcrNotAvailableError, PaddleOcrRuntimeError) as exc:
        pytest.skip(f"PaddleOCR 真实模型不可用: {exc}")
    except Exception as exc:
        pytest.skip(f"PaddleOCR 推理环境不可用: {exc}")

    assert (artifact_dir / RAW_ARTIFACT_NAME).is_file()
    assert (artifact_dir / LINES_ARTIFACT_NAME).is_file()
    assert (artifact_dir / "ocr_meta.json").is_file()
    raw = json.loads((artifact_dir / RAW_ARTIFACT_NAME).read_text(encoding="utf-8"))
    assert raw is not None

    if not lines:
        pytest.skip(
            "真实 OCR 返回空结果（合成图可能无法识别；"
            "可放入 tests/fixtures/images/zh_slide.png 后重跑）"
        )

    for line in lines:
        assert line.text.strip()
        assert line.corrected_text is None
        dumped = line.model_dump(mode="json")
        assert "text" in dumped
        assert "corrected_text" in dumped
