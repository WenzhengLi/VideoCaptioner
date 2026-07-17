#!/usr/bin/env python3
"""Summarize Afeng model run status, token usage, cost, and publication classes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.afeng_models import AfengRunManifest, PublicationRecord


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_run_summaries", type=Path, nargs="+")
    parser.add_argument("--report-id")
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    sources = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.model_run_summaries
    ]
    manifests: list[AfengRunManifest] = []
    seen_cases: set[tuple[str, str]] = set()
    for source in sources:
        for item in source.get("results") or []:
            manifest = AfengRunManifest.model_validate(item)
            key = (manifest.course_id, manifest.case_id)
            if key in seen_cases:
                raise ValueError(f"duplicate case across summaries: {key[0]}/{key[1]}")
            seen_cases.add(key)
            manifests.append(manifest)
    status_counts = Counter(item.status for item in manifests)
    publication_counts: Counter[str] = Counter()
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_cost = 0.0
    total_model_duration_ms = 0
    case_rows: list[dict[str, Any]] = []
    for manifest in manifests:
        prompt_tokens = sum(
            int(event.model_metadata.get("prompt_tokens") or 0) for event in manifest.events
        )
        completion_tokens = sum(
            int(event.model_metadata.get("completion_tokens") or 0)
            for event in manifest.events
        )
        cost = sum(
            float(event.model_metadata.get("estimated_cost") or 0) for event in manifest.events
        )
        duration_ms = sum(
            int(event.model_metadata.get("duration_ms") or event.duration_ms)
            for event in manifest.events
        )
        publication_class = ""
        publication_path = manifest.artifact_paths.get("publication")
        if publication_path and Path(publication_path).is_file():
            publication = PublicationRecord.model_validate_json(
                Path(publication_path).read_text(encoding="utf-8")
            )
            publication_class = publication.publication_class.value
            publication_counts[publication_class] += 1
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens
        total_cost += cost
        total_model_duration_ms += duration_ms
        case_rows.append(
            {
                "course_id": manifest.course_id,
                "case_id": manifest.case_id,
                "status": manifest.status,
                "revision_count": manifest.revision_count,
                "publication_class": publication_class,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "estimated_cost": round(cost, 8),
                "model_duration_ms": duration_ms,
            }
        )
    all_failures = [
        failure for source in sources for failure in source.get("failures") or []
    ]
    failures = [
        failure
        for failure in all_failures
        if (str(failure.get("course_id") or ""), str(failure.get("case_id") or ""))
        not in seen_cases
    ]
    pilot_ids = list(dict.fromkeys(str(source.get("pilot_id") or "") for source in sources))
    models = list(dict.fromkeys(str(source.get("model") or "") for source in sources))
    report_id = args.report_id or (pilot_ids[0] if len(pilot_ids) == 1 else "+".join(pilot_ids))
    report = {
        "schema_version": "1.0",
        "pilot_id": report_id,
        "source_pilot_ids": pilot_ids,
        "source_summaries": [str(path.resolve()) for path in args.model_run_summaries],
        "model": models[0] if len(models) == 1 else models,
        "status": "complete" if not failures else "needs_review",
        "case_count": len(manifests),
        "failure_count": len(failures),
        "status_counts": dict(status_counts),
        "publication_class_counts": dict(publication_counts),
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "estimated_cost": round(total_cost, 8),
        "model_duration_ms": total_model_duration_ms,
        "cases": case_rows,
        "failures": failures,
    }
    atomic_write_text(args.json_output, json.dumps(report, ensure_ascii=False, indent=2))
    lines = [
        f"# 阿峰模型试验汇总：{report['pilot_id']}",
        "",
        f"- 模型：`{report['model']}`",
        f"- 状态：`{report['status']}`",
        f"- 案例：{report['case_count']}；失败：{report['failure_count']}",
        f"- Tokens：{report['total_tokens']}（input {total_prompt_tokens} / output {total_completion_tokens}）",
        f"- 估算成本：{report['estimated_cost']}",
        f"- 模型耗时：{total_model_duration_ms / 1000:.2f}s",
        "",
        "| Course | Case | Status | Revisions | Publication | Input tokens | Output tokens | Cost | Duration |",
        "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in case_rows:
        lines.append(
            f"| {item['course_id']} | {item['case_id']} | {item['status']} | "
            f"{item['revision_count']} | {item['publication_class']} | {item['prompt_tokens']} | "
            f"{item['completion_tokens']} | {item['estimated_cost']} | "
            f"{item['model_duration_ms'] / 1000:.2f}s |"
        )
    if report["failures"]:
        lines.extend(["", "## 失败", ""])
        for failure in report["failures"]:
            lines.append(
                f"- `{failure.get('course_id')}/{failure.get('case_id')}`：{failure.get('error')}"
            )
    atomic_write_text(args.markdown_output, "\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
