"""Parse PaddleOCR raw outputs into sorted / line-merged ``OcrLine`` values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from course_video_analyzer.models import OcrLine

# Boxes whose vertical centres differ by less than this fraction of mean height
# are treated as the same reading line.
_DEFAULT_LINE_Y_RATIO = 0.5


class OcrParseError(ValueError):
    """Raised when PaddleOCR raw payload cannot be mapped to ``OcrLine``."""


@dataclass(frozen=True)
class _RawBox:
    text: str
    confidence: float | None
    bbox: list[list[float]]


def parse_paddleocr_raw(
    raw: Any,
    *,
    confidence_threshold: float = 0.5,
    merge_same_line: bool = True,
    line_y_ratio: float = _DEFAULT_LINE_Y_RATIO,
) -> list[OcrLine]:
    """Convert PaddleOCR ``predict`` / classic ``ocr`` payloads to ``OcrLine``.

    Supported shapes:

    - PaddleOCR 3.x: ``list[{"rec_texts", "rec_scores", "rec_polys"|"dt_polys"}]``
    - Classic 2.x: ``[[ [box, (text, score)], ... ]]`` or a single page list
    - Mapping / result-like objects exposing the 3.x keys
    - empty / ``None`` → ``[]``

    Low-confidence detections are **kept** and flagged with ``low_confidence=True``.
    ``corrected_text`` is always left ``None`` (manual revision only).
    """
    if confidence_threshold < 0 or confidence_threshold > 1:
        raise OcrParseError(
            f"confidence_threshold 须在 [0, 1]，实际为 {confidence_threshold}"
        )

    boxes = _extract_raw_boxes(raw)
    if not boxes:
        return []

    ordered = sort_reading_order(boxes)
    if merge_same_line:
        ordered = merge_same_line_boxes(ordered, line_y_ratio=line_y_ratio)

    lines: list[OcrLine] = []
    for item in ordered:
        text = item.text.strip()
        if not text:
            continue
        conf = item.confidence
        if conf is not None:
            conf = float(max(0.0, min(1.0, conf)))
        low = conf is not None and conf < confidence_threshold
        lines.append(
            OcrLine(
                text=text,
                confidence=conf,
                corrected_text=None,
                bbox=item.bbox,
                low_confidence=low,
            )
        )
    return lines


def sort_reading_order(boxes: Sequence[_RawBox]) -> list[_RawBox]:
    """Top-to-bottom, then left-to-right by box centre."""

    def key(item: _RawBox) -> tuple[float, float]:
        xs = [p[0] for p in item.bbox]
        ys = [p[1] for p in item.bbox]
        return (sum(ys) / len(ys), sum(xs) / len(xs))

    return sorted(boxes, key=key)


def merge_same_line_boxes(
    boxes: Sequence[_RawBox],
    *,
    line_y_ratio: float = _DEFAULT_LINE_Y_RATIO,
) -> list[_RawBox]:
    """Merge horizontally adjacent boxes that share roughly the same baseline."""
    if not boxes:
        return []

    sorted_boxes = sort_reading_order(boxes)
    lines: list[list[_RawBox]] = [[sorted_boxes[0]]]
    for item in sorted_boxes[1:]:
        current = lines[-1]
        if _same_line(current[-1], item, line_y_ratio=line_y_ratio):
            current.append(item)
        else:
            lines.append([item])

    merged: list[_RawBox] = []
    for group in lines:
        group_sorted = sorted(group, key=lambda b: min(p[0] for p in b.bbox))
        if len(group_sorted) == 1:
            merged.append(group_sorted[0])
            continue
        text = "".join(b.text for b in group_sorted)
        confs = [b.confidence for b in group_sorted if b.confidence is not None]
        confidence = min(confs) if confs else None
        bbox = _union_bbox([b.bbox for b in group_sorted])
        merged.append(_RawBox(text=text, confidence=confidence, bbox=bbox))
    return merged


def apply_text_correction(line: OcrLine, corrected_text: str) -> OcrLine:
    """Write human revision into ``corrected_text`` without changing ``text``."""
    if not isinstance(corrected_text, str):
        raise OcrParseError(
            f"corrected_text 必须是 str，实际为 {type(corrected_text).__name__}"
        )
    # Never mutate / overwrite the original OCR evidence field.
    return line.model_copy(update={"corrected_text": corrected_text})


def apply_corrections(
    lines: Sequence[OcrLine],
    corrections: Mapping[int, str],
) -> list[OcrLine]:
    """Apply index→revision map; untouched lines keep ``corrected_text=None``."""
    result: list[OcrLine] = []
    for index, line in enumerate(lines):
        if index in corrections:
            result.append(apply_text_correction(line, corrections[index]))
        else:
            result.append(line)
    return result


def board_body_text(lines: Sequence[OcrLine], *, prefer_corrected: bool = True) -> str:
    """Aggregate board text; prefer ``corrected_text`` when present and requested.

    TASK-008 / export consumers should call with ``prefer_corrected=True`` for
    human-facing views, and keep raw ``text`` for evidence / audit.
    """
    parts: list[str] = []
    for line in lines:
        if prefer_corrected and line.corrected_text is not None:
            piece = line.corrected_text.strip()
        else:
            piece = line.text.strip()
        if piece:
            parts.append(piece)
    return "\n".join(parts)


def _extract_raw_boxes(raw: Any) -> list[_RawBox]:
    if raw is None:
        return []

    # Single OCRResult / Mapping (PaddleOCR 3.x page).
    if _looks_like_v3_page(raw):
        return _boxes_from_v3_page(raw)

    if isinstance(raw, dict) and "res" in raw:
        return _extract_raw_boxes(raw["res"])

    if not isinstance(raw, (list, tuple)):
        # OCRResult behaves like Mapping but may not be dict.
        if hasattr(raw, "keys") and _looks_like_v3_page(raw):
            return _boxes_from_v3_page(raw)
        raise OcrParseError(
            f"PaddleOCR 原始结果应为 list 或含 rec_texts 的映射，实际为 {type(raw).__name__}"
        )

    if not raw:
        return []

    # list of v3 pages
    if all(_looks_like_v3_page(item) for item in raw):
        boxes: list[_RawBox] = []
        for page in raw:
            boxes.extend(_boxes_from_v3_page(page))
        return boxes

    # Classic nested page: [ [box, (text, score)], ... ]
    first = raw[0]
    if isinstance(first, (list, tuple)) and first and _looks_like_classic_item(first[0]):
        boxes = []
        for page in raw:
            if page is None:
                continue
            if not isinstance(page, (list, tuple)):
                raise OcrParseError("经典 PaddleOCR 分页结果项应为 list")
            boxes.extend(_boxes_from_classic_page(page))
        return boxes

    # Classic flat page
    if _looks_like_classic_item(first):
        return _boxes_from_classic_page(raw)

    # Sometimes predict returns [[v3_page]] wrapping
    if isinstance(first, (list, tuple)) and first and _looks_like_v3_page(first[0]):
        boxes = []
        for page in first:
            boxes.extend(_boxes_from_v3_page(page))
        return boxes

    raise OcrParseError(
        "无法识别的 PaddleOCR 结果结构；期望 PP-OCRv3+ 的 rec_texts/"
        "rec_scores/rec_polys，或经典 [[box, (text, score)], ...] 格式。"
    )


def _looks_like_v3_page(value: Any) -> bool:
    if value is None:
        return False
    getter = None
    if isinstance(value, Mapping):
        getter = value.get
    elif hasattr(value, "get") and callable(value.get):
        getter = value.get
    elif hasattr(value, "__getitem__") and (
        "rec_texts" in value if hasattr(value, "__contains__") else False
    ):
        return True
    else:
        return False
    return getter("rec_texts") is not None or getter("dt_polys") is not None


def _boxes_from_v3_page(page: Any) -> list[_RawBox]:
    get = page.get if hasattr(page, "get") else lambda k, d=None: page[k] if k in page else d
    texts = get("rec_texts") or []
    scores = get("rec_scores") or []
    polys = get("rec_polys")
    if polys is None or (hasattr(polys, "__len__") and len(polys) == 0):
        polys = get("dt_polys") or []

    texts_list = list(texts)
    scores_list = list(scores) if scores is not None else []
    polys_list = list(polys)

    n = len(texts_list)
    if n == 0:
        return []
    if len(polys_list) not in (0, n):
        raise OcrParseError(
            f"rec_texts({n}) 与多边形数量({len(polys_list)})不一致"
        )

    boxes: list[_RawBox] = []
    for i in range(n):
        text = texts_list[i]
        if text is None:
            continue
        text_str = str(text).strip()
        if not text_str:
            continue
        conf: float | None
        if i < len(scores_list) and scores_list[i] is not None:
            conf = float(scores_list[i])
        else:
            conf = None
        if i < len(polys_list):
            bbox = _normalize_bbox(polys_list[i])
        else:
            bbox = [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]
        boxes.append(_RawBox(text=text_str, confidence=conf, bbox=bbox))
    return boxes


def _looks_like_classic_item(item: Any) -> bool:
    if not isinstance(item, (list, tuple)) or len(item) < 2:
        return False
    box, payload = item[0], item[1]
    try:
        if len(box) < 4:
            return False
    except TypeError:
        return False
    if isinstance(payload, (list, tuple)) and len(payload) >= 1:
        return True
    return isinstance(payload, str)


def _boxes_from_classic_page(page: Sequence[Any]) -> list[_RawBox]:
    boxes: list[_RawBox] = []
    for index, item in enumerate(page):
        if item is None:
            continue
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            raise OcrParseError(f"经典结果项[{index}] 应为 [box, (text, score)]")
        box, payload = item[0], item[1]
        if isinstance(payload, (list, tuple)):
            text = str(payload[0]) if payload else ""
            conf = float(payload[1]) if len(payload) > 1 and payload[1] is not None else None
        elif isinstance(payload, str):
            text = payload
            conf = None
        else:
            raise OcrParseError(f"经典结果项[{index}] 文本载荷无法解析")
        text = text.strip()
        if not text:
            continue
        boxes.append(_RawBox(text=text, confidence=conf, bbox=_normalize_bbox(box)))
    return boxes


def _normalize_bbox(box: Any) -> list[list[float]]:
    if hasattr(box, "tolist"):
        box = box.tolist()
    if not isinstance(box, (list, tuple)):
        raise OcrParseError(f"文字框应为点序列，实际为 {type(box).__name__}")
    points: list[list[float]] = []
    for point in box:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise OcrParseError("文字框每个点需要至少两个坐标")
        points.append([float(point[0]), float(point[1])])
    if len(points) < 4:
        raise OcrParseError(f"文字框至少需要 4 个点，实际为 {len(points)}")
    return points


def _union_bbox(boxes: Sequence[list[list[float]]]) -> list[list[float]]:
    xs = [p[0] for box in boxes for p in box]
    ys = [p[1] for box in boxes for p in box]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _same_line(a: _RawBox, b: _RawBox, *, line_y_ratio: float) -> bool:
    ay0 = min(p[1] for p in a.bbox)
    ay1 = max(p[1] for p in a.bbox)
    by0 = min(p[1] for p in b.bbox)
    by1 = max(p[1] for p in b.bbox)
    ac = (ay0 + ay1) / 2.0
    bc = (by0 + by1) / 2.0
    mean_h = max(((ay1 - ay0) + (by1 - by0)) / 2.0, 1.0)
    return abs(ac - bc) <= mean_h * line_y_ratio
