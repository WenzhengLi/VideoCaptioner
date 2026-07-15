#!/usr/bin/env python3
"""Build a machine-readable + Markdown quality report for a course range."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _speaker_stats(segments: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for seg in segments:
        speaker = str(seg.get("speaker") or seg.get("speaker_id") or "missing")
        counts[speaker] += 1
    total = sum(counts.values()) or 1
    unknown = sum(v for k, v in counts.items() if "unknown" in k.lower())
    return {
        "distribution": dict(sorted(counts.items())),
        "unknown_ratio": round(unknown / total, 4),
        "segment_count": sum(counts.values()),
    }


def _qa_status(path: Path | None) -> str:
    if path is None or not path.exists():
        return "missing"
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return "invalid"
    return str(payload.get("status", "unknown"))


def analyze_course(data_root: Path, course_id: str, output_version: str) -> dict[str, Any]:
    course_dir = data_root / "courses" / course_id
    p01 = _load_json(course_dir / "02_normalized" / f"P01-{output_version}.json")
    p03 = _load_json(course_dir / "03_cases" / f"P03-{output_version}.json")
    segments: list[dict[str, Any]] = []
    if isinstance(p01, dict):
        segments = list(p01.get("segments") or [])
    speaker = _speaker_stats(segments) if segments else {
        "distribution": {},
        "unknown_ratio": None,
        "segment_count": 0,
    }

    cases = []
    unassigned = 0
    if isinstance(p03, dict):
        cases = list(p03.get("cases") or [])
        unassigned = len(p03.get("unassigned_segment_ids") or [])
    case_count = len(cases)
    assigned = sum(len(c.get("segment_ids") or []) for c in cases if isinstance(c, dict))
    total_for_ratio = assigned + unassigned
    unassigned_ratio = round(unassigned / total_for_ratio, 4) if total_for_ratio else None

    p05_dir = course_dir / "04_knowledge" / f"P05-{output_version}"
    risk_types: Counter[str] = Counter()
    risk_count = 0
    if p05_dir.exists():
        for path in sorted(p05_dir.glob("*.json")):
            if ".invalid-" in path.name or path.name.endswith(".cursor-task.json"):
                continue
            payload = _load_json(path)
            if not isinstance(payload, dict):
                continue
            reviews = payload.get("reviews") or payload.get("items") or []
            if isinstance(reviews, list):
                for item in reviews:
                    if not isinstance(item, dict):
                        continue
                    flags = item.get("safety_flags") or item.get("risks") or []
                    if isinstance(flags, list):
                        for flag in flags:
                            risk_types[str(flag)] += 1
                            risk_count += 1

    p06_dir = course_dir / "05_tidy" / f"P06-{output_version}"
    entry_count = 0
    if p06_dir.exists():
        for path in sorted(p06_dir.glob("*.json")):
            if ".invalid-" in path.name or path.name.endswith(".cursor-task.json"):
                continue
            payload = _load_json(path)
            if isinstance(payload, dict):
                entry_count += len(payload.get("entries") or [])

    markdown_dir = course_dir / "05_tidy" / f"markdown-{output_version}"
    markdown_count = (
        len(list(markdown_dir.rglob("*.md"))) if markdown_dir.exists() else 0
    )

    qa_dir = course_dir / "qa"
    qa = {
        "raw": _qa_status(next(iter(sorted(qa_dir.glob("RUN-*.json"))), None))
        if qa_dir.exists()
        else "missing",
        "P01": _qa_status(qa_dir / f"P01-{output_version}-qa.json"),
        "P02": _qa_status(qa_dir / f"P02-{output_version}-qa.json"),
        "P03": _qa_status(qa_dir / f"P03-{output_version}-qa.json"),
    }
    case_qa = {"P04": {}, "P05": {}, "P06": {}}
    if qa_dir.exists():
        for stage in ("P04", "P05", "P06"):
            for path in sorted(qa_dir.glob(f"{stage}-*-{output_version}-qa.json")):
                match = re.search(rf"{stage}-(CASE-[^-]+-\d+)-", path.name)
                key = match.group(1) if match else path.stem
                case_qa[stage][key] = _qa_status(path)

    return {
        "course_id": course_id,
        "segment_count": speaker["segment_count"],
        "speaker_distribution": speaker["distribution"],
        "unknown_ratio": speaker["unknown_ratio"],
        "case_count": case_count,
        "unassigned_segment_count": unassigned,
        "unassigned_ratio": unassigned_ratio,
        "p05_risk_count": risk_count,
        "p05_risk_types": dict(risk_types),
        "p06_entry_count": entry_count,
        "markdown_count": markdown_count,
        "qa": qa,
        "case_qa": case_qa,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 知识库质量报告 {report['start_course']}-{report['end_course']}",
        "",
        f"- output_version: `{report['output_version']}`",
        f"- courses: {len(report['courses'])}",
        f"- total_segments: {report['totals']['segment_count']}",
        f"- total_cases: {report['totals']['case_count']}",
        f"- total_entries: {report['totals']['p06_entry_count']}",
        f"- total_risks: {report['totals']['p05_risk_count']}",
        "",
        "| Course | Segments | Unknown% | Cases | Unassigned% | Risks | Entries | MD | QA |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for course in report["courses"]:
        unk = "n/a" if course["unknown_ratio"] is None else f"{course['unknown_ratio']*100:.1f}"
        unassigned = (
            "n/a"
            if course["unassigned_ratio"] is None
            else f"{course['unassigned_ratio']*100:.1f}"
        )
        qa_ok = all(v == "pass" for v in course["qa"].values())
        lines.append(
            f"| {course['course_id']} | {course['segment_count']} | {unk} | "
            f"{course['case_count']} | {unassigned} | {course['p05_risk_count']} | "
            f"{course['p06_entry_count']} | {course['markdown_count']} | "
            f"{'pass' if qa_ok else 'check'} |"
        )
    lines.append("")
    lines.append("机器可读完整结果见同名 `.json`。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--output-version", default="knowledge-v002")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    courses = [
        analyze_course(args.data_root, f"C{i:03d}", args.output_version)
        for i in range(args.start, args.end + 1)
    ]
    totals = {
        "segment_count": sum(c["segment_count"] for c in courses),
        "case_count": sum(c["case_count"] for c in courses),
        "p06_entry_count": sum(c["p06_entry_count"] for c in courses),
        "p05_risk_count": sum(c["p05_risk_count"] for c in courses),
        "markdown_count": sum(c["markdown_count"] for c in courses),
    }
    report = {
        "schema_version": "1.0",
        "start_course": f"C{args.start:03d}",
        "end_course": f"C{args.end:03d}",
        "output_version": args.output_version,
        "totals": totals,
        "courses": courses,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    json_path = args.output.with_suffix(".json")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {args.output} and {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
