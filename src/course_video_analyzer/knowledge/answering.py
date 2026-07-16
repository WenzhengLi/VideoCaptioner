"""Cited multi-option answer generation over the local knowledge store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.cursor_runner import CursorStageConfig, run_cursor_stage
from course_video_analyzer.knowledge.store import build_answer_context

REQUIRED_STYLES = {"自然稳妥", "轻松幽默", "直接真诚"}


def validate_answer_output(context_path: Path, output_path: Path) -> dict[str, Any]:
    context = json.loads(Path(context_path).read_text(encoding="utf-8"))
    output = json.loads(Path(output_path).read_text(encoding="utf-8"))
    valid_entries = {item["id"] for item in context.get("retrieved_entries", [])}
    citations = output.get("knowledge_citations")
    invalid_citations: list[str] = []
    if isinstance(citations, list):
        for item in citations:
            if not isinstance(item, dict) or item.get("entry_id") not in valid_entries:
                invalid_citations.append(str(item))
    else:
        invalid_citations.append("knowledge_citations")
    plans = output.get("plans") if isinstance(output.get("plans"), list) else []
    invalid_plans: list[int] = []
    for index, plan in enumerate(plans):
        if not isinstance(plan, dict):
            invalid_plans.append(index)
            continue
        replies = plan.get("reply_options")
        reply_items = replies if isinstance(replies, list) else []
        styles = {
            str(item.get("style"))
            for item in reply_items
            if isinstance(item, dict)
        }
        if (
            not isinstance(replies, list)
            or not REQUIRED_STYLES <= styles
            or not isinstance(plan.get("applicability"), list)
            or not isinstance(plan.get("risks"), list)
            or not isinstance(plan.get("stop_conditions"), list)
        ):
            invalid_plans.append(index)
    checks = {
        "schema_version": output.get("schema_version") == "1.0",
        "query_preserved": output.get("query") == context.get("query"),
        "objective_facts_present": isinstance(output.get("objective_facts"), list),
        "multiple_interpretations": isinstance(output.get("interpretations"), list)
        and len(output["interpretations"]) >= 2,
        "multiple_plans": len(plans) >= 2,
        "plan_contract": not invalid_plans,
        "citations_valid": not invalid_citations,
        "limitations_present": isinstance(output.get("knowledge_limitations"), list),
        "safety_present": isinstance(output.get("safety_and_boundaries"), list),
    }
    return {
        "status": "pass" if all(checks.values()) else "needs_review",
        "checks": checks,
        "invalid_plan_indexes": invalid_plans,
        "invalid_citations": invalid_citations[:20],
    }


def answer_tidy_query(
    query: str,
    database_path: Path,
    output_path: Path,
    workspace: Path,
    *,
    prompt_root: Path = Path("prompts/knowledge-v002"),
    limit: int = 8,
) -> tuple[Path, Path]:
    output_path = Path(output_path).resolve()
    context_path = output_path.with_suffix(output_path.suffix + ".context.json")
    qa_path = output_path.with_suffix(output_path.suffix + ".qa.json")
    context = build_answer_context(database_path, query, limit=limit)
    atomic_write_text(context_path, json.dumps(context, ensure_ascii=False, indent=2))
    run_cursor_stage(
        "QUERY",
        "ANSWER",
        context_path,
        output_path,
        workspace,
        config=CursorStageConfig(
            model="auto",
            prompt_root=prompt_root,
            timeout_seconds=1200,
            finish_on_stable_output=True,
            output_stability_seconds=60,
        ),
    )
    report = validate_answer_output(context_path, output_path)
    atomic_write_text(qa_path, json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "pass":
        raise RuntimeError(f"知识库回答 QA 未通过: {qa_path}")
    return output_path, qa_path
