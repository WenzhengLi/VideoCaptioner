#!/usr/bin/env python3
"""Run model-backed Afeng stages for an already prepared pilot manifest."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.afeng_executor import (
    ClaudeCodeCcSwitchConfig,
    ClaudeCodeCcSwitchExecutor,
    OpenAICompatibleAfengExecutor,
    OpenAICompatibleConfig,
)
from course_video_analyzer.knowledge.afeng_experiment import PilotManifest
from course_video_analyzer.knowledge.afeng_models import AfengRunManifest
from course_video_analyzer.knowledge.afeng_pipeline import run_afeng_method_pipeline


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _collect_run_state(
    run_root: Path, pilot: PilotManifest, model_name: str
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    """Rebuild the summary from immutable case manifests after partial reruns."""
    allowed = {(item.course_id, item.case_id) for item in pilot.cases}
    latest: dict[tuple[str, str], tuple[int, AfengRunManifest]] = {}
    for path in run_root.glob("courses/*/06_afeng_methods/runs/*.json"):
        try:
            manifest = AfengRunManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        key = (manifest.course_id, manifest.case_id)
        if key not in allowed or manifest.model != model_name:
            continue
        modified = path.stat().st_mtime_ns
        if key not in latest or modified > latest[key][0]:
            latest[key] = (modified, manifest)
    results: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for key in sorted(latest):
        manifest = latest[key][1]
        if manifest.status == "failed":
            error = next(
                (event.error for event in reversed(manifest.events) if event.error),
                "case pipeline failed; inspect its run manifest",
            )
            failures.append(
                {"course_id": manifest.course_id, "case_id": manifest.case_id, "error": error}
            )
        else:
            results.append(manifest.model_dump(mode="json"))
    return results, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("data/afeng/model-runs"))
    parser.add_argument("--run-name", default="all")
    parser.add_argument("--courses", default=None)
    parser.add_argument("--case-ids", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--executor", choices=["cc-switch", "http"], default="cc-switch")
    parser.add_argument("--max-revisions", type=int, default=2)
    parser.add_argument("--endpoint")
    parser.add_argument("--model")
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument(
        "--response-format",
        choices=["json_schema", "json_object", "none"],
        default=None,
    )
    parser.add_argument("--thinking", choices=["enabled", "disabled"], default=None)
    parser.add_argument("--max-completion-tokens", type=int, default=16384)
    parser.add_argument("--input-cost-per-million", type=float)
    parser.add_argument("--output-cost-per-million", type=float)
    parser.add_argument("--max-budget-usd", type=float, default=2.0)
    parser.add_argument("--cc-settings", type=Path, default=Path.home() / ".claude" / "settings.json")
    args = parser.parse_args()
    pilot = PilotManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    selected_courses = (
        {item.strip() for item in args.courses.split(",") if item.strip()}
        if args.courses
        else None
    )
    selected_cases = (
        {item.strip() for item in args.case_ids.split(",") if item.strip()}
        if args.case_ids
        else None
    )
    pilot_cases = [
        item
        for item in pilot.cases
        if (selected_courses is None or item.course_id in selected_courses)
        and (selected_cases is None or item.case_id in selected_cases)
    ]
    if args.limit is not None:
        pilot_cases = pilot_cases[: args.limit]
    if not pilot_cases:
        raise ValueError("no pilot cases matched the requested filters")
    if args.executor == "cc-switch":
        cc_model = args.model or "mimo-v2.5-pro"
        config = ClaudeCodeCcSwitchConfig(
            model=cc_model,
            timeout_seconds=max(args.timeout_seconds, 300),
            max_retries=args.max_retries,
            max_budget_usd=args.max_budget_usd,
            settings_path=args.cc_settings,
            working_directory=args.output_root.resolve() / ".claude-runtime",
        )
        executor = ClaudeCodeCcSwitchExecutor(config)
        endpoint_summary = "cc-switch://claude-code"
        model_name = config.model
    elif args.endpoint and args.model:
        config = OpenAICompatibleConfig(
            endpoint=args.endpoint,
            model=args.model,
            api_key_env=args.api_key_env or "AFENG_LLM_API_KEY",
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
            response_format=args.response_format or "json_schema",
            thinking=args.thinking,
            max_completion_tokens=args.max_completion_tokens,
            input_cost_per_million=args.input_cost_per_million,
            output_cost_per_million=args.output_cost_per_million,
        )
        executor = OpenAICompatibleAfengExecutor(config)
        endpoint_summary = _safe_endpoint(config.endpoint)
        model_name = config.model
    else:
        env_config = OpenAICompatibleConfig.mimo_v25_pro()
        config = OpenAICompatibleConfig(
            endpoint=env_config.endpoint,
            model=env_config.model,
            api_key_env=args.api_key_env or env_config.api_key_env,
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
            response_format=args.response_format or env_config.response_format,
            thinking=args.thinking or env_config.thinking,
            temperature=env_config.temperature,
            top_p=env_config.top_p,
            max_completion_tokens=args.max_completion_tokens,
            input_cost_per_million=args.input_cost_per_million
            if args.input_cost_per_million is not None
            else env_config.input_cost_per_million,
            output_cost_per_million=args.output_cost_per_million
            if args.output_cost_per_million is not None
            else env_config.output_cost_per_million,
            cost_currency=env_config.cost_currency,
        )
        executor = OpenAICompatibleAfengExecutor(config)
        endpoint_summary = _safe_endpoint(config.endpoint)
        model_name = config.model
    results = []
    failures = []
    run_root = args.output_root.resolve() / pilot.pilot_id / args.run_name
    for case in pilot_cases:
        try:
            manifest = run_afeng_method_pipeline(
                Path(case.evidence_path),
                run_root / "courses" / case.course_id,
                executor,
                max_revisions=args.max_revisions,
                external_segment_profile=pilot.external_segment_profile,
                external_context_window=pilot.external_context_window,
            )
            results.append(manifest.model_dump(mode="json"))
        except Exception as exc:
            failures.append(
                {"course_id": case.course_id, "case_id": case.case_id, "error": str(exc)}
            )
    results, failures = _collect_run_state(run_root, pilot, model_name)
    output = {
        "schema_version": "1.0",
        "pilot_id": pilot.pilot_id,
        "run_name": args.run_name,
        "executor": args.executor,
        "model": model_name,
        "endpoint": endpoint_summary,
        "completed_at": _utc_now(),
        "status": "complete" if not failures else "needs_review",
        "results": results,
        "failures": failures,
    }
    output_path = run_root / "model-run-summary.json"
    atomic_write_text(output_path, json.dumps(output, ensure_ascii=False, indent=2))
    print(f"Afeng model pilot: {output['status']}; results={len(results)} failures={len(failures)}")
    print(f"Summary: {output_path}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
