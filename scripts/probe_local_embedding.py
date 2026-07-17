#!/usr/bin/env python3
"""Probe local embedding availability for Dify high_quality indexing.

Checks:
1. Ollama health endpoint
2. bge-m3 model availability
3. Real embedding call with sample text
4. Embedding dimension consistency

Usage:
    python scripts/probe_local_embedding.py [--ollama-url http://127.0.0.1:11434]
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any


def _request(url: str, method: str = "GET", payload: dict | None = None, timeout: float = 30.0) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def probe_ollama(base_url: str) -> dict[str, Any]:
    result: dict[str, Any] = {"base_url": base_url, "checks": {}}

    # 1. Health check
    try:
        tags = _request(f"{base_url}/api/tags")
        models = [m["name"] for m in tags.get("models", [])]
        result["checks"]["ollama_health"] = {"status": "ok", "models": models}
    except Exception as exc:
        result["checks"]["ollama_health"] = {"status": "failed", "error": str(exc)}
        result["overall"] = "failed"
        return result

    # 2. Check bge-m3 availability
    bge_models = [m for m in models if "bge" in m.lower() or "m3" in m.lower()]
    if bge_models:
        result["checks"]["bge_m3_available"] = {"status": "ok", "models": bge_models}
    else:
        result["checks"]["bge_m3_available"] = {
            "status": "missing",
            "available_models": models,
            "hint": "Run: ollama pull bge-m3",
        }
        result["overall"] = "incomplete"
        return result

    # 3. Real embedding call
    test_text = "阿峰课程方法：如何在约会中建立吸引力"
    try:
        embed_resp = _request(
            f"{base_url}/api/embed",
            method="POST",
            payload={"model": bge_models[0], "input": test_text},
            timeout=60.0,
        )
        embeddings = embed_resp.get("embeddings", [])
        if embeddings and len(embeddings[0]) > 0:
            dim = len(embeddings[0])
            result["checks"]["embedding_call"] = {
                "status": "ok",
                "model": bge_models[0],
                "dimension": dim,
                "sample_text": test_text,
                "vector_norm": round(sum(x * x for x in embeddings[0]) ** 0.5, 4),
            }
        else:
            result["checks"]["embedding_call"] = {"status": "failed", "error": "empty embeddings"}
            result["overall"] = "failed"
            return result
    except Exception as exc:
        result["checks"]["embedding_call"] = {"status": "failed", "error": str(exc)}
        result["overall"] = "failed"
        return result

    # 4. Dimension consistency check
    test_text_2 = "课程证据引用：SEG-C003-000123"
    try:
        embed_resp_2 = _request(
            f"{base_url}/api/embed",
            method="POST",
            payload={"model": bge_models[0], "input": test_text_2},
            timeout=60.0,
        )
        dim_2 = len(embed_resp_2.get("embeddings", [[]])[0])
        result["checks"]["dimension_consistency"] = {
            "status": "ok" if dim == dim_2 else "mismatch",
            "first_dim": dim,
            "second_dim": dim_2,
        }
    except Exception as exc:
        result["checks"]["dimension_consistency"] = {"status": "failed", "error": str(exc)}

    all_ok = all(c.get("status") == "ok" for c in result["checks"].values())
    result["overall"] = "ok" if all_ok else "partial"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe local embedding availability")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--json-output", type=str, default=None)
    args = parser.parse_args()

    result = probe_ollama(args.ollama_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.json_output:
        from pathlib import Path
        Path(args.json_output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    return 0 if result["overall"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
