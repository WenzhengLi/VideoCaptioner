#!/usr/bin/env python3
"""Build a machine-readable + Markdown quality report for a course range.

Focuses on the fact & evidence layer (raw + P01–P04). Historical P05/P06
counts are retained as optional context only.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
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


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _stage_timings_seconds(job: dict[str, Any] | None) -> dict[str, float | None]:
    if not isinstance(job, dict):
        return {}
    stages = job.get("stages") or {}
    result: dict[str, float | None] = {}
    if not isinstance(stages, dict):
        return result
    for name, payload in stages.items():
        if not isinstance(payload, dict):
            result[name] = None
            continue
        start = _parse_iso(payload.get("started_at"))
        end = _parse_iso(payload.get("finished_at"))
        if start and end:
            result[name] = round((end - start).total_seconds(), 1)
        else:
            result[name] = None
    return result


def _resolve_run_id(course_dir: Path) -> str | None:
    raw_dir = course_dir / "01_raw"
    if not raw_dir.exists():
        return None
    runs = sorted(
        [
            p.name
            for p in raw_dir.iterdir()
            if p.is_dir() and p.name.startswith("RUN-") and (p / "run.json").exists()
        ]
    )
    preferred = [r for r in runs if r != "RUN-20260715-BASELINE"]
    if preferred:
        return preferred[-1]
    return runs[-1] if runs else None


def _resolve_job_dir(
    course_id: str,
    run_id: str | None,
    course_dir: Path,
    jobs_root: Path,
) -> Path | None:
    if run_id:
        batch_job = jobs_root / "batch" / f"{course_id}-{run_id}"
        if batch_job.exists():
            return batch_job
        archive_job = course_dir / "01_raw" / run_id
        if (archive_job / "job.json").exists():
            return archive_job
    # C001 baseline style: source_job_id may be a short hash under jobs/real
    run_meta = None
    if run_id:
        run_meta = _load_json(course_dir / "01_raw" / run_id / "run.json")
    if isinstance(run_meta, dict):
        source_job_id = run_meta.get("source_job_id")
        if source_job_id:
            for parent in (jobs_root / "real", jobs_root / "batch", jobs_root):
                candidate = parent / str(source_job_id)
                if (candidate / "job.json").exists():
                    return candidate
    return None


def _ocr_metrics(job_dir: Path | None) -> dict[str, Any]:
    empty = {
        "ocr_call_count": None,
        "ocr_cache_hits": None,
        "ocr_dedup_image_count": None,
        "frame_count": None,
        "sampling_mode": None,
    }
    if job_dir is None:
        return empty
    manifest_path = job_dir / "frames" / "manifest.json"
    payload = _load_json(manifest_path)
    if not isinstance(payload, dict):
        return empty
    stats_value = payload.get("stats")
    stats: dict[str, Any] = stats_value if isinstance(stats_value, dict) else {}
    return {
        "ocr_call_count": stats.get("actual_full_ocr_count"),
        "ocr_cache_hits": stats.get("downstream_ocr_cache_hit_count"),
        "ocr_dedup_image_count": stats.get("final_image_count_after_ocr_dedup"),
        "frame_count": len(payload.get("frames") or []),
        "sampling_mode": payload.get("mode"),
    }


def _batch_item(batch_manifest: dict[str, Any] | None, course_id: str) -> dict[str, Any]:
    if not isinstance(batch_manifest, dict):
        return {"attempts": None, "status": None, "error": None}
    for item in batch_manifest.get("items") or []:
        if isinstance(item, dict) and item.get("course_id") == course_id:
            return {
                "attempts": item.get("attempts"),
                "status": item.get("status"),
                "error": item.get("error"),
            }
    return {"attempts": None, "status": None, "error": None}


def _p04_out_of_range(case_qa_payloads: dict[str, dict[str, Any]]) -> list[str]:
    flagged: list[str] = []
    for case_id, payload in case_qa_payloads.items():
        checks = payload.get("checks") if isinstance(payload, dict) else None
        if isinstance(checks, dict) and checks.get("evidence_in_case_range") is False:
            flagged.append(case_id)
            continue
        metrics = payload.get("metrics") if isinstance(payload, dict) else None
        if isinstance(metrics, dict) and int(metrics.get("invalid_evidence_count") or 0) > 0:
            flagged.append(case_id)
    return flagged


def _case_boundary_flags(
    cases: list[dict[str, Any]],
    unassigned_ratio: float | None,
    segment_count: int,
) -> list[str]:
    flags: list[str] = []
    if not cases:
        if segment_count:
            flags.append("no_cases")
        return flags
    sizes: list[int] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        seg_ids = case.get("segment_ids")
        if isinstance(seg_ids, list) and seg_ids:
            sizes.append(len(seg_ids))
            continue
        start = str(case.get("start_segment_id") or "")
        end = str(case.get("end_segment_id") or "")
        start_n = re.search(r"(\d+)$", start)
        end_n = re.search(r"(\d+)$", end)
        if start_n and end_n:
            sizes.append(max(0, int(end_n.group(1)) - int(start_n.group(1)) + 1))
    if sizes:
        median = sorted(sizes)[len(sizes) // 2]
        tiny = sum(1 for s in sizes if s < max(50, int(0.02 * segment_count)))
        if tiny >= max(2, len(sizes) // 2):
            flags.append("case_boundaries_too_fragmented")
        if len(sizes) == 1 and unassigned_ratio is not None and unassigned_ratio > 0.35:
            flags.append("case_boundaries_possibly_too_narrow")
        if median > 0.85 * segment_count and len(sizes) == 1:
            flags.append("case_boundaries_possibly_too_wide")
    return flags


def analyze_course(
    data_root: Path,
    course_id: str,
    output_version: str,
    *,
    jobs_root: Path | None = None,
    batch_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    course_dir = data_root / "courses" / course_id
    jobs_root = jobs_root or Path("jobs")
    p01 = _load_json(course_dir / "02_normalized" / f"P01-{output_version}.json")
    p03 = _load_json(course_dir / "03_cases" / f"P03-{output_version}.json")
    segments: list[dict[str, Any]] = []
    if isinstance(p01, dict):
        segments = list(p01.get("segments") or [])
    speaker = (
        _speaker_stats(segments)
        if segments
        else {
            "distribution": {},
            "unknown_ratio": None,
            "segment_count": 0,
        }
    )

    cases: list[Any] = []
    unassigned = 0
    assigned = 0
    if isinstance(p03, dict):
        cases = list(p03.get("cases") or [])
        unassigned = len(p03.get("unassigned_segment_ids") or [])
        metrics = p03.get("segmentation_metrics") or {}
        if isinstance(metrics, dict):
            assigned = int(metrics.get("assigned_segment_count") or 0)
            unassigned = int(metrics.get("unassigned_segment_count") or unassigned)
        if not assigned:
            assigned = sum(
                len(c.get("segment_ids") or []) for c in cases if isinstance(c, dict)
            )
    case_count = len(cases)
    total_for_ratio = (
        int((p03 or {}).get("segmentation_metrics", {}).get("input_segment_count") or 0)
        if isinstance(p03, dict)
        else 0
    )
    if not total_for_ratio:
        total_for_ratio = assigned + unassigned or speaker["segment_count"]
    unassigned_ratio = (
        round(unassigned / total_for_ratio, 4) if total_for_ratio else None
    )

    # Historical P05/P06 (context only; not evidence-layer completion criteria)
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
            flags = payload.get("safety_flags") or []
            if isinstance(flags, list):
                for flag in flags:
                    if isinstance(flag, dict):
                        label = str(
                            flag.get("type")
                            or flag.get("risk_type")
                            or flag.get("name")
                            or "unknown"
                        )
                    else:
                        label = str(flag)
                    risk_types[label] += 1
                    risk_count += 1
            reviews = (
                payload.get("evidence_reviews")
                or payload.get("reviews")
                or payload.get("items")
                or []
            )
            if isinstance(reviews, list):
                for item in reviews:
                    if not isinstance(item, dict):
                        continue
                    nested = item.get("safety_flags") or item.get("risks") or []
                    if isinstance(nested, list):
                        for flag in nested:
                            if isinstance(flag, dict):
                                label = str(
                                    flag.get("type")
                                    or flag.get("risk_type")
                                    or flag.get("name")
                                    or "unknown"
                                )
                            else:
                                label = str(flag)
                            risk_types[label] += 1
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

    p04_dir = course_dir / "04_knowledge" / f"P04-{output_version}"
    p04_files = []
    if p04_dir.exists():
        p04_files = sorted(
            p
            for p in p04_dir.glob("CASE-*.json")
            if ".invalid-" not in p.name and not p.name.endswith(".cursor-task.json")
        )
    p04_case_file_count = len(p04_files)

    qa_dir = course_dir / "qa"
    qa = {
        "raw": _qa_status(next(iter(sorted(qa_dir.glob("RUN-*.json"))), None))
        if qa_dir.exists()
        else "missing",
        "P01": _qa_status(qa_dir / f"P01-{output_version}-qa.json"),
        "P02": _qa_status(qa_dir / f"P02-{output_version}-qa.json"),
        "P03": _qa_status(qa_dir / f"P03-{output_version}-qa.json"),
    }
    case_qa: dict[str, dict[str, str]] = {"P04": {}, "P05": {}, "P06": {}}
    p04_qa_payloads: dict[str, dict[str, Any]] = {}
    if qa_dir.exists():
        for stage in ("P04", "P05", "P06"):
            for path in sorted(qa_dir.glob(f"{stage}-*-{output_version}-qa.json")):
                match = re.search(rf"{stage}-(CASE-[^-]+-\d+)-", path.name)
                key = match.group(1) if match else path.stem
                case_qa[stage][key] = _qa_status(path)
                if stage == "P04":
                    payload = _load_json(path)
                    if isinstance(payload, dict):
                        p04_qa_payloads[key] = payload

    run_id = _resolve_run_id(course_dir)
    job_dir = _resolve_job_dir(course_id, run_id, course_dir, jobs_root)
    job_payload = None
    if job_dir is not None:
        job_payload = _load_json(job_dir / "job.json")
    stage_timings = _stage_timings_seconds(
        job_payload if isinstance(job_payload, dict) else None
    )
    ocr = _ocr_metrics(job_dir)
    batch = _batch_item(batch_manifest, course_id)
    attempts = batch.get("attempts")
    failure_count = 0
    if isinstance(attempts, int) and attempts > 1:
        failure_count = attempts - 1
    if batch.get("status") == "failed":
        failure_count = max(failure_count, 1)

    version_fields_present = {
        "p01": bool(
            isinstance(p01, dict)
            and (p01.get("prompt_version") or p01.get("schema_version"))
        ),
        "p03": bool(
            isinstance(p03, dict)
            and (p03.get("prompt_version") or p03.get("schema_version"))
        ),
    }

    flags: list[str] = []
    if unassigned_ratio is not None and unassigned_ratio > 0.20:
        flags.append("high_unassigned_gt_20pct")
    if speaker["unknown_ratio"] is not None and speaker["unknown_ratio"] > 0.10:
        flags.append("high_unknown_speaker")
    out_of_range = _p04_out_of_range(p04_qa_payloads)
    if out_of_range:
        flags.append("p04_evidence_outside_case_range")
    flags.extend(
        _case_boundary_flags(
            [c for c in cases if isinstance(c, dict)],
            unassigned_ratio,
            int(speaker["segment_count"] or 0),
        )
    )
    board_count = None
    if run_id:
        analysis = _load_json(course_dir / "01_raw" / run_id / "analysis.json")
        if isinstance(analysis, dict):
            diag = analysis.get("diagnostics") or {}
            if isinstance(diag, dict):
                board_count = diag.get("board_count")
    ocr_calls = ocr.get("ocr_call_count")
    if (
        isinstance(ocr_calls, int)
        and isinstance(board_count, int)
        and board_count > 0
        and ocr_calls > board_count * 3
    ):
        flags.append("ocr_ratio_high_vs_boards")
    for stage_name, status in qa.items():
        if status != "pass":
            flags.append(f"qa_{stage_name}_{status}")
    for case_id, status in case_qa["P04"].items():
        if status != "pass":
            flags.append(f"qa_P04_{case_id}_{status}")
    if p04_case_file_count != case_count:
        flags.append("p04_case_file_count_mismatch")
    if not version_fields_present["p01"] or not version_fields_present["p03"]:
        flags.append("missing_version_fields")
    if failure_count:
        flags.append("has_retries_or_failures")

    evidence_qa_ok = all(v == "pass" for v in qa.values()) and all(
        v == "pass" for v in case_qa["P04"].values()
    ) and (case_count == 0 or len(case_qa["P04"]) == case_count)

    return {
        "course_id": course_id,
        "run_id": run_id,
        "segment_count": speaker["segment_count"],
        "speaker_distribution": speaker["distribution"],
        "unknown_ratio": speaker["unknown_ratio"],
        "case_count": case_count,
        "unassigned_segment_count": unassigned,
        "unassigned_ratio": unassigned_ratio,
        "p04_case_file_count": p04_case_file_count,
        "stage_timings_seconds": stage_timings,
        "ocr": ocr,
        "board_count": board_count,
        "attempts": attempts,
        "failure_count": failure_count,
        "batch_status": batch.get("status"),
        "p05_risk_count": risk_count,
        "p05_risk_types": dict(risk_types),
        "p06_entry_count": entry_count,
        "markdown_count": markdown_count,
        "qa": qa,
        "case_qa": case_qa,
        "p04_out_of_range_cases": out_of_range,
        "version_fields_present": version_fields_present,
        "flags": flags,
        "evidence_qa_ok": evidence_qa_ok,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 事实与证据层质量报告 {report['start_course']}-{report['end_course']}",
        "",
        f"- output_version: `{report['output_version']}`",
        f"- courses: {len(report['courses'])}",
        f"- total_segments: {report['totals']['segment_count']}",
        f"- total_cases: {report['totals']['case_count']}",
        f"- total_p04_files: {report['totals']['p04_case_file_count']}",
        f"- evidence_qa_all_pass: {report['totals']['evidence_qa_all_pass']}",
        f"- flagged_courses: {report['totals']['flagged_course_count']}",
        "",
        "> 本报告聚焦 raw / P01–P04。下列 P05/P06 数字仅为历史信息，不作为本次完成标准。",
        f"> historical p06_entries={report['totals']['p06_entry_count']}, "
        f"p05_risks={report['totals']['p05_risk_count']}",
        "",
        "| Course | Segs | Unk% | Cases | Unass% | P04 | OCR | Cache | Dedup | Fail | EvQA | Flags |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for course in report["courses"]:
        unk = (
            "n/a"
            if course["unknown_ratio"] is None
            else f"{course['unknown_ratio'] * 100:.1f}"
        )
        unassigned = (
            "n/a"
            if course["unassigned_ratio"] is None
            else f"{course['unassigned_ratio'] * 100:.1f}"
        )
        ocr = course.get("ocr") or {}
        ocr_calls = ocr.get("ocr_call_count")
        cache = ocr.get("ocr_cache_hits")
        dedup = ocr.get("ocr_dedup_image_count")
        flags = ",".join(course.get("flags") or []) or "-"
        lines.append(
            f"| {course['course_id']} | {course['segment_count']} | {unk} | "
            f"{course['case_count']} | {unassigned} | {course['p04_case_file_count']} | "
            f"{ocr_calls if ocr_calls is not None else 'n/a'} | "
            f"{cache if cache is not None else 'n/a'} | "
            f"{dedup if dedup is not None else 'n/a'} | "
            f"{course.get('failure_count', 0)} | "
            f"{'pass' if course.get('evidence_qa_ok') else 'check'} | {flags} |"
        )

    flagged = [c for c in report["courses"] if c.get("flags")]
    lines.extend(["", "## 特别标记", ""])
    if not flagged:
        lines.append("- 无特别标记。")
    else:
        for course in flagged:
            lines.append(
                f"- **{course['course_id']}**: {', '.join(course['flags'])}"
            )

    lines.extend(
        [
            "",
            "## 视频阶段耗时（秒）",
            "",
            "| Course | media | transcript | diarization | alignment | board_detect | board_track | board_ocr | merge | export |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    stage_names = [
        "media",
        "transcript",
        "diarization",
        "alignment",
        "board_detect",
        "board_track",
        "board_ocr",
        "merge",
        "export",
    ]
    for course in report["courses"]:
        timings = course.get("stage_timings_seconds") or {}
        cells = [
            "n/a" if timings.get(name) is None else str(timings.get(name))
            for name in stage_names
        ]
        lines.append(f"| {course['course_id']} | " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("机器可读完整结果见同名 `.json`。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--jobs-root", type=Path, default=Path("jobs"))
    parser.add_argument("--batch-id", default="BATCH-20260715-001")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--output-version", default="knowledge-v002")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    batch_manifest = _load_json(
        args.data_root / "batches" / args.batch_id / "manifest.json"
    )
    courses = [
        analyze_course(
            args.data_root,
            f"C{i:03d}",
            args.output_version,
            jobs_root=args.jobs_root,
            batch_manifest=batch_manifest if isinstance(batch_manifest, dict) else None,
        )
        for i in range(args.start, args.end + 1)
    ]
    totals = {
        "segment_count": sum(c["segment_count"] for c in courses),
        "case_count": sum(c["case_count"] for c in courses),
        "p04_case_file_count": sum(c["p04_case_file_count"] for c in courses),
        "p06_entry_count": sum(c["p06_entry_count"] for c in courses),
        "p05_risk_count": sum(c["p05_risk_count"] for c in courses),
        "markdown_count": sum(c["markdown_count"] for c in courses),
        "ocr_call_count": sum(
            int(c["ocr"]["ocr_call_count"])
            for c in courses
            if isinstance(c.get("ocr", {}).get("ocr_call_count"), int)
        ),
        "ocr_cache_hits": sum(
            int(c["ocr"]["ocr_cache_hits"])
            for c in courses
            if isinstance(c.get("ocr", {}).get("ocr_cache_hits"), int)
        ),
        "failure_count": sum(int(c.get("failure_count") or 0) for c in courses),
        "flagged_course_count": sum(1 for c in courses if c.get("flags")),
        "evidence_qa_all_pass": all(c.get("evidence_qa_ok") for c in courses),
    }
    report = {
        "schema_version": "1.1",
        "report_focus": "fact_and_evidence_layer",
        "start_course": f"C{args.start:03d}",
        "end_course": f"C{args.end:03d}",
        "output_version": args.output_version,
        "batch_id": args.batch_id,
        "totals": totals,
        "courses": courses,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    json_path = args.output.with_suffix(".json")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args.output.write_text(render_markdown(report), encoding="utf-8")
    print(f"Wrote {args.output} and {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
