"""Reusable deterministic P01 transcript normalization baseline."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.cleaning_qa import parse_transcript_blocks

DEFAULT_DISFLUENCY_RULES: tuple[tuple[str, str, str], ...] = (
    (r"(?:然后){2,}", "然后", "disfluency_normalized"),
    (r"(?:你跟){2,}", "你跟", "disfluency_normalized"),
    (r"(?:人家){2,}", "人家", "disfluency_normalized"),
    (r"(?:为什么){2,}", "为什么", "disfluency_normalized"),
    (r"怎么怎么样", "怎么样", "disfluency_normalized"),
    (r"中中层", "中层", "disfluency_normalized"),
    (r"回回家", "回家", "disfluency_normalized"),
    (r"玩玩完", "玩完", "disfluency_normalized"),
    (r"忘忘记记", "忘记", "obvious_typo_fixed"),
    (r"什么么", "什么", "obvious_typo_fixed"),
    (r"会会加", "会加", "disfluency_normalized"),
    (r"直直回", "直回", "disfluency_normalized"),
    (r"维维持", "维持", "disfluency_normalized"),
    (r"一一起", "一起", "disfluency_normalized"),
    (r"情情感", "情感", "disfluency_normalized"),
    (r"就是是", "就是", "disfluency_normalized"),
    (r"关关系", "关系", "disfluency_normalized"),
    (r"原原因", "原因", "disfluency_normalized"),
    (r"总总结", "总结", "disfluency_normalized"),
    (r"就{2,}", "就", "disfluency_normalized"),
    (r"很{2,}", "很", "disfluency_normalized"),
)


@dataclass(frozen=True)
class TranscriptNormalizerConfig:
    prompt_version: str = "knowledge-v002-p01"
    label_map: dict[str, str] = field(
        default_factory=lambda: {"导师": "teacher_a", "学员": "student"}
    )
    disfluency_rules: tuple[tuple[str, str, str], ...] = DEFAULT_DISFLUENCY_RULES
    ambiguous_repeat_pattern: str = r"(什么什么|好好好+|啊啊+|对对对+)"
    normalize_ascii_punctuation: bool = True
    board_prefix: str = "课板"


def _map_label(label: str, config: TranscriptNormalizerConfig) -> tuple[str, str]:
    if label.startswith(config.board_prefix):
        return "unknown", "board_ocr"
    return config.label_map.get(label, "unknown"), "speech"


def _normalize_speech(
    text: str,
    config: TranscriptNormalizerConfig,
) -> tuple[str, list[str], list[str]]:
    notes: list[str] = []
    uncertainties: list[str] = []
    normalized = text
    for pattern, replacement, note in config.disfluency_rules:
        normalized, count = re.subn(pattern, replacement, normalized)
        if count and note not in notes:
            notes.append(note)
    if re.search(config.ambiguous_repeat_pattern, normalized):
        uncertainties.append("存在可能为口语强调或识别重复的叠词，已保留原文结构")
    if config.normalize_ascii_punctuation:
        punctuated = normalized.translate(str.maketrans({",": "，", "?": "？", "!": "！"}))
        punctuated = re.sub(r"\.$", "。", punctuated)
        punctuated = re.sub(r"([，。！？、；：])\1+", r"\1", punctuated)
        if punctuated != normalized:
            normalized = punctuated
            notes.append("punctuation_normalized")
    return normalized, notes, uncertainties


def normalize_transcript_p01(
    course_id: str,
    transcript_path: Path,
    output_path: Path,
    *,
    config: TranscriptNormalizerConfig | None = None,
) -> Path:
    """Generate a complete P01 baseline without LLM calls or context loss."""
    cfg = config or TranscriptNormalizerConfig()
    transcript_path = Path(transcript_path).resolve()
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise FileExistsError(f"P01 输出已存在，拒绝覆盖: {output_path}")
    blocks = parse_transcript_blocks(transcript_path)
    if not blocks:
        raise ValueError(f"未解析到转写时间段: {transcript_path}")

    segments: list[dict[str, object]] = []
    uncertainties: list[dict[str, str]] = []
    punctuation_count = 0
    text_correction_count = 0
    for index, block in enumerate(blocks, start=1):
        segment_id = f"SEG-{course_id}-{index:06d}"
        speaker, content_type = _map_label(str(block["label"]), cfg)
        raw_text = str(block["text"])
        if content_type == "board_ocr":
            normalized = raw_text
            notes: list[str] = []
            uncertainty_notes: list[str] = []
            confidence = 0.8
        else:
            normalized, notes, uncertainty_notes = _normalize_speech(raw_text, cfg)
            confidence = 0.93 if not notes and not uncertainty_notes else 0.88
            if uncertainty_notes:
                confidence = 0.75
        for note in uncertainty_notes:
            uncertainties.append(
                {"segment_id": segment_id, "field": "normalized_text", "note": note}
            )
        if normalized != raw_text:
            if "punctuation_normalized" in notes:
                punctuation_count += 1
            if any(
                note
                in {
                    "disfluency_normalized",
                    "obvious_typo_fixed",
                    "context_supported_homophone_fixed",
                }
                for note in notes
            ):
                text_correction_count += 1
        segments.append(
            {
                "segment_id": segment_id,
                "start_ms": block["start_ms"],
                "end_ms": block["end_ms"],
                "speaker": speaker,
                "content_type": content_type,
                "raw_text": raw_text,
                "normalized_text": normalized,
                "edit_notes": notes,
                "confidence": confidence,
            }
        )
    changed_count = sum(
        item["normalized_text"] != item["raw_text"] for item in segments
    )
    payload = {
        "schema_version": "1.0",
        "prompt_version": cfg.prompt_version,
        "source_ids": [course_id],
        "segments": segments,
        "uncertainties": uncertainties,
        "validation": {
            "input_segment_count": len(blocks),
            "output_segment_count": len(segments),
        },
        "quality_metrics": {
            "changed_segment_count": changed_count,
            "punctuation_normalized_count": punctuation_count,
            "text_correction_count": text_correction_count,
            "uncertainty_count": len(uncertainties),
        },
    }
    atomic_write_text(output_path, json.dumps(payload, ensure_ascii=False, indent=2))
    reloaded = json.loads(output_path.read_text(encoding="utf-8"))
    if len(reloaded["segments"]) != len(blocks):
        raise RuntimeError("P01 自检失败：输入输出段数不同")
    for source, segment in zip(blocks, reloaded["segments"], strict=True):
        if (
            segment["raw_text"] != source["text"]
            or segment["start_ms"] != source["start_ms"]
            or segment["end_ms"] != source["end_ms"]
        ):
            raise RuntimeError("P01 自检失败：原文或时间戳未完整保留")
    return output_path
