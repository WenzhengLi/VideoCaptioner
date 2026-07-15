"""Parse FunASR raw outputs into ``TranscriptSegment`` intervals."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from course_video_analyzer.models import TranscriptSegment

# Contentful characters for empty-segment filtering (CJK / word chars).
_CONTENT_RE = re.compile(r"[\w\u4e00-\u9fff]", re.UNICODE)


class FunASRParseError(ValueError):
    """Raised when FunASR raw payload cannot be mapped to transcript segments."""


def normalize_transcript_text(text: str) -> str:
    """Normalize whitespace/punctuation forms while keeping readable text.

    Uses NFKC so full-width Latin/digits become half-width; collapses runs of
    whitespace to a single space; strips ends. Chinese sentence punctuation is
    preserved.
    """
    if not isinstance(text, str):
        raise FunASRParseError(f"文本字段必须是 str，实际为 {type(text).__name__}")
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def parse_funasr_raw(raw: Any) -> list[TranscriptSegment]:
    """Convert FunASR ``generate()`` return value into sorted segments.

    Supported shapes:

    - ``list[{"sentence_info": [...], ...}]`` (preferred sentence timestamps)
    - ``list[{"text": "...", "timestamp": [[s, e], ...], ...}]`` (utterance fallback)
    - empty list / empty text → ``[]``

    Raises:
        FunASRParseError: unexpected structure or illegal timestamps.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise FunASRParseError(
            f"FunASR 原始结果应为 list，实际为 {type(raw).__name__}；"
            "请确认使用 AutoModel.generate() 的返回值。"
        )
    if not raw:
        return []

    segments: list[TranscriptSegment] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise FunASRParseError(
                f"FunASR 结果项[{index}] 应为 dict，实际为 {type(item).__name__}"
            )
        if "sentence_info" in item:
            sentence_info = item["sentence_info"]
            if sentence_info is None:
                continue
            if not isinstance(sentence_info, list):
                raise FunASRParseError(
                    f"FunASR 结果项[{index}].sentence_info 应为 list，"
                    f"实际为 {type(sentence_info).__name__}"
                )
            for s_index, sentence in enumerate(sentence_info):
                segment = _sentence_to_segment(sentence, path=f"[{index}].sentence_info[{s_index}]")
                if segment is not None:
                    segments.append(segment)
            continue

        if "text" in item:
            segment = _utterance_to_segment(item, path=f"[{index}]")
            if segment is not None:
                segments.append(segment)
            continue

        raise FunASRParseError(
            f"FunASR 结果项[{index}] 缺少 sentence_info 或 text 字段，"
            f"键为 {sorted(item.keys())}"
        )

    segments.sort(key=lambda seg: (seg.start_ms, seg.end_ms))
    return segments


def _sentence_to_segment(sentence: Any, *, path: str) -> TranscriptSegment | None:
    if not isinstance(sentence, dict):
        raise FunASRParseError(f"{path} 应为 dict，实际为 {type(sentence).__name__}")

    raw_text = sentence.get("raw_text")
    if raw_text is None:
        raw_text = sentence.get("text")
    if raw_text is None:
        raise FunASRParseError(f"{path} 缺少 text/raw_text")

    if not isinstance(raw_text, str):
        raise FunASRParseError(f"{path}.text 必须是 str")

    raw_text = raw_text.strip()
    text = normalize_transcript_text(str(sentence.get("text", raw_text)))
    if not text or not _CONTENT_RE.search(text):
        return None

    start_ms, end_ms = _extract_ms_range(sentence, path=path)
    confidence = _extract_confidence(sentence)
    words = _extract_words(sentence, text=str(sentence.get("text", raw_text)))

    return TranscriptSegment(
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        raw_text=raw_text if raw_text else None,
        confidence=confidence,
        words=words,
        source="funasr",
    )


def _utterance_to_segment(item: dict[str, Any], *, path: str) -> TranscriptSegment | None:
    raw_text_value = item.get("raw_text", item.get("text"))
    if not isinstance(raw_text_value, str):
        raise FunASRParseError(f"{path}.text 必须是 str")

    raw_text = raw_text_value.strip()
    text = normalize_transcript_text(str(item.get("text", raw_text)))
    if not text or not _CONTENT_RE.search(text):
        return None

    if "start" in item or "end" in item or "start_ms" in item or "end_ms" in item:
        start_ms, end_ms = _extract_ms_range(item, path=path)
    else:
        timestamp = item.get("timestamp")
        if not timestamp:
            raise FunASRParseError(
                f"{path} 无句级时间戳且缺少 timestamp，无法构造区间"
            )
        start_ms, end_ms = _range_from_timestamp_list(timestamp, path=f"{path}.timestamp")

    confidence = _extract_confidence(item)
    words = _extract_words(item, text=str(item.get("text", raw_text)))
    return TranscriptSegment(
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        raw_text=raw_text if raw_text else None,
        confidence=confidence,
        words=words,
        source="funasr",
    )


def _extract_ms_range(payload: dict[str, Any], *, path: str) -> tuple[int, int]:
    start_raw = payload.get("start_ms", payload.get("start"))
    end_raw = payload.get("end_ms", payload.get("end"))
    if start_raw is None or end_raw is None:
        timestamp = payload.get("timestamp")
        if timestamp:
            return _range_from_timestamp_list(timestamp, path=f"{path}.timestamp")
        raise FunASRParseError(f"{path} 缺少 start/end（或 start_ms/end_ms）时间戳")
    return _coerce_ms_pair(start_raw, end_raw, path=path)


def _range_from_timestamp_list(timestamp: Any, *, path: str) -> tuple[int, int]:
    if not isinstance(timestamp, list) or not timestamp:
        raise FunASRParseError(f"{path} 应为非空 list[[start, end], ...]")
    first = timestamp[0]
    last = timestamp[-1]
    if (
        not isinstance(first, (list, tuple))
        or not isinstance(last, (list, tuple))
        or len(first) < 2
        or len(last) < 2
    ):
        raise FunASRParseError(f"{path} 元素应为 [start, end]")
    return _coerce_ms_pair(first[0], last[1], path=path)


def _coerce_ms_pair(start_raw: Any, end_raw: Any, *, path: str) -> tuple[int, int]:
    try:
        start_ms = int(round(float(start_raw)))
        end_ms = int(round(float(end_raw)))
    except (TypeError, ValueError) as exc:
        raise FunASRParseError(
            f"{path} 时间戳无法转换为整数毫秒: start={start_raw!r}, end={end_raw!r}"
        ) from exc

    if start_ms < 0 or end_ms < 0:
        raise FunASRParseError(
            f"{path} 时间戳不能为负: start_ms={start_ms}, end_ms={end_ms}"
        )
    if end_ms <= start_ms:
        raise FunASRParseError(
            f"{path} 非法时间戳区间 [start_ms, end_ms)=[{start_ms}, {end_ms})，"
            "要求 end_ms > start_ms"
        )
    return start_ms, end_ms


def _extract_confidence(payload: dict[str, Any]) -> float | None:
    for key in ("confidence", "score", "confidence_score"):
        if key not in payload or payload[key] is None:
            continue
        try:
            value = float(payload[key])
        except (TypeError, ValueError):
            continue
        if 0.0 <= value <= 1.0:
            return value
        if 0.0 <= value <= 100.0:
            return value / 100.0
    return None


def _extract_words(payload: dict[str, Any], *, text: str) -> list[dict[str, Any]]:
    """Best-effort word/char timing from FunASR ``timestamp`` arrays."""
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, list) or not timestamp:
        return []

    # Prefer space-separated tokens when present (FunASR raw_text style).
    tokens = [t for t in text.split() if t]
    chars = [ch for ch in text if not ch.isspace()]
    units = tokens if len(tokens) == len(timestamp) else chars

    words: list[dict[str, Any]] = []
    for index, pair in enumerate(timestamp):
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        try:
            start_ms = int(round(float(pair[0])))
            end_ms = int(round(float(pair[1])))
        except (TypeError, ValueError):
            continue
        if end_ms <= start_ms or start_ms < 0:
            continue
        token = units[index] if index < len(units) else ""
        if not token:
            continue
        words.append({"start_ms": start_ms, "end_ms": end_ms, "text": token})
    return words
