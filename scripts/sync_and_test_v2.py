#!/usr/bin/env python3
"""Sync v002.6 to v2 Dataset and run retrieval validation.

Requires:
- Dify running with external embedding provider configured
- v2 Dataset created (run setup_v2_dataset.py first)
- API Key in dify-runtime-v2.env

Usage:
    python scripts/sync_and_test_v2.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _load_env(env_path: Path) -> dict[str, str]:
    """Load environment variables from file."""
    result = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                result[k.strip()] = v.strip()
    return result


def _api_call(base_url: str, api_key: str, method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
    """Make Dify API call."""
    url = f"{base_url}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"API {method} {path} -> HTTP {e.code}: {detail}") from e


def _retrieve(base_url: str, api_key: str, dataset_id: str, query: str, top_k: int = 15) -> list[dict[str, Any]]:
    """Retrieve with hybrid search, return raw segments."""
    payload = {
        "query": query,
        "retrieval_model": {
            "search_method": "hybrid_search",
            "reranking_enable": False,
            "top_k": top_k,
            "score_threshold_enabled": False,
        },
    }
    result = _api_call(base_url, api_key, "POST", f"/datasets/{dataset_id}/retrieve", payload)
    return result.get("records", [])


def _dedup_by_document(records: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    """Document-level deduplication: keep highest-scoring segment per document."""
    seen: dict[str, dict[str, Any]] = {}
    for rec in records:
        seg = rec.get("segment", rec)
        doc = seg.get("document") or {}
        kid = doc.get("name", seg.get("document_id", ""))
        score = rec.get("score", 0)
        if kid not in seen or score > seen[kid]["score"]:
            seen[kid] = {
                "knowledge_id": kid,
                "score": score,
                "content_preview": str(seg.get("content", ""))[:200],
            }
    return sorted(seen.values(), key=lambda h: h["score"], reverse=True)[:top_k]


def main() -> int:
    # Load v2 config
    env_path = Path("D:/Dev/dify-deploy/secrets/dify-runtime-v2.env")
    env = _load_env(env_path)
    base_url = env.get("DIFY_BASE_URL", "").rstrip("/")
    api_key = env.get("DIFY_API_KEY", "")
    dataset_id = env.get("DIFY_DATASET_ID", "")

    if not all([base_url, api_key, dataset_id]):
        print(f"ERROR: Missing config in {env_path}", file=sys.stderr)
        print("Required: DIFY_BASE_URL, DIFY_API_KEY, DIFY_DATASET_ID", file=sys.stderr)
        return 1

    # Verify dataset
    print("Verifying v2 Dataset...")
    try:
        ds = _api_call(base_url, api_key, "GET", f"/datasets/{dataset_id}")
        print(f"  Dataset: {ds['name']}")
        print(f"  Mode: {ds['indexing_technique']}")
        print(f"  Embedding: {ds.get('embedding_model')} ({ds.get('embedding_model_provider')})")
        print(f"  Documents: {ds['document_count']}")
    except Exception as e:
        print(f"ERROR: Cannot access dataset: {e}", file=sys.stderr)
        return 1

    # First sync
    print("\nSyncing v002.6 documents to v2 Dataset...")
    map_path = Path("data/dify/document-map-v2.json")
    markdown_root = Path("data/dify/afeng-release-v002.6/documents")

    # Use CLI for sync
    import subprocess
    result = subprocess.run(
        [
            sys.executable, "-m", "course_video_analyzer.knowledge.cli", "dify-sync-markdown",
            "--markdown-root", str(markdown_root),
            "--map-path", str(map_path),
            "--dataset-id", dataset_id,
            "--indexing-technique", "high_quality",
            "--poll-indexing",
        ],
        capture_output=True, text=True, encoding="utf-8",
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"Sync failed: {result.stderr}", file=sys.stderr)
        return 1

    # Second sync (should skip all)
    print("\nSecond sync (idempotency check)...")
    result2 = subprocess.run(
        [
            sys.executable, "-m", "course_video_analyzer.knowledge.cli", "dify-sync-markdown",
            "--markdown-root", str(markdown_root),
            "--map-path", str(map_path),
            "--dataset-id", dataset_id,
        ],
        capture_output=True, text=True, encoding="utf-8",
    )
    print(result2.stdout)

    # Load test set
    test_path = Path("data/dify/afeng-retrieval-test-v002.json")
    if not test_path.exists():
        test_path = Path("data/dify/afeng-retrieval-test-v001.json")
    test_set = json.loads(test_path.read_text(encoding="utf-8"))
    if isinstance(test_set, dict):
        test_set = test_set.get("questions", test_set)

    # Run retrieval test
    print(f"\nRunning {len(test_set)} retrieval questions...")
    results_raw = []
    results_dedup = []

    for item in test_set:
        query = item["question"]
        expected = item.get("expected_canonical", "")
        category = item.get("category", "")

        records = _retrieve(base_url, api_key, dataset_id, query, top_k=15)

        # Raw segment Top-5
        raw_hits = []
        for rec in records[:5]:
            seg = rec.get("segment", rec)
            doc = seg.get("document") or {}
            raw_hits.append({
                "knowledge_id": doc.get("name", ""),
                "score": rec.get("score", 0),
            })

        if isinstance(expected, list):
            raw_found = any(h["knowledge_id"] in expected for h in raw_hits)
        else:
            raw_found = any(h["knowledge_id"] == expected for h in raw_hits)

        results_raw.append({
            "id": item["id"], "category": category,
            "expected": expected, "found": raw_found,
            "hits": raw_hits,
        })

        # Document-deduplicated Top-5
        dedup_hits = _dedup_by_document(records, 5)

        if isinstance(expected, list):
            dedup_found = any(h["knowledge_id"] in expected for h in dedup_hits)
        else:
            dedup_found = any(h["knowledge_id"] == expected for h in dedup_hits)

        results_dedup.append({
            "id": item["id"], "category": category,
            "expected": expected, "found": dedup_found,
            "hits": dedup_hits,
        })

    raw_correct = sum(1 for r in results_raw if r["found"])
    dedup_correct = sum(1 for r in results_dedup if r["found"])
    total = len(test_set)

    print(f"\n{'='*50}")
    print(f"Raw Segment Top-5:        {raw_correct}/{total} ({raw_correct/total*100:.0f}%)")
    print(f"Document-Dedup Top-5:     {dedup_correct}/{total} ({dedup_correct/total*100:.0f}%)")
    print(f"{'='*50}")

    # Save report
    report = {
        "schema_version": "1.0",
        "test_type": "afeng-retrieval-v2-validation",
        "dataset_id": dataset_id,
        "test_set": str(test_path),
        "search_method": "hybrid_search",
        "raw_segment_top5": {
            "correct": raw_correct,
            "total": total,
            "accuracy": round(raw_correct / total * 100, 1),
        },
        "document_dedup_top5": {
            "correct": dedup_correct,
            "total": total,
            "accuracy": round(dedup_correct / total * 100, 1),
        },
        "results_raw": results_raw,
        "results_dedup": results_dedup,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    report_path = Path("data/dify/afeng-retrieval-report-v2.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nReport saved: {report_path}")

    # Check pass/fail
    if dedup_correct / total >= 0.9:
        print("PASS: Document-dedup Top-5 >= 90%")
        return 0
    else:
        print(f"FAIL: Document-dedup Top-5 = {dedup_correct/total*100:.0f}% < 90%")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
