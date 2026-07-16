#!/usr/bin/env python3
"""Compare Afeng external payload profiles for the same pilot cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.afeng_experiment import PilotManifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    manifests = [
        PilotManifest.model_validate_json(path.read_text(encoding="utf-8"))
        for path in args.manifests
    ]
    case_sets = [
        {(item.course_id, item.case_id) for item in manifest.cases}
        for manifest in manifests
    ]
    if not case_sets or any(items != case_sets[0] for items in case_sets[1:]):
        raise ValueError("pilot manifests do not contain the same cases")
    rows = []
    for manifest, path in zip(manifests, args.manifests, strict=True):
        local_segments = sum(item.segment_count for item in manifest.cases)
        external_segments = sum(item.external_segment_count for item in manifest.cases)
        characters = sum(item.estimated_input_characters for item in manifest.cases)
        rows.append(
            {
                "pilot_id": manifest.pilot_id,
                "manifest": str(path.resolve()),
                "profile": manifest.external_segment_profile,
                "context_window": manifest.external_context_window,
                "case_count": len(manifest.cases),
                "local_segment_count": local_segments,
                "external_segment_count": external_segments,
                "segment_reduction_ratio": round(
                    1 - external_segments / local_segments, 4
                )
                if local_segments
                else 0,
                "estimated_input_characters": characters,
                "rough_input_tokens": round(characters / 3.5),
                "minimum_required_evidence_coverage": min(
                    (item.required_evidence_coverage for item in manifest.cases),
                    default=0,
                ),
                "all_external_payloads_safe": all(
                    item.external_payload_safe for item in manifest.cases
                ),
            }
        )
    full = next((row for row in rows if row["profile"] == "full"), None)
    if full:
        for row in rows:
            row["character_reduction_vs_full"] = round(
                1 - row["estimated_input_characters"] / full["estimated_input_characters"],
                4,
            )
    payload = {"schema_version": "1.0", "profiles": rows}
    atomic_write_text(args.json_output, json.dumps(payload, ensure_ascii=False, indent=2))
    lines = [
        "# 阿峰三课外发载荷 Profile 对比",
        "",
        "固定输入：C003、C006、C010，共 5 个案例。所有 Profile 均保留本地完整证据包。",
        "",
        "| Profile | Context | External segments | Segment reduction | Characters | Rough tokens | Character reduction | Evidence coverage | PII safe |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['profile']} | {row['context_window']} | {row['external_segment_count']} | "
            f"{row['segment_reduction_ratio']:.1%} | {row['estimated_input_characters']} | "
            f"{row['rough_input_tokens']} | {row.get('character_reduction_vs_full', 0):.1%} | "
            f"{row['minimum_required_evidence_coverage']:.1%} | "
            f"{row['all_external_payloads_safe']} |"
        )
    lines.extend(
        [
            "",
            "## 当前结论",
            "",
            "- `full` 只用于本地审计或超长上下文模型，不作为默认 API 载荷。",
            "- `evidence_focused/context=1` 保留所有引用证据及相邻上下文，作为完整度优先候选。",
            "- `evidence_focused/context=0` 保留所有引用证据但不带相邻段，作为上下文受限候选。",
            "- 两种 focused Profile 的必需 evidence 覆盖率都必须保持 100%。",
            "- 取得真实模型上下文限制后，再确定三课 A/B 使用窗口 0、窗口 1 或两者并跑。",
            "",
        ]
    )
    atomic_write_text(args.markdown_output, "\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
