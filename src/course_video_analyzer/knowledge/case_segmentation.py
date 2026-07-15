"""Compact, lossless-for-boundaries P03 timeline inputs."""

from __future__ import annotations

import json
from pathlib import Path

from course_video_analyzer.jobs.workspace import atomic_write_text


def build_p03_timeline_input(course_id: str, p02_path: Path, output_path: Path) -> Path:
    source = json.loads(Path(p02_path).read_text(encoding="utf-8"))
    segments = source.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("P02 segments 为空")
    timeline = []
    for item in segments:
        timeline.append(
            {
                "segment_id": item["segment_id"],
                "start_ms": item["start_ms"],
                "end_ms": item["end_ms"],
                "speaker": item["speaker"],
                "content_type": item["content_type"],
                "source_role": item["source_role"],
                "epistemic_type": item["epistemic_type"],
                "relevance": item["relevance"],
                "text": item["normalized_text"],
            }
        )
    payload = {
        "schema_version": "1.0",
        "prompt_version": "knowledge-v002-p03-input",
        "source_ids": [course_id],
        "course_id": course_id,
        "input_segment_count": len(timeline),
        "segments": timeline,
        "note": "该输入仅去除 P03 边界判断不需要的 raw/edit 字段，segment 顺序与文本完整保留。",
    }
    atomic_write_text(output_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return Path(output_path)
