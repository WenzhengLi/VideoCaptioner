"""Compact Cursor review packs for P02 classification.

The full P02 JSON can be several megabytes. Cursor only needs representative
speaker samples plus explicit candidates; deterministic code applies the
review decisions back to every segment.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text

QUOTE_RE = re.compile(r"(我说|他说|她说|对方说|回复|回了|发给我|问我|告诉我)")
MARKETING_RE = re.compile(r"(报名|优惠|课程咨询|加微信|二维码|招生|付费群|私教名额)")
ALLOWED_CLUSTER_ROLES = {"instructor_explanation", "student_question", "unknown"}


def _even_samples(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(items) <= limit:
        selected = items
    else:
        indexes = sorted({round(i * (len(items) - 1) / (limit - 1)) for i in range(limit)})
        selected = [items[index] for index in indexes]
    return [
        {
            "segment_id": item["segment_id"],
            "speaker": item["speaker"],
            "text": item["normalized_text"],
        }
        for item in selected
    ]


def build_p02_review_pack(
    course_id: str,
    baseline_path: Path,
    output_path: Path,
    *,
    samples_per_cluster: int = 40,
    max_quote_candidates: int = 600,
) -> Path:
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    segments = baseline.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("P02 baseline segments 为空")
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    quote_candidates: list[dict[str, Any]] = []
    marketing_candidates: list[dict[str, Any]] = []
    unknown_candidates: list[dict[str, Any]] = []
    for segment in segments:
        speaker = str(segment.get("speaker", ""))
        if speaker.startswith("speaker_"):
            clusters[speaker].append(segment)
        compact = {
            "segment_id": segment.get("segment_id"),
            "speaker": speaker,
            "text": str(segment.get("normalized_text", "")),
        }
        if QUOTE_RE.search(compact["text"]):
            quote_candidates.append(compact)
        if MARKETING_RE.search(compact["text"]):
            marketing_candidates.append(compact)
        if segment.get("source_role") == "unknown":
            unknown_candidates.append(compact)
    payload = {
        "schema_version": "1.0",
        "prompt_version": "knowledge-v002-p02-review-input",
        "course_id": course_id,
        "speaker_cluster_profiles": {
            speaker: {
                "segment_count": len(items),
                "samples": _even_samples(items, samples_per_cluster),
            }
            for speaker, items in sorted(clusters.items())
        },
        "actual_chat_candidates": quote_candidates[:max_quote_candidates],
        "marketing_candidates": marketing_candidates,
        "unknown_candidates": unknown_candidates[:100],
        "constraints": {
            "actual_chat_ids_must_come_from_candidates": True,
            "marketing_ids_must_come_from_candidates": True,
            "do_not_rewrite_text": True,
        },
    }
    atomic_write_text(output_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return Path(output_path)


def apply_p02_review(
    course_id: str,
    baseline_path: Path,
    review_pack_path: Path,
    review_path: Path,
    output_path: Path,
) -> Path:
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    pack = json.loads(Path(review_pack_path).read_text(encoding="utf-8"))
    review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    if review.get("course_id") != course_id:
        raise ValueError("P02 review course_id 不匹配")
    profiles = pack.get("speaker_cluster_profiles") or {}
    roles = review.get("speaker_cluster_roles") or {}
    if set(roles) != set(profiles):
        raise ValueError("P02 review 必须为每个 speaker cluster 给出角色")
    if any(role not in ALLOWED_CLUSTER_ROLES for role in roles.values()):
        raise ValueError("P02 review 包含非法 speaker cluster 角色")
    quote_allowed = {item["segment_id"] for item in pack.get("actual_chat_candidates", [])}
    marketing_allowed = {item["segment_id"] for item in pack.get("marketing_candidates", [])}
    actual_ids = set(review.get("actual_chat_segment_ids") or [])
    marketing_ids = set(review.get("marketing_segment_ids") or [])
    uncertain_ids = set(review.get("uncertain_segment_ids") or [])
    if not actual_ids <= quote_allowed:
        raise ValueError("P02 review actual_chat_segment_ids 越界")
    if not marketing_ids <= marketing_allowed:
        raise ValueError("P02 review marketing_segment_ids 越界")

    segments = baseline["segments"]
    before = [
        (item["source_role"], item["epistemic_type"], item["relevance"])
        for item in segments
    ]
    valid_ids = {item["segment_id"] for item in segments}
    if not uncertain_ids <= valid_ids:
        raise ValueError("P02 review uncertain_segment_ids 越界")
    for item in segments:
        segment_id = item["segment_id"]
        speaker = str(item.get("speaker", ""))
        if item.get("content_type") == "board_ocr":
            continue
        if segment_id in marketing_ids:
            item.update(
                source_role="marketing",
                epistemic_type="quoted_statement",
                relevance="boilerplate",
                classification_reasons=["Cursor 复核为明确营销或联系方式"],
                classification_confidence=0.85,
            )
        elif segment_id in actual_ids:
            item.update(
                source_role="actual_chat",
                epistemic_type="quoted_statement",
                relevance="core",
                classification_reasons=["Cursor 根据引语与上下文复核为实际聊天复述"],
                classification_confidence=0.82,
            )
        elif segment_id in uncertain_ids:
            item.update(
                source_role="unknown",
                epistemic_type="unknown",
                relevance="uncertain",
                classification_reasons=["Cursor 复核后仍缺少足够上下文"],
                classification_confidence=0.45,
            )
        elif speaker in roles:
            role = roles[speaker]
            if role == "instructor_explanation":
                item.update(
                    source_role=role,
                    epistemic_type="instructor_claim",
                    relevance="core",
                    classification_reasons=[f"Cursor 复核 {speaker} 为主讲或讲解簇"],
                    classification_confidence=0.8,
                )
            elif role == "student_question":
                item.update(
                    source_role=role,
                    epistemic_type="quoted_statement",
                    relevance="core",
                    classification_reasons=[f"Cursor 复核 {speaker} 为学员或参与者簇"],
                    classification_confidence=0.72,
                )
            else:
                item.update(
                    source_role="unknown",
                    epistemic_type="unknown",
                    relevance="uncertain",
                    classification_reasons=[f"Cursor 无法确认 {speaker} 的语义角色"],
                    classification_confidence=0.5,
                )

    role_counts: dict[str, int] = {}
    epistemic_counts: dict[str, int] = {}
    relevance_counts: dict[str, int] = {}
    for item in segments:
        for target, field in (
            (role_counts, "source_role"),
            (epistemic_counts, "epistemic_type"),
            (relevance_counts, "relevance"),
        ):
            value = str(item[field])
            target[value] = target.get(value, 0) + 1
    after = [
        (item["source_role"], item["epistemic_type"], item["relevance"])
        for item in segments
    ]
    baseline_prompt_version = str(baseline.get("prompt_version") or "")
    baseline["prompt_version"] = (
        baseline_prompt_version.removesuffix("-baseline")
        if baseline_prompt_version.endswith("-p02-baseline")
        else "knowledge-v002-p02"
    )
    baseline["classification_metrics"] = {
        "source_role_counts": role_counts,
        "epistemic_type_counts": epistemic_counts,
        "relevance_counts": relevance_counts,
        "uncertain_segment_count": relevance_counts.get("uncertain", 0),
        "speaker_cluster_role_review": roles,
    }
    baseline["review_metrics"] = {
        "baseline_segment_count": len(segments),
        "reviewed_segment_count": len(segments),
        "classification_change_count": sum(x != y for x, y in zip(before, after, strict=True)),
        "remaining_uncertain_count": relevance_counts.get("uncertain", 0),
        "review_mode": "compact_decisions_applied_deterministically",
    }
    atomic_write_text(output_path, json.dumps(baseline, ensure_ascii=False, indent=2))
    return Path(output_path)
