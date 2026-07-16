#!/usr/bin/env python3
"""Build a hybrid evidence baseline from v002/v003 course outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from course_video_analyzer.knowledge.evidence_wave import (
    build_evidence_baseline,
    write_evidence_baseline,
)


def _metrics(path: Path) -> dict | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    metrics = payload.get("segmentation_metrics")
    return metrics if isinstance(metrics, dict) else None


def choose_p03_version(
    course_dir: Path,
    *,
    prefer_v003_if_better: bool = True,
    force_v003: set[str] | None = None,
) -> str:
    course_id = course_dir.name
    if force_v003 and course_id in force_v003:
        if (course_dir / "03_cases" / "P03-knowledge-v003.json").exists():
            return "knowledge-v003"
    v2 = _metrics(course_dir / "03_cases" / "P03-knowledge-v002.json")
    v3 = _metrics(course_dir / "03_cases" / "P03-knowledge-v003.json")
    qa3 = course_dir / "qa" / "P03-knowledge-v003-qa.json"
    v3_ok = False
    if qa3.exists():
        status = json.loads(qa3.read_text(encoding="utf-8-sig")).get("status")
        v3_ok = status == "pass" and v3 is not None
    if not v3_ok:
        return "knowledge-v002"
    if v3 is None:
        return "knowledge-v002"
    if not prefer_v003_if_better or v2 is None:
        return "knowledge-v003"
    r2 = (v2.get("unassigned_segment_count") or 0) / max(
        int(v2.get("input_segment_count") or 1), 1
    )
    r3 = (v3.get("unassigned_segment_count") or 0) / max(
        int(v3.get("input_segment_count") or 1), 1
    )
    # Prefer v003 only when unassigned improves by >= 3 percentage points.
    if r3 <= r2 - 0.03:
        return "knowledge-v003"
    return "knowledge-v002"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=15)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/catalog/evidence-baseline-C001-C015.json"),
    )
    parser.add_argument(
        "--force-v003",
        default="C003",
        help="comma-separated course ids forced to v003 when QA pass",
    )
    parser.add_argument(
        "--full-v003-from",
        type=int,
        default=None,
        help="course ordinal from which P01-P04 all use knowledge-v003",
    )
    args = parser.parse_args()
    force = {c.strip() for c in args.force_v003.split(",") if c.strip()}

    courses = []
    for ordinal in range(args.start, args.end + 1):
        course_id = f"C{ordinal:03d}"
        course_dir = args.data_root / "courses" / course_id
        full_v003 = args.full_v003_from is not None and ordinal >= args.full_v003_from
        p01_version = "knowledge-v003" if full_v003 else "knowledge-v002"
        p02_version = "knowledge-v003" if full_v003 else "knowledge-v002"
        p03_version = (
            "knowledge-v003"
            if full_v003
            else choose_p03_version(course_dir, force_v003=force)
        )
        p04_version = p03_version
        previous = (
            "knowledge-v002"
            if p03_version == "knowledge-v003" and not full_v003
            else None
        )
        payload = build_evidence_baseline(
            args.data_root,
            start_ordinal=ordinal,
            end_ordinal=ordinal,
            p01_version=p01_version,
            p02_version=p02_version,
            p03_version=p03_version,
            p04_version=p04_version,
            previous_p03_version=previous,
        )
        for course in payload["courses"]:
            for case in course["cases"]:
                # Entire-course v002: mark all cases unchanged and reuse v002 QA.
                if p03_version == "knowledge-v002":
                    case["source_case_changed"] = False
                # Unchanged case on a v003 course: reuse existing v002 P04.
                if (
                    p03_version == "knowledge-v003"
                    and not case.get("source_case_changed")
                    and case.get("qa_status") != "pass"
                ):
                    qa_v2 = (
                        course_dir
                        / "qa"
                        / f"P04-{case['case_id']}-knowledge-v002-qa.json"
                    )
                    if qa_v2.exists():
                        status = json.loads(
                            qa_v2.read_text(encoding="utf-8-sig")
                        ).get("status")
                        if status == "pass":
                            case["p04_version"] = "knowledge-v002"
                            case["qa_status"] = "pass"
                            continue
                if p03_version == "knowledge-v002":
                    qa = (
                        course_dir
                        / "qa"
                        / f"P04-{case['case_id']}-knowledge-v002-qa.json"
                    )
                    if qa.exists():
                        case["qa_status"] = json.loads(
                            qa.read_text(encoding="utf-8-sig")
                        ).get("status", case["qa_status"])
        courses.extend(payload["courses"])

    report = {
        "schema_version": "1.0",
        "policy": "adopt_v003_hybrid",
        "generated_from": "scripts/build_evidence_baseline_hybrid.py",
        "courses": courses,
    }
    write_evidence_baseline(args.output, report)
    print(f"Wrote {args.output}")
    for course in courses:
        print(
            course["course_id"],
            course["p03_version"],
            f"cases={len(course['cases'])}",
            "changed="
            + str(sum(1 for c in course["cases"] if c.get("source_case_changed"))),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
