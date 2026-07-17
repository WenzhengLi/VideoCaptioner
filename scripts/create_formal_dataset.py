#!/usr/bin/env python3
"""Create the formal high_quality Dataset for Afeng knowledge base.

Requires:
- Dify running at DIFY_BASE_URL
- Admin API key in DIFY_API_KEY
- Embedding provider already configured in Dify console

Usage:
    python scripts/create_formal_dataset.py [--name 阿峰课程方法库-研究版-v1]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


def _request(base_url: str, api_key: str, method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
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
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="阿峰课程方法库-研究版-v1")
    parser.add_argument("--description", default="阿峰课程方法正式语义检索库")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    base_url = args.base_url or os.environ.get("DIFY_BASE_URL", "").rstrip("/")
    api_key = args.api_key or os.environ.get("DIFY_API_KEY", "")
    if not base_url or not api_key:
        print("ERROR: 需要 DIFY_BASE_URL 和 DIFY_API_KEY", file=sys.stderr)
        return 1

    # Check if Dataset already exists
    datasets = _request(base_url, api_key, "GET", "/datasets")
    for ds in datasets.get("data", []):
        if ds.get("name") == args.name:
            print(f"Dataset 已存在: {ds['name']} (id={ds['id']}, mode={ds.get('indexing_technique')})")
            print(f"请将 DIFY_DATASET_ID={ds['id']} 写入正式库的环境变量")
            return 0

    # Create new Dataset with high_quality
    result = _request(base_url, api_key, "POST", "/datasets", payload={
        "name": args.name,
        "description": args.description,
        "indexing_technique": "high_quality",
        "permission": "only_me",
    })
    dataset_id = result.get("id")
    print("正式 Dataset 已创建:")
    print(f"  名称: {args.name}")
    print(f"  ID: {dataset_id}")
    print(f"  模式: {result.get('indexing_technique')}")
    print(f"  embedding: {result.get('embedding_model', 'pending')}")
    print()
    print(f"请将 DIFY_DATASET_ID={dataset_id} 写入正式库的环境变量")
    print("请使用独立 document map，不要复用旧 economy 工作库的 map")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
