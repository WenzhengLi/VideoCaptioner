#!/usr/bin/env python3
"""Run the frozen 20-question acceptance suite against the real Afeng app."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from scripts.deploy_afeng_dify_app import (
    ADMIN_ENV_PATH,
    APP_NAME,
    BASE_URL,
    ConsoleClient,
    _find_app,
    _load_env,
    _parse_sse_answer,
)
from scripts.validate_afeng_citations import validate_citations


TEST_SET = Path("data/dify/afeng-retrieval-test-v002.json")
MANIFEST = Path("data/dify/afeng-release-v002.6/manifest.json")
JSON_OUTPUT = Path("data/dify/afeng-app-acceptance.json")
MD_OUTPUT = Path("docs/evaluation/afeng-app-acceptance.md")


def _citation_sources() -> tuple[set[str], dict[str, set[str]]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    known: set[str] = set()
    evidence: dict[str, set[str]] = {}
    for document in manifest["documents"]:
        knowledge_id = str(document["knowledge_id"])
        known.add(knowledge_id)
        path = Path(str(document["document_path"]))
        evidence[knowledge_id] = set(re.findall(r"SEG-C\d{3}-\d{6}", path.read_text(encoding="utf-8")))
    return known, evidence


def _expected_coverage(answer: dict[str, Any], expected: str | list[str]) -> dict[str, Any]:
    claims = answer.get("claims", []) if isinstance(answer, dict) else []
    cited = {str(claim.get("knowledge_id")) for claim in claims if isinstance(claim, dict)}
    expected_ids = set(expected if isinstance(expected, list) else [expected])
    found = sorted(expected_ids & cited)
    return {
        "expected": sorted(expected_ids),
        "found": found,
        "complete": expected_ids <= cited,
    }


def main() -> int:
    test_payload = json.loads(TEST_SET.read_text(encoding="utf-8"))
    questions = test_payload["questions"]
    known, citation_index = _citation_sources()
    admin = _load_env(ADMIN_ENV_PATH)
    client = ConsoleClient(BASE_URL)
    client.login(admin["DIFY_ADMIN_EMAIL"], admin["DIFY_ADMIN_PASSWORD"])
    app = _find_app(client, APP_NAME)
    if not app:
        raise RuntimeError("Afeng app is not deployed")
    app_id = str(app["id"])

    results: list[dict[str, Any]] = []
    for position, item in enumerate(questions, start=1):
        query = str(item["question"])
        raw = client.request(
            "POST",
            f"/console/api/apps/{app_id}/advanced-chat/workflows/draft/run",
            {"inputs": {}, "query": query, "files": []},
            raw=True,
            timeout=180,
        )
        answer_text, errors = _parse_sse_answer(raw)
        try:
            answer = json.loads(answer_text)
            json_valid = True
        except json.JSONDecodeError:
            answer = {}
            json_valid = False
        validation = validate_citations(answer, known, citation_index) if json_valid else {
            "valid": False,
            "issues": ["invalid JSON"],
        }
        coverage = _expected_coverage(answer, item.get("expected_canonical", ""))
        insufficient = bool(answer.get("evidence_insufficient")) if isinstance(answer, dict) else False
        passed = bool(json_valid and not errors and validation["valid"] and (coverage["complete"] or insufficient))
        results.append(
            {
                "id": item["id"],
                "category": item.get("category", ""),
                "question": query,
                "json_valid": json_valid,
                "errors": errors,
                "citation_validation": validation,
                "expected_coverage": coverage,
                "evidence_insufficient": insufficient,
                "passed": passed,
                "answer": answer if json_valid else answer_text,
            }
        )
        print(f"[{position:02d}/{len(questions)}] {item['id']}: {'PASS' if passed else 'FAIL'}", flush=True)

    passed_count = sum(1 for result in results if result["passed"])
    report = {
        "schema_version": "1.0",
        "test_type": "afeng-app-acceptance",
        "app_name": APP_NAME,
        "app_id": app_id,
        "test_set": str(TEST_SET).replace("\\", "/"),
        "total": len(results),
        "passed": passed_count,
        "pass_rate": round(passed_count / len(results) * 100, 1),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": results,
    }
    JSON_OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 阿峰 Dify 应用 20 问验收报告",
        "",
        f"- 生成时间：{report['timestamp']}",
        f"- 结果：{passed_count}/{len(results)}（{report['pass_rate']}%）",
        "- 通过条件：合法 JSON、无 Workflow 错误、引用硬校验通过，并命中预期 canonical 文档或明确返回证据不足。",
        "",
        "| ID | 类别 | JSON | 引用 | 预期覆盖 | 证据不足 | 结果 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result['id']} | {result['category']} | "
            f"{'PASS' if result['json_valid'] else 'FAIL'} | "
            f"{'PASS' if result['citation_validation']['valid'] else 'FAIL'} | "
            f"{'PASS' if result['expected_coverage']['complete'] else 'MISS'} | "
            f"{'YES' if result['evidence_insufficient'] else 'NO'} | "
            f"{'PASS' if result['passed'] else 'FAIL'} |"
        )
    MD_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed_count, "total": len(results), "report": str(JSON_OUTPUT)}, ensure_ascii=False))
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
