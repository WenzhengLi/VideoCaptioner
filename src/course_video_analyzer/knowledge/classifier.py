"""Deterministic P02 classification baseline for Cursor review."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text


@dataclass(frozen=True)
class SegmentClassification:
    source_role: str
    epistemic_type: str
    relevance: str
    reason: str
    confidence: float


MARKETING_RE = re.compile(r"(报名|优惠|课程咨询|加微信|二维码|招生|付费群|私教名额)")


def classify_segment_baseline(
    segment: dict[str, Any],
    *,
    cluster_roles: dict[str, str] | None = None,
) -> SegmentClassification:
    text = str(segment.get("normalized_text", ""))
    speaker = segment.get("speaker")
    content_type = segment.get("content_type")
    if content_type == "board_ocr":
        return SegmentClassification(
            "board",
            "unknown",
            "supporting",
            "课板 OCR 仅证明画面文字存在，内部语义需后续审查",
            0.85,
        )
    if MARKETING_RE.search(text):
        return SegmentClassification(
            "marketing",
            "quoted_statement",
            "boilerplate",
            "文本包含明确课程营销或联系方式关键词",
            0.75,
        )
    if speaker in {"teacher_a", "teacher_b"}:
        return SegmentClassification(
            "instructor_explanation",
            "instructor_claim",
            "core",
            "讲师发言默认视为课程解释或判断，不当作客观事实",
            0.8,
        )
    if isinstance(speaker, str) and speaker.startswith("speaker_"):
        inferred_role = (cluster_roles or {}).get(speaker)
        if inferred_role == "instructor_explanation":
            return SegmentClassification(
                "instructor_explanation",
                "instructor_claim",
                "core",
                "该声纹簇在本课发言占比最高，保守作为主讲簇，需 Cursor 结合上下文复核",
                0.65,
            )
        if inferred_role == "student_question":
            return SegmentClassification(
                "student_question",
                "quoted_statement",
                "core",
                "该声纹簇不是主讲簇，保守作为参与者发言，需 Cursor 结合上下文复核",
                0.55,
            )
    if speaker == "student":
        return SegmentClassification(
            "student_question",
            "quoted_statement",
            "core",
            "学员直接发言，具体是否复述案例需 Cursor 结合上下文审查",
            0.75,
        )
    return SegmentClassification(
        "unknown",
        "unknown",
        "uncertain",
        "说话人或来源证据不足，保守标记为未知",
        0.5,
    )


def classify_p02_baseline(
    course_id: str,
    p01_path: Path,
    output_path: Path,
    *,
    prompt_version: str = "knowledge-v002-p02-baseline",
) -> Path:
    p01_path = Path(p01_path).resolve()
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise FileExistsError(f"P02 输出已存在，拒绝覆盖: {output_path}")
    source = json.loads(p01_path.read_text(encoding="utf-8"))
    source_segments = source.get("segments")
    if not isinstance(source_segments, list) or not source_segments:
        raise ValueError(f"P01 segments 为空: {p01_path}")
    segments: list[dict[str, Any]] = []
    cluster_counts: dict[str, int] = {}
    for source_segment in source_segments:
        if isinstance(source_segment, dict):
            speaker = source_segment.get("speaker")
            if isinstance(speaker, str) and speaker.startswith("speaker_"):
                cluster_counts[speaker] = cluster_counts.get(speaker, 0) + 1
    cluster_roles: dict[str, str] = {}
    if cluster_counts:
        dominant_cluster = max(cluster_counts, key=cluster_counts.get)
        cluster_roles = {
            speaker: (
                "instructor_explanation"
                if speaker == dominant_cluster
                else "student_question"
            )
            for speaker in cluster_counts
        }
    role_counts: dict[str, int] = {}
    epistemic_counts: dict[str, int] = {}
    relevance_counts: dict[str, int] = {}
    for source_segment in source_segments:
        if not isinstance(source_segment, dict):
            raise ValueError("P01 segment 必须是对象")
        classification = classify_segment_baseline(
            source_segment,
            cluster_roles=cluster_roles,
        )
        item = dict(source_segment)
        item.update(
            {
                "source_role": classification.source_role,
                "epistemic_type": classification.epistemic_type,
                "relevance": classification.relevance,
                "classification_reasons": [classification.reason],
                "classification_confidence": classification.confidence,
            }
        )
        segments.append(item)
        role_counts[classification.source_role] = role_counts.get(classification.source_role, 0) + 1
        epistemic_counts[classification.epistemic_type] = (
            epistemic_counts.get(classification.epistemic_type, 0) + 1
        )
        relevance_counts[classification.relevance] = (
            relevance_counts.get(classification.relevance, 0) + 1
        )
    payload = {
        "schema_version": "1.0",
        "prompt_version": prompt_version,
        "source_ids": [course_id],
        "segments": segments,
        "uncertainties": list(source.get("uncertainties") or []),
        "validation": {
            "input_segment_count": len(source_segments),
            "output_segment_count": len(segments),
        },
        "classification_metrics": {
            "source_role_counts": role_counts,
            "epistemic_type_counts": epistemic_counts,
            "relevance_counts": relevance_counts,
            "uncertain_segment_count": sum(
                item["relevance"] == "uncertain" for item in segments
            ),
            "speaker_cluster_counts": cluster_counts,
            "speaker_cluster_role_baseline": cluster_roles,
        },
    }
    atomic_write_text(output_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return output_path
