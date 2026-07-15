"""Run exactly one video per process for isolated, resumable batch execution."""

from __future__ import annotations

import argparse
from pathlib import Path

from course_video_analyzer.jobs.workspace import JobWorkspace
from course_video_analyzer.knowledge.runs import archive_successful_job
from course_video_analyzer.pipeline import create_default_analysis_service
from course_video_analyzer.processing_profiles import DEFAULT_PROCESSING_PROFILE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze one course video in an isolated resumable process"
    )
    parser.add_argument("video", type=Path)
    parser.add_argument("--jobs-root", type=Path, default=Path("jobs/batch"))
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--processing-profile", default=DEFAULT_PROCESSING_PROFILE)
    parser.add_argument("--interval-ms", type=int, default=5000)
    parser.add_argument("--max-frames", type=int, default=800)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--archive-course")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--run-id")
    parser.add_argument("--baseline", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    jobs_root = args.jobs_root.resolve()
    workspace = JobWorkspace(jobs_root, job_id=args.job_id)
    if workspace.job_json.exists():
        if args.no_resume:
            raise FileExistsError(f"任务已存在且禁止恢复: {workspace.job_dir}")
    else:
        workspace.create(
            args.video.resolve(),
            config={
                "processing_profile": args.processing_profile,
                "interval_ms": args.interval_ms,
                "max_frames": args.max_frames,
                "device": args.device,
            },
        )

    service = create_default_analysis_service()
    service.run(workspace, resume=not args.no_resume)
    print(f"分析完成: {workspace.job_dir}")

    if args.archive_course:
        if not args.run_id:
            raise ValueError("指定 --archive-course 时必须同时指定 --run-id")
        run_dir = archive_successful_job(
            args.archive_course,
            workspace.job_dir,
            args.data_root,
            run_id=args.run_id,
            baseline=args.baseline,
        )
        print(f"归档完成: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
