#!/usr/bin/env python3
"""Run Afeng retrieval test suite against a Dify Dataset.

Loads the 20-question test set, queries Dify's retrieve API,
and generates a JSON + Markdown validation report.

Usage:
    python scripts/run_afeng_retrieval_test.py \
      --test-set data/dify/afeng-retrieval-test-v001.json \
      --map-path data/dify/document-map-v1.json \
      --json-output data/dify/afeng-retrieval-report.json \
      --md-output docs/evaluation/afeng-retrieval-report.md
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _retrieve(base_url: str, api_key: str, dataset_id: str, query: str, top_k: int = 5, search_method: str = "hybrid_search") -> dict[str, Any]:
    url = f"{base_url}/datasets/{dataset_id}/retrieve"
    payload = {
        "query": query,
        "retrieval_model": {
            "search_method": search_method,
            "reranking_enable": False,
            "top_k": top_k,
            "score_threshold_enabled": False,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return {"error": f"HTTP {exc.code}: {detail}"}
    except urllib.error.URLError as exc:
        return {"error": str(exc)}


def run_test(
    base_url: str,
    api_key: str,
    dataset_id: str,
    test_set: list[dict[str, Any]],
    top_k: int = 5,
    search_method: str = "hybrid_search",
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for item in test_set:
        query = item["question"]
        resp = _retrieve(base_url, api_key, dataset_id, query, top_k=top_k * 3, search_method=search_method)
        records = resp.get("records", resp.get("data", []))
        # Document-level deduplication: keep highest-scoring segment per document
        seen_docs: dict[str, dict[str, Any]] = {}
        for rec in records:
            segment = rec.get("segment", rec)
            doc = rec.get("document") or segment.get("document") or {}
            kid = doc.get("name", segment.get("document_id", ""))
            score = rec.get("score", 0)
            if kid not in seen_docs or score > seen_docs[kid]["score"]:
                seen_docs[kid] = {
                    "knowledge_id": kid,
                    "score": score,
                    "content_preview": str(segment.get("content", ""))[:200],
                }
        hits = sorted(seen_docs.values(), key=lambda h: h["score"], reverse=True)[:top_k]
        expected = item.get("expected_canonical", "")
        if isinstance(expected, list):
            found = any(h["knowledge_id"] in expected for h in hits)
        else:
            found = any(h["knowledge_id"] == expected for h in hits)
        results.append({
            "id": item["id"],
            "question": query,
            "expected_canonical": expected,
            "category": item.get("category", ""),
            "top_k_hits": len(hits),
            "expected_found_in_top_k": found,
            "hits": hits,
            "error": resp.get("error"),
        })
    correct = sum(1 for r in results if r["expected_found_in_top_k"])
    total = len(results)
    return {
        "schema_version": "1.0",
        "test_type": "afeng-retrieval-validation",
        "dataset_id": dataset_id,
        "top_k": top_k,
        "total_questions": total,
        "correct_in_top_k": correct,
        "accuracy": round(correct / total * 100, 1) if total else 0,
        "results": results,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def write_markdown_report(report: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# 阿峰检索验收报告",
        "",
        f"生成时间：{report['timestamp']}",
        f"Dataset ID：{report['dataset_id']}",
        f"Top-K：{report['top_k']}",
        "",
        "## 总览",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 总问题数 | {report['total_questions']} |",
        f"| Top-K 命中 | {report['correct_in_top_k']} |",
        f"| 准确率 | {report['accuracy']}% |",
        "",
        "## 逐题结果",
        "",
        "| ID | 类别 | 预期命中 | Top-K 命中 | 结果 |",
        "|---|---|---|---|---|",
    ]
    for r in report["results"]:
        status = "PASS" if r["expected_found_in_top_k"] else "FAIL"
        exp = r["expected_canonical"]
        if isinstance(exp, list):
            exp = ", ".join(exp[:2]) + "..."
        lines.append(f"| {r['id']} | {r['category']} | {exp[:40]} | {r['top_k_hits']} | {status} |")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-set", type=Path, required=True)
    parser.add_argument("--map-path", type=Path, default=Path("data/dify/document-map-v1.json"))
    parser.add_argument("--json-output", type=Path, default=Path("data/dify/afeng-retrieval-report.json"))
    parser.add_argument("--md-output", type=Path, default=Path("docs/evaluation/afeng-retrieval-report.md"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--search-method", default="semantic_search",
                        choices=["semantic_search", "keyword_search", "hybrid_search"])
    args = parser.parse_args()

    base_url = os.environ.get("DIFY_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("DIFY_API_KEY", "")
    dataset_id = os.environ.get("DIFY_DATASET_ID", "")
    if not all([base_url, api_key, dataset_id]):
        print("ERROR: 需要 DIFY_BASE_URL, DIFY_API_KEY, DIFY_DATASET_ID", flush=True)
        return 1

    test_set = json.loads(args.test_set.read_text(encoding="utf-8"))
    report = run_test(base_url, api_key, dataset_id, test_set, top_k=args.top_k, search_method=args.search_method)
    report["search_method"] = args.search_method

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_report(report, args.md_output)

    print(f"检索验收: {report['correct_in_top_k']}/{report['total_questions']} ({report['accuracy']}%)", flush=True)
    return 0 if report["accuracy"] >= 90 else 1


if __name__ == "__main__":
    raise SystemExit(main())
