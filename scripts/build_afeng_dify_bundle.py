#!/usr/bin/env python3
"""Build an offline Dify-ready bundle from published Afeng model runs."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_video_analyzer.knowledge.afeng_dify import build_afeng_dify_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_run_summaries", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    result = build_afeng_dify_bundle(
        args.model_run_summaries,
        args.output_dir,
        args.manifest,
    )
    print(
        f"Afeng Dify bundle: documents={result['document_count']} "
        f"excluded={result['excluded_count']}"
    )
    print(f"Manifest: {args.manifest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
