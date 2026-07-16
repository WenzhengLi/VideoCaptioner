#!/usr/bin/env python3
"""Refresh evidence-baseline qa_status from on-disk P04 QA reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("data/catalog/evidence-baseline-C001-C015.json"),
    )
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    updated = 0
    for course in baseline.get("courses") or []:
        course_id = course["course_id"]
        for case in course.get("cases") or []:
            case_id = case["case_id"]
            p04_version = case["p04_version"]
            qa_path = (
                args.data_root
                / "courses"
                / course_id
                / "qa"
                / f"P04-{case_id}-{p04_version}-qa.json"
            )
            if not qa_path.exists():
                if case.get("qa_status") != "missing":
                    case["qa_status"] = "missing"
                    updated += 1
                continue
            qa = json.loads(qa_path.read_text(encoding="utf-8"))
            status = qa.get("status") or "missing"
            if case.get("qa_status") != status:
                case["qa_status"] = status
                updated += 1
    args.baseline.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"refreshed {args.baseline}; updated_fields={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
