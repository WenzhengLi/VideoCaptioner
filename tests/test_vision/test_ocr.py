"""Unit tests for PaddleOCR adapter / parser (fake engine — no model download)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from course_video_analyzer.models import OcrLine
from course_video_analyzer.vision.ocr import (
    LINES_ARTIFACT_NAME,
    META_ARTIFACT_NAME,
    RAW_ARTIFACT_NAME,
    OcrConfig,
    PaddleBoardOcr,
    PaddleOcrNotAvailableError,
    _import_paddleocr,
)
from course_video_analyzer.vision.ocr_parser import (
    apply_corrections,
    apply_text_correction,
    board_body_text,
    merge_same_line_boxes,
    parse_paddleocr_raw,
    sort_reading_order,
)


def _box(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


class FakePaddleEngine:
    """Minimal predict()-compatible stub used by unit tests."""

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def predict(self, image_path: str, **kwargs: Any) -> Any:
        self.calls.append((image_path, dict(kwargs)))
        return self.payload


def _write_tiny_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((64, 128, 3), 255, dtype=np.uint8)
    cv2.putText(image, "Hi", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    assert cv2.imwrite(str(path), image)
    return path


# --- parser -----------------------------------------------------------------


def test_parse_v3_payload_sorts_and_merges_same_line() -> None:
    raw = [
        {
            "rec_texts": ["世界", "你好", "第二行"],
            "rec_scores": [0.91, 0.95, 0.88],
            "rec_polys": [
                _box(80, 10, 140, 40),  # 世界 — right on first line
                _box(10, 12, 70, 42),  # 你好 — left on first line
                _box(10, 80, 100, 110),  # 第二行
            ],
        }
    ]
    lines = parse_paddleocr_raw(raw, confidence_threshold=0.5, merge_same_line=True)
    assert len(lines) == 2
    assert lines[0].text == "你好世界"
    assert lines[1].text == "第二行"
    assert lines[0].corrected_text is None
    assert lines[0].low_confidence is False


def test_parse_keeps_low_confidence_and_flags() -> None:
    raw = {
        "rec_texts": ["模糊字"],
        "rec_scores": [0.2],
        "rec_polys": [_box(0, 0, 40, 20)],
    }
    lines = parse_paddleocr_raw(raw, confidence_threshold=0.5)
    assert len(lines) == 1
    assert lines[0].text == "模糊字"
    assert lines[0].confidence == pytest.approx(0.2)
    assert lines[0].low_confidence is True
    assert lines[0].corrected_text is None


def test_parse_empty_and_none() -> None:
    assert parse_paddleocr_raw(None) == []
    assert parse_paddleocr_raw([]) == []
    assert parse_paddleocr_raw({"rec_texts": [], "rec_scores": [], "rec_polys": []}) == []


def test_parse_classic_2x_shape() -> None:
    classic = [
        [
            [_box(10, 10, 50, 30), ("课板", 0.97)],
            [_box(60, 12, 100, 32), ("文字", 0.93)],
        ]
    ]
    lines = parse_paddleocr_raw(classic, merge_same_line=True)
    assert len(lines) == 1
    assert lines[0].text == "课板文字"


def test_sort_reading_order_top_then_left() -> None:
    from course_video_analyzer.vision.ocr_parser import _RawBox

    # Same baseline (y centres equal) → left-to-right; then lower line.
    boxes = [
        _RawBox("B", 0.9, _box(100, 10, 140, 40)),
        _RawBox("A", 0.9, _box(10, 10, 50, 40)),
        _RawBox("C", 0.9, _box(10, 100, 50, 130)),
    ]
    ordered = sort_reading_order(boxes)
    assert [b.text for b in ordered] == ["A", "B", "C"]


def test_merge_same_line_uses_min_confidence() -> None:
    from course_video_analyzer.vision.ocr_parser import _RawBox

    boxes = [
        _RawBox("左", 0.9, _box(0, 0, 40, 20)),
        _RawBox("右", 0.4, _box(50, 2, 90, 22)),
    ]
    merged = merge_same_line_boxes(boxes)
    assert len(merged) == 1
    assert merged[0].text == "左右"
    assert merged[0].confidence == pytest.approx(0.4)


def test_apply_text_correction_does_not_overwrite_text() -> None:
    line = OcrLine(text="原始", confidence=0.9, corrected_text=None, bbox=_box(0, 0, 1, 1))
    updated = apply_text_correction(line, "修订后")
    assert updated.text == "原始"
    assert updated.corrected_text == "修订后"


def test_apply_corrections_by_index() -> None:
    lines = [
        OcrLine(text="一", confidence=0.9),
        OcrLine(text="二", confidence=0.8),
    ]
    updated = apply_corrections(lines, {1: "贰"})
    assert updated[0].corrected_text is None
    assert updated[1].text == "二"
    assert updated[1].corrected_text == "贰"


def test_board_body_prefers_corrected() -> None:
    lines = [
        OcrLine(text="原1", confidence=0.9, corrected_text="修1"),
        OcrLine(text="原2", confidence=0.9, corrected_text=None),
    ]
    assert board_body_text(lines, prefer_corrected=True) == "修1\n原2"
    assert board_body_text(lines, prefer_corrected=False) == "原1\n原2"


def test_ocr_line_serializes_text_and_correction() -> None:
    line = OcrLine(
        text="原文",
        confidence=0.55,
        corrected_text="修订",
        bbox=_box(1, 2, 3, 4),
        low_confidence=False,
    )
    payload = line.model_dump(mode="json")
    assert payload["text"] == "原文"
    assert payload["corrected_text"] == "修订"
    restored = OcrLine.model_validate(payload)
    assert restored.text == "原文"
    assert restored.corrected_text == "修订"


# --- BoardOcr adapter -------------------------------------------------------


def test_recognize_uses_fake_engine_and_writes_artifacts(tmp_path: Path) -> None:
    image = _write_tiny_png(tmp_path / "board.png")
    artifact_dir = tmp_path / "artifacts"
    payload = [
        {
            "rec_texts": ["你好", "世界"],
            "rec_scores": [0.96, 0.33],
            "rec_polys": [_box(10, 10, 40, 30), _box(50, 12, 90, 32)],
        }
    ]
    engine = FakePaddleEngine(payload)
    ocr = PaddleBoardOcr(
        OcrConfig(skip_enhance=True, confidence_threshold=0.5, merge_same_line=True),
        engine=engine,
    )
    assert ocr.engine_loaded is True

    lines = ocr.recognize(image, artifact_dir)
    assert len(engine.calls) == 1
    assert Path(engine.calls[0][0]) == image or engine.calls[0][0].endswith("board.png")

    assert len(lines) == 1
    assert lines[0].text == "你好世界"
    assert lines[0].confidence == pytest.approx(0.33)
    assert lines[0].low_confidence is True
    assert lines[0].corrected_text is None

    raw_path = artifact_dir / RAW_ARTIFACT_NAME
    lines_path = artifact_dir / LINES_ARTIFACT_NAME
    meta_path = artifact_dir / META_ARTIFACT_NAME
    assert raw_path.is_file()
    assert lines_path.is_file()
    assert meta_path.is_file()
    raw_json = json.loads(raw_path.read_text(encoding="utf-8"))
    assert isinstance(raw_json, list)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["line_count"] == 1
    assert meta["low_confidence_count"] == 1
    assert meta["enhance"]["skipped"] is True


def test_recognize_runs_enhance_by_default(tmp_path: Path) -> None:
    image = _write_tiny_png(tmp_path / "board.png")
    artifact_dir = tmp_path / "artifacts"
    payload = {
        "rec_texts": ["课"],
        "rec_scores": [0.99],
        "rec_polys": [_box(0, 0, 20, 20)],
    }
    engine = FakePaddleEngine(payload)
    ocr = PaddleBoardOcr(OcrConfig(board_mode="electronic"), engine=engine)
    lines = ocr.recognize(image, artifact_dir)
    assert len(lines) == 1
    assert (artifact_dir / "enhanced.png").is_file()
    assert (artifact_dir / "original.png").is_file()
    meta = json.loads((artifact_dir / META_ARTIFACT_NAME).read_text(encoding="utf-8"))
    assert meta["enhance"]["skipped"] is False
    assert meta["enhance"]["mode"] == "electronic"
    # Engine should see the enhanced artifact, not only the source.
    called = Path(engine.calls[0][0])
    assert called.name == "enhanced.png"


def test_apply_corrections_persists_artifacts(tmp_path: Path) -> None:
    lines = [
        OcrLine(text="错字", confidence=0.7, bbox=_box(0, 0, 10, 10)),
    ]
    ocr = PaddleBoardOcr(engine=FakePaddleEngine([]))
    updated = ocr.apply_corrections(lines, {0: "正字"}, artifact_dir=tmp_path)
    assert updated[0].text == "错字"
    assert updated[0].corrected_text == "正字"
    dumped = json.loads((tmp_path / LINES_ARTIFACT_NAME).read_text(encoding="utf-8"))
    assert dumped[0]["text"] == "错字"
    assert dumped[0]["corrected_text"] == "正字"
    body = (tmp_path / "board_body.txt").read_text(encoding="utf-8")
    assert body.strip() == "正字"


def test_missing_image_raises(tmp_path: Path) -> None:
    ocr = PaddleBoardOcr(engine=FakePaddleEngine([]))
    with pytest.raises(FileNotFoundError, match="不存在"):
        ocr.recognize(tmp_path / "nope.png", tmp_path / "out")


def test_import_paddleocr_is_lazy() -> None:
    """Constructor with fake engine must not require paddleocr installed."""
    ocr = PaddleBoardOcr(engine=FakePaddleEngine([]))
    assert ocr.engine_loaded is True
    # Real import path still exists for integration; unit path never calls it.
    try:
        _import_paddleocr()
    except PaddleOcrNotAvailableError:
        pass
