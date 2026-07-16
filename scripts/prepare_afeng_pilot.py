#!/usr/bin/env python3
"""Prepare C003/C006/C010 Afeng evidence packages without calling a model."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from course_video_analyzer.knowledge.afeng_experiment import (
    DEFAULT_PILOT_COURSES,
    build_legacy_baseline,
    load_evidence_baseline,
    prepare_afeng_pilot,
    write_baseline,
    write_manual_review_template,
    write_pilot_summary,
)
from course_video_analyzer.knowledge.afeng_models import ExternalSegmentProfile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--legacy-version", default="knowledge-v002")
    parser.add_argument("--courses", default=",".join(DEFAULT_PILOT_COURSES))
    parser.add_argument("--pilot-id", default="C003-C006-C010-prebaseline-v002")
    parser.add_argument("--output-root", type=Path, default=Path("data/afeng/pilots"))
    parser.add_argument("--historical-p05-version", default="knowledge-v002")
    parser.add_argument(
        "--external-segment-profile",
        choices=["full", "evidence_focused"],
        default="evidence_focused",
    )
    parser.add_argument("--external-context-window", type=int, default=1)
    args = parser.parse_args()
    courses = [item.strip() for item in args.courses.split(",") if item.strip()]
    if args.baseline:
        baseline_path = args.baseline.resolve()
        baseline = load_evidence_baseline(baseline_path)
    else:
        baseline = build_legacy_baseline(
            args.data_root.resolve(), courses, version=args.legacy_version
        )
        baseline_path = (
            args.output_root.resolve() / args.pilot_id / "temporary-baseline.json"
        )
        write_baseline(baseline_path, baseline)
    manifest = prepare_afeng_pilot(
        baseline,
        baseline_path,
        args.data_root.resolve(),
        args.output_root.resolve(),
        pilot_id=args.pilot_id,
        course_ids=courses,
        historical_p05_version=args.historical_p05_version or None,
        external_segment_profile=cast(ExternalSegmentProfile, args.external_segment_profile),
        external_context_window=args.external_context_window,
    )
    summary = args.output_root.resolve() / args.pilot_id / "summary.md"
    write_pilot_summary(manifest, summary)
    review_json = args.output_root.resolve() / args.pilot_id / "manual-review.json"
    review_md = args.output_root.resolve() / args.pilot_id / "manual-review.md"
    write_manual_review_template(manifest, review_json, review_md)
    print(f"Afeng pilot prepared: {manifest.status}; cases={len(manifest.cases)}")
    print(f"Manifest: {args.output_root.resolve() / args.pilot_id / 'manifest.json'}")
    print(f"Summary: {summary}")
    print(f"Manual review: {review_md}")
    return 0 if manifest.status == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
