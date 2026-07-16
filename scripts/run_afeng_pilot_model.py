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
    OpenAICompatibleAfengExecutor,
    OpenAICompatibleConfig,
)
from course_video_analyzer.knowledge.afeng_experiment import PilotManifest
from course_video_analyzer.knowledge.afeng_pipeline import run_afeng_method_pipeline


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("data/afeng/model-runs"))
    parser.add_argument("--max-revisions", type=int, default=2)
    parser.add_argument("--endpoint")
    parser.add_argument("--model")
    parser.add_argument("--api-key-env", default="AFENG_LLM_API_KEY")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--without-json-schema", action="store_true")
    parser.add_argument("--input-cost-per-million", type=float)
    parser.add_argument("--output-cost-per-million", type=float)
    args = parser.parse_args()
    pilot = PilotManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    if args.endpoint and args.model:
        config = OpenAICompatibleConfig(
            endpoint=args.endpoint,
            model=args.model,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
            structured_output=not args.without_json_schema,
            input_cost_per_million=args.input_cost_per_million,
            output_cost_per_million=args.output_cost_per_million,
        )
    else:
        env_config = OpenAICompatibleConfig.from_env()
        config = OpenAICompatibleConfig(
            endpoint=env_config.endpoint,
            model=env_config.model,
            api_key_env=args.api_key_env,
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
            structured_output=not args.without_json_schema,
            input_cost_per_million=args.input_cost_per_million,
            output_cost_per_million=args.output_cost_per_million,
        )
    executor = OpenAICompatibleAfengExecutor(config)
    results = []
    failures = []
    run_root = args.output_root.resolve() / pilot.pilot_id
    for case in pilot.cases:
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
    output = {
        "schema_version": "1.0",
        "pilot_id": pilot.pilot_id,
        "model": config.model,
        "endpoint": _safe_endpoint(config.endpoint),
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
