"""Command-line entry points for the versioned knowledge workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_video_analyzer.knowledge.catalog import initialize_knowledge_workspace
from course_video_analyzer.knowledge.batch import run_batch
from course_video_analyzer.knowledge.runs import archive_successful_job, write_run_qa


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
    qa = subparsers.add_parser("qa-run", help="validate an archived transcript")
    qa.add_argument("course_id")
    qa.add_argument("run_id")
    qa.add_argument("--data-root", type=Path, default=Path("data"))
    batch = subparsers.add_parser("run-batch", help="run courses serially with retries")
    batch.add_argument("batch_id")
    batch.add_argument("--data-root", type=Path, default=Path("data"))
    batch.add_argument("--jobs-root", type=Path, default=Path("jobs/batch"))
    batch.add_argument("--start", type=int)
    batch.add_argument("--end", type=int)
    batch.add_argument("--run-version", default="V001")
    batch.add_argument("--processing-profile", default="complete-v1")
    batch.add_argument("--timeout-seconds", type=int, default=14_400)
    batch.add_argument("--max-attempts", type=int, default=2)
    batch.add_argument("--ffmpeg-bin", type=Path)
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
    elif args.command == "qa-run":
        report = write_run_qa(args.course_id, args.run_id, args.data_root)
        print(f"QA 报告: {report}")
    elif args.command == "run-batch":
        manifest = run_batch(
            args.batch_id,
            args.data_root,
            args.jobs_root,
            start_ordinal=args.start,
            end_ordinal=args.end,
            run_version=args.run_version,
            processing_profile=args.processing_profile,
            timeout_seconds=args.timeout_seconds,
            max_attempts=args.max_attempts,
            ffmpeg_bin=args.ffmpeg_bin,
        )
        succeeded = sum(item.status.value == "succeeded" for item in manifest.items)
        failed = sum(item.status.value == "failed" for item in manifest.items)
        print(f"批次完成: succeeded={succeeded}, failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
