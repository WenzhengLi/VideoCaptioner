#!/usr/bin/env python3
"""Build a baseline-aware C001-C020 fact and evidence report through P04."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _qa_status(path: Path) -> str:
    return str(_load(path).get("status") or "missing") if path.is_file() else "missing"


def _raw_qa_status(course_dir: Path) -> str:
    candidates = sorted((course_dir / "qa").glob("RUN*.json"), reverse=True)
    statuses = [_qa_status(path) for path in candidates]
    return "pass" if "pass" in statuses else (statuses[0] if statuses else "missing")


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def build_report(baseline_path: Path, data_root: Path) -> dict[str, Any]:
    baseline = _load(baseline_path)
    courses: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    total_segments = 0
    total_cases = 0
    total_ocr = 0

    for baseline_course in baseline.get("courses") or []:
        course_id = str(baseline_course["course_id"])
        course_dir = data_root / "courses" / course_id
        p01_version = str(baseline_course["p01_version"])
        p02_version = str(baseline_course["p02_version"])
        p03_version = str(baseline_course["p03_version"])
        p01_path = course_dir / "02_normalized" / f"P01-{p01_version}.json"
        p03_path = course_dir / "03_cases" / f"P03-{p03_version}.json"
        p01 = _load(p01_path)
        p03 = _load(p03_path)
        segments = p01.get("segments") or []
        metrics = p03.get("segmentation_metrics") or {}
        segment_count = len(segments)
        assigned = int(metrics.get("assigned_segment_count") or 0)
        unassigned = int(metrics.get("unassigned_segment_count") or 0)
        input_count = int(metrics.get("input_segment_count") or segment_count)
        speaker_counts = Counter(
            str(item.get("speaker") or "unknown") for item in segments
        )
        unknown_count = speaker_counts.get("unknown", 0)
        ocr_count = sum(
            1 for item in segments if item.get("content_type") == "board_ocr"
        )
        case_rows: list[dict[str, Any]] = []
        out_of_range: list[str] = []

        for case in baseline_course.get("cases") or []:
            case_id = str(case["case_id"])
            p04_version = str(case["p04_version"])
            qa_path = course_dir / "qa" / f"P04-{case_id}-{p04_version}-qa.json"
            qa: dict[str, Any] = (
                _load(qa_path) if qa_path.is_file() else {"status": "missing"}
            )
            qa_status = str(qa.get("status") or "missing")
            invalid = int((qa.get("metrics") or {}).get("invalid_evidence_count") or 0)
            if invalid:
                out_of_range.append(case_id)
            if qa_status != "pass":
                failures.append(
                    {"course_id": course_id, "stage": "P04", "case_id": case_id}
                )
            case_rows.append(
                {
                    "case_id": case_id,
                    "p04_version": p04_version,
                    "source_case_changed": bool(case.get("source_case_changed")),
                    "qa_status": qa_status,
                    "invalid_evidence_count": invalid,
                }
            )

        qa_statuses = {
            "raw": _raw_qa_status(course_dir),
            "P01": _qa_status(course_dir / "qa" / f"P01-{p01_version}-qa.json"),
            "P02": _qa_status(course_dir / "qa" / f"P02-{p02_version}-qa.json"),
            "P03": _qa_status(course_dir / "qa" / f"P03-{p03_version}-qa.json"),
        }
        for stage, status in qa_statuses.items():
            if status != "pass":
                failures.append({"course_id": course_id, "stage": stage, "case_id": ""})

        uncertainties = list(p01.get("uncertainties") or []) + list(
            p03.get("uncertainties") or []
        )
        courses.append(
            {
                "course_id": course_id,
                "versions": {
                    "P01": p01_version,
                    "P02": p02_version,
                    "P03": p03_version,
                },
                "segment_count": segment_count,
                "speaker_distribution": dict(sorted(speaker_counts.items())),
                "unknown_speaker_count": unknown_count,
                "unknown_speaker_ratio": _ratio(unknown_count, segment_count),
                "ocr_segment_count": ocr_count,
                "case_count": len(case_rows),
                "assigned_segment_count": assigned,
                "unassigned_segment_count": unassigned,
                "unassigned_ratio": _ratio(unassigned, input_count),
                "coverage_count_matches": assigned + unassigned == input_count,
                "qa": qa_statuses,
                "cases": case_rows,
                "p04_out_of_range_cases": out_of_range,
                "known_uncertainties": uncertainties,
            }
        )
        total_segments += segment_count
        total_cases += len(case_rows)
        total_ocr += ocr_count

    return {
        "schema_version": "1.0",
        "report_focus": "fact_and_evidence_layer_through_p04",
        "baseline": str(baseline_path.resolve()),
        "baseline_policy": baseline.get("policy"),
        "course_count": len(courses),
        "case_count": total_cases,
        "segment_count": total_segments,
        "ocr_segment_count": total_ocr,
        "failure_count": len(failures),
        "all_qa_pass": not failures,
        "failures": failures,
        "courses": courses,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# C001–C020 事实与证据层质量报告",
        "",
        f"- baseline policy：`{report['baseline_policy']}`",
        f"- 课程：{report['course_count']}；案例：{report['case_count']}",
        f"- segments：{report['segment_count']}；OCR segments：{report['ocr_segment_count']}",
        f"- 全部 QA pass：`{str(report['all_qa_pass']).lower()}`；失败：{report['failure_count']}",
        "",
        "| Course | P01 | P02 | P03 | Segments | OCR | Unknown | Cases | Assigned | Unassigned | Raw/P01/P02/P03 | P04 |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in report["courses"]:
        qa = item["qa"]
        p04_pass = sum(1 for case in item["cases"] if case["qa_status"] == "pass")
        lines.append(
            f"| {item['course_id']} | {item['versions']['P01']} | "
            f"{item['versions']['P02']} | {item['versions']['P03']} | "
            f"{item['segment_count']} | {item['ocr_segment_count']} | "
            f"{item['unknown_speaker_ratio']:.2%} | {item['case_count']} | "
            f"{item['assigned_segment_count']} | {item['unassigned_segment_count']} "
            f"({item['unassigned_ratio']:.2%}) | "
            f"{qa['raw']}/{qa['P01']}/{qa['P02']}/{qa['P03']} | "
            f"{p04_pass}/{item['case_count']} |"
        )

    checks = [
        (
            "20 课 raw QA 全部通过",
            all(c["qa"]["raw"] == "pass" for c in report["courses"]),
        ),
        (
            "P01/P02/P03 QA 全部通过",
            all(
                all(v == "pass" for v in c["qa"].values())
                for c in report["courses"]
            ),
        ),
        (
            "40 个案例 P04 QA 全部通过",
            all(
                case["qa_status"] == "pass"
                for c in report["courses"]
                for case in c["cases"]
            ),
        ),
        (
            "P03 assigned + unassigned 覆盖计数一致",
            all(c["coverage_count_matches"] for c in report["courses"]),
        ),
        (
            "P04 无案例外 evidence",
            all(not c["p04_out_of_range_cases"] for c in report["courses"]),
        ),
    ]
    lines.extend(["", "## 验收", ""])
    lines.extend(f"- [{'x' if passed else ' '}] {label}" for label, passed in checks)
    lines.extend(["", "## 已知不确定项", ""])
    for item in report["courses"]:
        notes = item["known_uncertainties"]
        if notes or item["unknown_speaker_ratio"] or item["unassigned_ratio"]:
            lines.append(
                f"- `{item['course_id']}`：unknown speaker "
                f"{item['unknown_speaker_ratio']:.2%}；unassigned "
                f"{item['unassigned_ratio']:.2%}；结构化 uncertainty {len(notes)} 条。"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.baseline, args.data_root)
    atomic_write_text(
        args.json_output,
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    atomic_write_text(args.markdown_output, render_markdown(report))
    print(
        f"Evidence report: courses={report['course_count']} "
        f"cases={report['case_count']} failures={report['failure_count']}"
    )
    return 0 if report["all_qa_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
