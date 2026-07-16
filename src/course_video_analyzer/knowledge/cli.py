"""Command-line entry points for the versioned knowledge workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from course_video_analyzer.knowledge.catalog import initialize_knowledge_workspace
from course_video_analyzer.knowledge.batch import mark_batch_item, run_batch
from course_video_analyzer.knowledge.cursor_runner import CursorStageConfig, run_cursor_stage
from course_video_analyzer.knowledge.cleaning_qa import write_p01_qa, write_p02_qa, write_p03_qa
from course_video_analyzer.knowledge.normalizer import (
    TranscriptNormalizerConfig,
    normalize_transcript_p01,
    restore_p01_speaker_clusters,
)
from course_video_analyzer.knowledge.classifier import classify_p02_baseline
from course_video_analyzer.knowledge.p02_review import build_p02_review_pack, apply_p02_review
from course_video_analyzer.knowledge.case_segmentation import build_p03_timeline_input
from course_video_analyzer.knowledge.extraction import build_p04_case_input, write_p04_qa
from course_video_analyzer.knowledge.safety_review import build_p05_input, write_p05_qa
from course_video_analyzer.knowledge.tidy_entries import (
    build_p06_input,
    export_tidy_markdown,
    write_p06_qa,
)
from course_video_analyzer.knowledge.store import (
    build_answer_context,
    index_tidy_entries,
    search_tidy_entries,
)
from course_video_analyzer.knowledge.answering import answer_tidy_query
from course_video_analyzer.knowledge.runs import archive_successful_job, write_run_qa
from course_video_analyzer.knowledge.dify_sync import (
    DifyConfig,
    create_dataset,
    sync_markdown_dir,
)


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
    cursor.add_argument("stage", choices=["P01", "P02", "P03", "P04", "P05", "P06", "ANSWER"])
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
    cursor.add_argument("--finish-on-stable-output", action="store_true")
    cursor.add_argument("--output-stability-seconds", type=int, default=30)
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
    p03_qa = subparsers.add_parser("qa-p03", help="validate P03 case boundaries and coverage")
    p03_qa.add_argument("course_id")
    p03_qa.add_argument("p02", type=Path)
    p03_qa.add_argument("output", type=Path)
    p03_qa.add_argument("report", type=Path)
    p03_qa.add_argument("--prompt-version", default="knowledge-v002-p03")
    normalize = subparsers.add_parser("normalize-p01", help="generate deterministic P01 baseline")
    normalize.add_argument("course_id")
    normalize.add_argument("transcript", type=Path)
    normalize.add_argument("output", type=Path)
    normalize.add_argument("--prompt-version", default="knowledge-v002-p01")
    repair_speakers = subparsers.add_parser(
        "repair-p01-speakers", help="restore raw diarization cluster IDs in an existing P01"
    )
    repair_speakers.add_argument("course_id")
    repair_speakers.add_argument("transcript", type=Path)
    repair_speakers.add_argument("p01", type=Path)
    repair_speakers.add_argument("output", type=Path)
    classify = subparsers.add_parser("classify-p02", help="generate deterministic P02 baseline")
    classify.add_argument("course_id")
    classify.add_argument("p01", type=Path)
    classify.add_argument("output", type=Path)
    classify.add_argument("--prompt-version", default="knowledge-v002-p02-baseline")
    p02_pack = subparsers.add_parser("build-p02-review", help="build compact P02 Cursor review pack")
    p02_pack.add_argument("course_id")
    p02_pack.add_argument("baseline", type=Path)
    p02_pack.add_argument("output", type=Path)
    p02_apply = subparsers.add_parser("apply-p02-review", help="apply compact P02 review decisions")
    p02_apply.add_argument("course_id")
    p02_apply.add_argument("baseline", type=Path)
    p02_apply.add_argument("review_pack", type=Path)
    p02_apply.add_argument("review", type=Path)
    p02_apply.add_argument("output", type=Path)
    p03_input = subparsers.add_parser("build-p03-input", help="build compact P03 timeline input")
    p03_input.add_argument("course_id")
    p03_input.add_argument("p02", type=Path)
    p03_input.add_argument("output", type=Path)
    p04_input = subparsers.add_parser("build-p04-input", help="build one isolated P04 case bundle")
    p04_input.add_argument("course_id")
    p04_input.add_argument("case_id")
    p04_input.add_argument("p02", type=Path)
    p04_input.add_argument("p03", type=Path)
    p04_input.add_argument("output", type=Path)
    p04_qa = subparsers.add_parser("qa-p04", help="validate P04 evidence references")
    p04_qa.add_argument("course_id")
    p04_qa.add_argument("case_id")
    p04_qa.add_argument("case_input", type=Path)
    p04_qa.add_argument("output", type=Path)
    p04_qa.add_argument("report", type=Path)
    p05_input = subparsers.add_parser("build-p05-input", help="build P05 evidence review bundle")
    p05_input.add_argument("course_id")
    p05_input.add_argument("case_id")
    p05_input.add_argument("case_input", type=Path)
    p05_input.add_argument("p04", type=Path)
    p05_input.add_argument("output", type=Path)
    p05_qa = subparsers.add_parser("qa-p05", help="validate P05 review coverage and evidence")
    p05_qa.add_argument("course_id")
    p05_qa.add_argument("case_id")
    p05_qa.add_argument("input", type=Path)
    p05_qa.add_argument("output", type=Path)
    p05_qa.add_argument("report", type=Path)
    p06_input = subparsers.add_parser("build-p06-input", help="build P06 atomic entry bundle")
    p06_input.add_argument("course_id")
    p06_input.add_argument("case_id")
    p06_input.add_argument("p04", type=Path)
    p06_input.add_argument("p05", type=Path)
    p06_input.add_argument("output", type=Path)
    p06_qa = subparsers.add_parser("qa-p06", help="validate P06 atomic entries")
    p06_qa.add_argument("course_id")
    p06_qa.add_argument("case_id")
    p06_qa.add_argument("input", type=Path)
    p06_qa.add_argument("output", type=Path)
    p06_qa.add_argument("report", type=Path)
    tidy_export = subparsers.add_parser(
        "export-tidy",
        aliases=["local-export-markdown"],
        help="export P06 entries as Markdown (local; not Dify)",
    )
    tidy_export.add_argument("p06", type=Path)
    tidy_export.add_argument("output_dir", type=Path)
    tidy_index = subparsers.add_parser(
        "index-tidy",
        aliases=["local-index-build"],
        help="index P06 into local SQLite FTS (offline regression; not Dify)",
    )
    tidy_index.add_argument("--data-root", type=Path, default=Path("data"))
    tidy_index.add_argument("--database", type=Path, default=Path("data/tidy/knowledge.db"))
    tidy_index.add_argument(
        "--output-version",
        default="knowledge-v002",
        help="P06 output directory suffix, e.g. knowledge-v002 or knowledge-v003",
    )
    tidy_search = subparsers.add_parser(
        "search-tidy",
        aliases=["local-index-search"],
        help="search local SQLite index (offline; not Dify)",
    )
    tidy_search.add_argument("query")
    tidy_search.add_argument("--database", type=Path, default=Path("data/tidy/knowledge.db"))
    tidy_search.add_argument("--limit", type=int, default=8)
    answer_context = subparsers.add_parser("answer-context", help="build cited multi-option answer context")
    answer_context.add_argument("query")
    answer_context.add_argument("output", type=Path)
    answer_context.add_argument("--database", type=Path, default=Path("data/tidy/knowledge.db"))
    answer_context.add_argument("--limit", type=int, default=8)
    tidy_answer = subparsers.add_parser(
        "answer-tidy",
        aliases=["local-index-answer"],
        help="local multi-option answer via SQLite+Cursor (not Dify Chatflow)",
    )
    tidy_answer.add_argument("query")
    tidy_answer.add_argument("output", type=Path)
    tidy_answer.add_argument("--database", type=Path, default=Path("data/tidy/knowledge.db"))
    tidy_answer.add_argument("--workspace", type=Path, default=Path.cwd())
    tidy_answer.add_argument("--limit", type=int, default=8)
    tidy_answer.add_argument(
        "--prompt-root",
        type=Path,
        default=Path("prompts/knowledge-v002"),
        help="Prompt directory used by Cursor answer stage",
    )
    dify_create = subparsers.add_parser(
        "dify-create-dataset",
        help="create a Dify Knowledge dataset via official API",
    )
    dify_create.add_argument("--name", default="VideoCaptioner Courses")
    dify_create.add_argument("--description", default="Course knowledge from P06 Markdown")
    dify_sync = subparsers.add_parser(
        "dify-sync-markdown",
        help="idempotently sync Markdown knowledge files into a Dify dataset",
    )
    dify_sync.add_argument(
        "--markdown-root",
        type=Path,
        default=Path("data/courses"),
        help="Courses root or a markdown directory containing *.md",
    )
    dify_sync.add_argument(
        "--map-path",
        type=Path,
        default=Path("data/dify/document-map.json"),
        help="Local knowledge_id to document_id map (runtime; do not commit secrets)",
    )
    dify_sync.add_argument("--dataset-id", default=None)
    dify_sync.add_argument("--limit", type=int, default=None)
    dify_sync.add_argument("--poll-indexing", action="store_true")
    dify_status = subparsers.add_parser(
        "dify-status",
        help="show local Dify document map summary (does not imply Dify is running)",
    )
    dify_status.add_argument(
        "--map-path",
        type=Path,
        default=Path("data/dify/document-map.json"),
    )
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
                finish_on_stable_output=args.finish_on_stable_output,
                output_stability_seconds=args.output_stability_seconds,
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
    elif args.command == "qa-p03":
        report = write_p03_qa(
            args.course_id,
            args.p02,
            args.output,
            args.report,
            expected_prompt_version=args.prompt_version,
        )
        print(f"P03 QA 报告: {report}")
    elif args.command == "normalize-p01":
        output = normalize_transcript_p01(
            args.course_id,
            args.transcript,
            args.output,
            config=TranscriptNormalizerConfig(prompt_version=args.prompt_version),
        )
        print(f"P01 基线完成: {output}")
    elif args.command == "repair-p01-speakers":
        output = restore_p01_speaker_clusters(
            args.course_id,
            args.transcript,
            args.p01,
            args.output,
        )
        print(f"P01 说话人聚类恢复完成: {output}")
    elif args.command == "classify-p02":
        output = classify_p02_baseline(
            args.course_id,
            args.p01,
            args.output,
            prompt_version=args.prompt_version,
        )
        print(f"P02 基线完成: {output}")
    elif args.command == "build-p02-review":
        output = build_p02_review_pack(args.course_id, args.baseline, args.output)
        print(f"P02 紧凑复核包完成: {output}")
    elif args.command == "apply-p02-review":
        output = apply_p02_review(
            args.course_id,
            args.baseline,
            args.review_pack,
            args.review,
            args.output,
        )
        print(f"P02 复核决策已应用: {output}")
    elif args.command == "build-p03-input":
        output = build_p03_timeline_input(args.course_id, args.p02, args.output)
        print(f"P03 紧凑时间线完成: {output}")
    elif args.command == "build-p04-input":
        output = build_p04_case_input(
            args.course_id,
            args.case_id,
            args.p02,
            args.p03,
            args.output,
        )
        print(f"P04 单案例输入完成: {output}")
    elif args.command == "qa-p04":
        output = write_p04_qa(
            args.course_id,
            args.case_id,
            args.case_input,
            args.output,
            args.report,
        )
        print(f"P04 QA 报告: {output}")
    elif args.command == "build-p05-input":
        output = build_p05_input(
            args.course_id,
            args.case_id,
            args.case_input,
            args.p04,
            args.output,
        )
        print(f"P05 审查输入完成: {output}")
    elif args.command == "qa-p05":
        output = write_p05_qa(
            args.course_id,
            args.case_id,
            args.input,
            args.output,
            args.report,
        )
        print(f"P05 QA 报告: {output}")
    elif args.command == "build-p06-input":
        output = build_p06_input(args.course_id, args.case_id, args.p04, args.p05, args.output)
        print(f"P06 原子条目输入完成: {output}")
    elif args.command == "qa-p06":
        output = write_p06_qa(args.course_id, args.case_id, args.input, args.output, args.report)
        print(f"P06 QA 报告: {output}")
    elif args.command in {"export-tidy", "local-export-markdown"}:
        outputs = export_tidy_markdown(args.p06, args.output_dir)
        print(f"本地 Markdown 已输出: {len(outputs)}（非 Dify）")
    elif args.command in {"index-tidy", "local-index-build"}:
        result = index_tidy_entries(
            args.data_root,
            args.database,
            output_version=args.output_version,
        )
        print(json.dumps(result, ensure_ascii=False))
    elif args.command in {"search-tidy", "local-index-search"}:
        result = search_tidy_entries(args.database, args.query, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "answer-context":
        result = build_answer_context(args.database, args.query, limit=args.limit)
        from course_video_analyzer.jobs.workspace import atomic_write_text

        atomic_write_text(args.output, json.dumps(result, ensure_ascii=False, indent=2))
        print(f"多方案回答上下文已输出: {args.output}")
    elif args.command in {"answer-tidy", "local-index-answer"}:
        output, qa = answer_tidy_query(
            args.query,
            args.database,
            args.output,
            args.workspace,
            prompt_root=args.prompt_root,
            limit=args.limit,
        )
        print(f"本地多方案回答完成: {output}; QA={qa}（非 Dify Chatflow）")
    elif args.command == "dify-create-dataset":
        cfg = DifyConfig.from_env(require_dataset=False)
        result = create_dataset(cfg, args.name, description=args.description)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        dataset_id = result.get("id")
        if dataset_id:
            print(f"请将 DIFY_DATASET_ID={dataset_id} 写入本地环境（勿提交）。")
    elif args.command == "dify-sync-markdown":
        cfg = DifyConfig.from_env(require_dataset=args.dataset_id is None)
        root = Path(args.markdown_root)
        if root.is_dir() and any(root.glob("*.md")):
            markdown_dirs = [root]
        else:
            markdown_dirs = sorted({p.parent for p in root.glob("**/markdown-*/*.md")})
        totals: dict = {"created": 0, "skipped": 0, "failed": [], "dirs": []}
        remaining = args.limit
        for md_dir in markdown_dirs:
            part = sync_markdown_dir(
                cfg,
                md_dir,
                args.map_path,
                dataset_id=args.dataset_id,
                limit=remaining,
                poll_indexing=args.poll_indexing,
            )
            totals["created"] += int(part["created"])
            totals["skipped"] += int(part["skipped"])
            totals["failed"].extend(part["failed"])
            totals["dirs"].append(str(md_dir))
            if remaining is not None:
                remaining = max(0, remaining - int(part["created"]))
                if remaining == 0:
                    break
        totals["map_path"] = str(args.map_path)
        print(json.dumps(totals, ensure_ascii=False, indent=2))
    elif args.command == "dify-status":
        from course_video_analyzer.knowledge.dify_sync import load_document_map

        mapping = load_document_map(args.map_path)
        docs = mapping.get("documents") or {}
        print(
            json.dumps(
                {
                    "map_path": str(args.map_path),
                    "dataset_id": mapping.get("dataset_id"),
                    "document_count": len(docs),
                    "updated_at": mapping.get("updated_at"),
                    "note": "本地映射摘要；不等于 Dify 容器已运行或 indexing 已完成",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
