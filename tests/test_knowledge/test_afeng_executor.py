from __future__ import annotations

from pathlib import Path
from typing import Any

from course_video_analyzer.knowledge.afeng_executor import (
    OpenAICompatibleAfengExecutor,
    OpenAICompatibleConfig,
    _extract_json_text,
)


def _draft() -> dict[str, Any]:
    evidence = ["SEG-C001-000001"]
    return {
        "schema_version": "1.0",
        "pipeline_version": "afeng-method-v001",
        "prompt_version": "mimo-method-v001",
        "knowledge_id": "AFENG-C001-CASE-C001-001",
        "course_id": "C001",
        "case_id": "CASE-C001-001",
        "method_name": "示例",
        "problem_addressed": {"content": "问题", "evidence_ids": evidence},
        "course_perspective": {"content": "按照课程方法", "evidence_ids": evidence},
        "applicable_conditions": [],
        "not_applicable_conditions": [],
        "core_logic": {
            "content": "课程逻辑",
            "evidence_ids": evidence,
            "evidence_level": "explicit",
        },
        "steps": [],
        "signals_used_by_course": [],
        "example_expressions": [],
        "course_reported_outcome": {
            "content": "",
            "evidence_ids": [],
            "evidence_level": "unknown",
        },
        "course_stated_limits": [],
        "insufficient_course_evidence": [],
        "source_time_range": {"start_ms": 0, "end_ms": 1},
        "draft_fidelity_status": "pending_review",
    }


def test_extract_json_text_accepts_code_fence_and_surrounding_text() -> None:
    assert _extract_json_text('```json\n{"ok": true}\n```') == {"ok": True}
    assert _extract_json_text('result:\n{"ok": true}\ndone') == {"ok": True}


def test_executor_retries_and_records_usage(tmp_path: Path) -> None:
    prompt_root = tmp_path / "prompts"
    prompt_root.mkdir()
    (prompt_root / "extract-method.md").write_text("only json", encoding="utf-8")
    attempts = 0

    def transport(body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        assert "Authorization" not in headers
        assert body["response_format"]["type"] == "json_schema"
        if attempts == 1:
            return {"choices": [{"message": {"content": "not json"}}]}
        import json

        return {
            "id": "req-1",
            "choices": [{"message": {"content": json.dumps(_draft(), ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    executor = OpenAICompatibleAfengExecutor(
        OpenAICompatibleConfig(
            endpoint="https://example.invalid/v1/chat/completions",
            model="test-model",
            max_retries=1,
            retry_delay_seconds=0,
            prompt_root=prompt_root,
            input_cost_per_million=1.0,
            output_cost_per_million=2.0,
        ),
        transport=transport,
    )
    result = executor.execute("extract_method", {"evidence_package": {}})
    assert attempts == 2
    assert result.output["knowledge_id"] == "AFENG-C001-CASE-C001-001"
    assert result.metadata["request_id"] == "req-1"
    assert result.metadata["total_tokens"] == 30
    assert result.metadata["estimated_cost"] == 0.00005


def test_render_stage_never_calls_model(tmp_path: Path) -> None:
    executor = OpenAICompatibleAfengExecutor(
        OpenAICompatibleConfig(endpoint="x", model="m", prompt_root=tmp_path),
        transport=lambda body, headers: {},
    )
    try:
        executor.execute("render_markdown", {})
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("render_markdown must not call a model")
