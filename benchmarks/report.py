"""Write machine-readable JSON and human-readable Markdown evaluation reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmarks.resources import hardware_info


def write_reports(
    result: dict[str, Any],
    output_dir: Path,
    *,
    basename: str = "benchmark_report",
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        **result,
        "hardware": hardware_info(),
    }
    json_path = output_dir / f"{basename}.json"
    md_path = output_dir / f"{basename}.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Benchmark Report: {payload.get('manifest', 'unknown')}",
        "",
        f"- dry_run: `{payload.get('dry_run')}`",
        f"- hardware: `{json.dumps(payload.get('hardware') or {}, ensure_ascii=False)}`",
        "",
        "## Missing media",
        "",
    ]
    missing = payload.get("missing_media") or []
    if missing:
        for item in missing:
            lines.append(f"- `{item}`")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Skipped samples", ""])
    skipped = payload.get("skipped") or []
    if skipped:
        for row in skipped:
            lines.append(f"- `{row.get('sample_id')}`: {row.get('reason')}")
    else:
        lines.append("- (none)")

    summary = payload.get("summary") or {}
    lines.extend(["", "## Summary", ""])
    if not summary:
        lines.append("_No metrics computed._")
    else:
        lines.append("```json")
        lines.append(json.dumps(summary, ensure_ascii=False, indent=2))
        lines.append("```")

    lines.extend(["", "## Component details", ""])
    components = payload.get("components") or {}
    for name, rows in components.items():
        lines.append(f"### {name}")
        lines.append("")
        if not rows:
            lines.append("_empty_")
            lines.append("")
            continue
        lines.append("```json")
        lines.append(json.dumps(rows, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines) + "\n"
