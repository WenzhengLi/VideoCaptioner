"""Command-line entry points for the versioned knowledge workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_video_analyzer.knowledge.catalog import initialize_knowledge_workspace
from course_video_analyzer.knowledge.runs import archive_successful_job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize the course knowledge workspace")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init", help="scan sources and create catalogs")
    init.add_argument("source_root", type=Path)
    init.add_argument("--data-root", type=Path, default=Path("data"))
    init.add_argument("--prompt-version", default="knowledge-v001")
    init.add_argument("--batch-id")
    archive = subparsers.add_parser("archive-job", help="archive a successful analyzer job")
    archive.add_argument("course_id")
    archive.add_argument("job_dir", type=Path)
    archive.add_argument("--data-root", type=Path, default=Path("data"))
    archive.add_argument("--run-id", required=True)
    archive.add_argument("--baseline", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "init":
        sources, courses, manifest = initialize_knowledge_workspace(
            args.source_root,
            args.data_root,
            prompt_version=args.prompt_version,
            batch_id=args.batch_id,
        )
        duplicates = [source for source in sources if source.duplicate_of]
        print(f"已登记来源: {len(sources)}")
        print(f"已登记课程: {len(courses)}")
        print(f"疑似重复且哈希确认: {len(duplicates)}")
        for source in duplicates:
            print(f"- {source.source_id} -> {source.duplicate_of}: {source.original_name}")
        print(f"批次清单: {manifest}")
    elif args.command == "archive-job":
        run_dir = archive_successful_job(
            args.course_id,
            args.job_dir,
            args.data_root,
            run_id=args.run_id,
            baseline=args.baseline,
        )
        print(f"已归档运行: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
