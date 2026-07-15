"""CLI entry: ``python -m benchmarks.run`` / ``course-video-benchmark``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from benchmarks.evaluate import evaluate_file
from benchmarks.report import write_reports
from benchmarks.schema import load_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="course-video-benchmark",
        description="Evaluate Course Video Analyzer components against a local manifest.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to manifest JSON (paths + annotations only).",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=None,
        help="Optional predictions JSON keyed by sample_id.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("benchmarks/output"),
        help="Directory for JSON/Markdown reports.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List missing media and skip evaluation without failing.",
    )
    parser.add_argument(
        "--list-missing",
        action="store_true",
        help="Only print missing media paths and exit 0.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.manifest.exists():
        print(f"manifest 不存在: {args.manifest}", file=sys.stderr)
        return 2

    manifest = load_manifest(args.manifest)
    missing = []
    for sample in manifest.samples:
        media = manifest.resolve_media_path(sample)
        if not media.exists():
            missing.append(str(media))

    if args.list_missing or args.dry_run:
        print(f"manifest: {manifest.name}")
        print(f"samples: {len(manifest.samples)}")
        print("missing media:")
        if missing:
            for path in missing:
                print(f"  - {path}")
        else:
            print("  (none)")
        if args.list_missing and not args.dry_run:
            return 0

    result = evaluate_file(
        args.manifest,
        predictions_path=args.predictions,
        dry_run=args.dry_run,
    )
    paths = write_reports(result, args.output_dir)
    print(json.dumps({"ok": True, "reports": {k: str(v) for k, v in paths.items()}}, ensure_ascii=False))
    # Missing media is never a hard failure for dry-run / default offline mode.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
