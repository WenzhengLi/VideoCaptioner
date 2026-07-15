"""Command-line entry points for the versioned knowledge workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_video_analyzer.knowledge.catalog import initialize_knowledge_workspace
from course_video_analyzer.knowledge.batch import mark_batch_item, run_batch
from course_video_analyzer.knowledge.cursor_runner import CursorStageConfig, run_cursor_stage
from course_video_analyzer.knowledge.cleaning_qa import write_p01_qa, write_p02_qa
from course_video_analyzer.knowledge.normalizer import (
    TranscriptNormalizerConfig,
    normalize_transcript_p01,
)
from course_video_analyzer.knowledge.classifier import classify_p02_baseline
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
    cursor = subparsers.add_parser("cursor-stage", help="run one isolated Cursor cleaning stage")
    cursor.add_argument("course_id")
    cursor.add_argument("stage", choices=["P01", "P02", "P03", "P04", "P05", "P06"])
    cursor.add_argument("input", type=Path)
    cursor.add_argument("output", type=Path)
    cursor.add_argument("--workspace", type=Path, default=Path.cwd())
    cursor.add_argument(
        "--cursor-agent",
        type=Path,
        default=Path(r"C:\Users\Administrator\AppData\Local\cursor-agent\cursor-agent.cmd"),
    )
    cursor.add_argument("--model", default="auto")
    cursor.add_argument("--prompt-root", type=Path, default=Path("prompts/knowledge-v001"))
    cursor.add_argument("--timeout-seconds", type=int, default=3600)
    mark = subparsers.add_parser("mark-batch", help="reconcile one course into a batch")
    mark.add_argument("batch_id")
    mark.add_argument("course_id")
    mark.add_argument("status", choices=["pending", "running", "succeeded", "failed", "needs_review"])
    mark.add_argument("--run-id")
    mark.add_argument("--error")
    mark.add_argument("--data-root", type=Path, default=Path("data"))
    clean_qa = subparsers.add_parser("qa-p01", help="validate P01 completeness and schema")
    clean_qa.add_argument("course_id")
    clean_qa.add_argument("transcript", type=Path)
    clean_qa.add_argument("output", type=Path)
    clean_qa.add_argument("report", type=Path)
    clean_qa.add_argument("--prompt-version", default="knowledge-v001-p01")
    p02_qa = subparsers.add_parser("qa-p02", help="validate P02 preservation and schema")
    p02_qa.add_argument("course_id")
    p02_qa.add_argument("p01", type=Path)
    p02_qa.add_argument("output", type=Path)
    p02_qa.add_argument("report", type=Path)
    p02_qa.add_argument("--prompt-version", default="knowledge-v002-p02")
    normalize = subparsers.add_parser("normalize-p01", help="generate deterministic P01 baseline")
    normalize.add_argument("course_id")
    normalize.add_argument("transcript", type=Path)
    normalize.add_argument("output", type=Path)
    normalize.add_argument("--prompt-version", default="knowledge-v002-p01")
    classify = subparsers.add_parser("classify-p02", help="generate deterministic P02 baseline")
    classify.add_argument("course_id")
    classify.add_argument("p01", type=Path)
    classify.add_argument("output", type=Path)
    classify.add_argument("--prompt-version", default="knowledge-v002-p02-baseline")
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
    elif args.command == "cursor-stage":
        result = run_cursor_stage(
            args.course_id,
            args.stage,
            args.input,
            args.output,
            args.workspace,
            config=CursorStageConfig(
                cursor_agent=args.cursor_agent,
                model=args.model,
                prompt_root=args.prompt_root,
                timeout_seconds=args.timeout_seconds,
            ),
        )
        print(f"Cursor 阶段完成: {result}")
    elif args.command == "mark-batch":
        from course_video_analyzer.knowledge.models import CourseStatus

        mark_batch_item(
            args.batch_id,
            args.course_id,
            CourseStatus(args.status),
            args.data_root,
            run_id=args.run_id,
            error=args.error,
        )
        print(f"批次状态已更新: {args.course_id} -> {args.status}")
    elif args.command == "qa-p01":
        report = write_p01_qa(
            args.course_id,
            args.transcript,
            args.output,
            args.report,
            expected_prompt_version=args.prompt_version,
        )
        print(f"P01 QA 报告: {report}")
    elif args.command == "qa-p02":
        report = write_p02_qa(
            args.course_id,
            args.p01,
            args.output,
            args.report,
            expected_prompt_version=args.prompt_version,
        )
        print(f"P02 QA 报告: {report}")
    elif args.command == "normalize-p01":
        output = normalize_transcript_p01(
            args.course_id,
            args.transcript,
            args.output,
            config=TranscriptNormalizerConfig(prompt_version=args.prompt_version),
        )
        print(f"P01 基线完成: {output}")
    elif args.command == "classify-p02":
        output = classify_p02_baseline(
            args.course_id,
            args.p01,
            args.output,
            prompt_version=args.prompt_version,
        )
        print(f"P02 基线完成: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
