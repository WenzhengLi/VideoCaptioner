"""Parse WeSpeaker ``diarize()`` outputs into ``SpeakerTurn`` intervals."""

from __future__ import annotations

from typing import Any, Literal

from course_video_analyzer.models import SpeakerTurn

SourceName = Literal["wespeaker", "campplus"]


class WeSpeakerParseError(ValueError):
    """Raised when WeSpeaker/CAM++ raw diarization output cannot be mapped."""


def seconds_to_ms(value: Any, *, path: str) -> int:
    """Convert a numeric second timestamp to a non-negative integer millisecond."""
    try:
        ms = int(round(float(value) * 1000.0))
    except (TypeError, ValueError) as exc:
        raise WeSpeakerParseError(f"{path} 无法转换为秒时间戳: {value!r}") from exc
    if ms < 0:
        raise WeSpeakerParseError(f"{path} 时间戳不能为负: {ms} ms (raw={value!r})")
    return ms


def speaker_id_from_label(label: Any) -> str:
    """Normalize a clustering label to ``Speaker N`` form.

    Accepts ints, numpy integers, or strings like ``\"0\"`` / ``\"Speaker 0\"``.
    """
    if isinstance(label, str):
        text = label.strip()
        if not text:
            raise WeSpeakerParseError("speaker label 不能为空字符串")
        lower = text.lower()
        if lower.startswith("speaker"):
            suffix = text[len("speaker") :].strip()
            if suffix.isdigit():
                return f"Speaker {int(suffix)}"
            raise WeSpeakerParseError(f"无法解析 speaker label: {label!r}")
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return f"Speaker {int(text)}"
        raise WeSpeakerParseError(f"无法解析 speaker label: {label!r}")

    try:
        index = int(label)
    except (TypeError, ValueError) as exc:
        raise WeSpeakerParseError(f"无法解析 speaker label: {label!r}") from exc
    if index < 0:
        raise WeSpeakerParseError(f"speaker label 不能为负: {label!r}")
    return f"Speaker {index}"


def parse_wespeaker_raw(
    raw: Any,
    *,
    source: SourceName = "wespeaker",
) -> list[SpeakerTurn]:
    """Convert WeSpeaker ``diarize()`` return value into sorted speaker turns.

    Expected shapes:

    - ``[]`` / ``None`` → empty speech, return ``[]``
    - ``list[(utt, start_sec, end_sec, label), ...]``
    - ``list[{"utt", "start", "end", "label"}, ...]`` (artifact reload)

    Labels that first appear earlier in time become ``Speaker 0``, ``Speaker 1``, …
    so numbering is stable within a single task even if cluster ids are sparse.
    """
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise WeSpeakerParseError(
            f"WeSpeaker 原始结果应为 list，实际为 {type(raw).__name__}；"
            "请确认使用 model.diarize() 的返回值 (utt, start, end, label)。"
        )
    if not raw:
        return []

    pending: list[tuple[int, int, Any, float | None]] = []
    for index, item in enumerate(raw):
        path = f"[{index}]"
        utt, start_sec, end_sec, label, confidence = _unpack_row(item, path=path)
        _ = utt  # utterance id is not part of SpeakerTurn
        if _is_noise_label(label):
            # HDBSCAN may emit -1 for unclustered noise; drop those rows.
            continue
        start_ms = seconds_to_ms(start_sec, path=f"{path}.start")
        end_ms = seconds_to_ms(end_sec, path=f"{path}.end")
        if end_ms <= start_ms:
            raise WeSpeakerParseError(
                f"{path} 非法时间戳区间 [start_ms, end_ms)=[{start_ms}, {end_ms})，"
                "要求 end_ms > start_ms"
            )
        pending.append((start_ms, end_ms, label, confidence))

    # Assign contiguous Speaker N by first appearance after time sort.
    # Same cluster label always maps to the same Speaker id within one call.
    pending.sort(key=lambda row: (row[0], row[1], _label_sort_key(row[2])))
    label_map: dict[Any, str] = {}
    turns: list[SpeakerTurn] = []
    for start_ms, end_ms, label, confidence in pending:
        key = _label_key(label)
        if key not in label_map:
            label_map[key] = f"Speaker {len(label_map)}"
        turns.append(
            SpeakerTurn(
                start_ms=start_ms,
                end_ms=end_ms,
                speaker_id=label_map[key],
                confidence=confidence,
                source=source,
            )
        )

    turns.sort(key=lambda t: (t.start_ms, t.end_ms, t.speaker_id))
    return turns


def raw_rows_to_jsonable(raw: Any) -> list[dict[str, Any]]:
    """Serialize WeSpeaker raw rows for ``wespeaker_raw.json``."""
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise WeSpeakerParseError(
            f"无法序列化 WeSpeaker 原始结果: 期望 list，实际为 {type(raw).__name__}"
        )
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        utt, start, end, label, confidence = _unpack_row(item, path=f"[{index}]")
        row: dict[str, Any] = {
            "utt": utt,
            "start": _json_number(start),
            "end": _json_number(end),
            "label": _json_label(label),
        }
        if confidence is not None:
            row["confidence"] = confidence
        rows.append(row)
    return rows


def _unpack_row(
    item: Any, *, path: str
) -> tuple[str, Any, Any, Any, float | None]:
    if isinstance(item, dict):
        missing = [k for k in ("start", "end", "label") if k not in item]
        if missing:
            raise WeSpeakerParseError(f"{path} 缺少字段: {missing}")
        utt = item.get("utt", "unk")
        confidence = _optional_confidence(item.get("confidence"), path=path)
        return str(utt), item["start"], item["end"], item["label"], confidence

    if isinstance(item, (list, tuple)):
        if len(item) < 4:
            raise WeSpeakerParseError(
                f"{path} 应为 (utt, start, end, label)，实际长度 {len(item)}"
            )
        confidence = None
        if len(item) >= 5 and item[4] is not None:
            confidence = _optional_confidence(item[4], path=path)
        return str(item[0]), item[1], item[2], item[3], confidence

    raise WeSpeakerParseError(
        f"{path} 应为 tuple/list 或 dict，实际为 {type(item).__name__}"
    )


def _optional_confidence(value: Any, *, path: str) -> float | None:
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise WeSpeakerParseError(f"{path}.confidence 非法: {value!r}") from exc
    if not 0.0 <= score <= 1.0:
        raise WeSpeakerParseError(f"{path}.confidence 超出 [0, 1]: {score}")
    return score


def _is_noise_label(label: Any) -> bool:
    try:
        return int(label) == -1
    except (TypeError, ValueError):
        return False


def _label_key(label: Any) -> Any:
    """Canonical dict key so ``0`` and ``\"0\"`` collapse when appropriate."""
    if isinstance(label, str):
        text = label.strip()
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text)
        return text
    try:
        return int(label)
    except (TypeError, ValueError):
        return label


def _label_sort_key(label: Any) -> tuple[int, str]:
    key = _label_key(label)
    if isinstance(key, int):
        return (0, f"{key:08d}")
    return (1, str(key))


def _json_number(value: Any) -> float | int:
    if isinstance(value, bool):
        raise WeSpeakerParseError(f"时间戳不能为 bool: {value!r}")
    if isinstance(value, int):
        return value
    return float(value)


def _json_label(label: Any) -> int | str:
    try:
        return int(label)
    except (TypeError, ValueError):
        return str(label)
