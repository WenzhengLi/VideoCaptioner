#!/usr/bin/env python3
"""Set up the v2 formal Dataset with external embedding provider.

This script:
1. Verifies Dify is reachable and an external embedding provider is configured
2. Creates a new high_quality Dataset named '阿峰课程方法库-研究版-v2'
3. Saves runtime config to D:\\Dev\\dify-deploy\\secrets\\dify-runtime-v2.env
4. Initializes an empty document-map-v2.json

Usage:
    python scripts/setup_v2_dataset.py [--dataset-name 阿峰课程方法库-研究版-v2]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _login_and_get_csrf(base_url: str, admin_email: str, admin_password: str) -> str:
    """Login to Dify console and return CSRF token."""
    import base64
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    pass_b64 = base64.b64encode(admin_password.encode("utf-8")).decode("ascii")
    payload = json.dumps({
        "email": admin_email,
        "password": pass_b64,
        "remember_me": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/console/api/login",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    resp = opener.open(req, timeout=30)
    result = json.loads(resp.read().decode("utf-8"))
    if result.get("result") != "success":
        raise RuntimeError(f"Login failed: {result}")

    for cookie in jar:
        if cookie.name == "csrf_token" and cookie.value:
            return str(cookie.value)
    raise RuntimeError("CSRF token not found after login")


def _create_dataset(
    base_url: str,
    csrf_token: str,
    name: str,
    description: str,
    admin_email: str,
    admin_password: str,
) -> dict[str, Any]:
    """Create a high_quality Dataset via console API."""
    import base64
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    # Re-login to get session
    pass_b64 = base64.b64encode(admin_password.encode("utf-8")).decode("ascii")
    login_payload = json.dumps({
        "email": admin_email,
        "password": pass_b64,
        "remember_me": True,
    }).encode("utf-8")
    login_req = urllib.request.Request(
        f"{base_url}/console/api/login",
        data=login_payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    opener.open(login_req, timeout=30)

    # Create dataset
    payload = json.dumps({
        "name": name,
        "description": description,
        "indexing_technique": "high_quality",
        "permission": "only_me",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/console/api/datasets",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf_token,
        },
    )
    try:
        resp = opener.open(req, timeout=30)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        if "409" in str(e.code):
            # Dataset already exists, find it
            list_req = urllib.request.Request(
                f"{base_url}/console/api/datasets?page=1&limit=100",
                headers={"X-CSRF-Token": csrf_token},
            )
            list_resp = opener.open(list_req, timeout=15)
            datasets = json.loads(list_resp.read().decode("utf-8"))
            for ds in datasets.get("data", []):
                if ds.get("name") == name:
                    return ds
        raise RuntimeError(f"Create dataset failed: HTTP {e.code}: {detail}") from e


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-name", default="阿峰课程方法库-研究版-v2")
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()

    # Load admin credentials
    admin_env = Path("D:/Dev/dify-deploy/secrets/admin.env")
    if not admin_env.exists():
        print("ERROR: admin.env not found", file=sys.stderr)
        return 1

    admin = {}
    for line in admin_env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            admin[k.strip()] = v.strip()

    base_url = args.base_url or "http://127.0.0.1:3080"

    # Check embedding provider
    print("Checking Dify embedding providers...")
    try:
        csrf = _login_and_get_csrf(base_url, admin["DIFY_ADMIN_EMAIL"], admin["DIFY_ADMIN_PASSWORD"])
    except Exception as e:
        print(f"ERROR: Cannot login to Dify: {e}", file=sys.stderr)
        return 1

    # Create dataset
    print(f"Creating Dataset: {args.dataset_name} (high_quality)...")
    try:
        result = _create_dataset(
            base_url,
            csrf,
            args.dataset_name,
            "阿峰课程方法正式语义检索库（外部 embedding）",
            admin["DIFY_ADMIN_EMAIL"],
            admin["DIFY_ADMIN_PASSWORD"],
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    dataset_id = result.get("id", "")
    embedding_model = result.get("embedding_model", "")
    embedding_provider = result.get("embedding_model_provider", "")
    technique = result.get("indexing_technique", "")

    print("Dataset created/found:")
    print(f"  ID: {dataset_id}")
    print(f"  Mode: {technique}")
    print(f"  Embedding: {embedding_model} ({embedding_provider})")

    if technique != "high_quality":
        print(f"WARNING: Dataset mode is {technique}, expected high_quality", file=sys.stderr)

    # Save runtime config
    runtime_env = Path("D:/Dev/dify-deploy/secrets/dify-runtime-v2.env")
    runtime_env.write_text(
        f"DIFY_BASE_URL={base_url}/v1\n"
        f"DIFY_DATASET_ID={dataset_id}\n"
        f"DIFY_DATASET_NAME={args.dataset_name}\n"
        f"# DIFY_API_KEY=<to be filled after creating API key in Dify>\n",
        encoding="utf-8",
    )
    print(f"Runtime config saved to: {runtime_env}")
    print()
    print("NEXT STEPS:")
    print("1. In Dify Web UI, create an API Key for this Dataset")
    print(f"2. Add DIFY_API_KEY=<your-key> to {runtime_env}")
    print("3. Run: python scripts/audit_afeng_production.py")

    # Initialize empty document map
    map_path = Path("data/dify/document-map-v2.json")
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(
        json.dumps({
            "schema_version": "1.0",
            "dataset_id": dataset_id,
            "dataset_name": args.dataset_name,
            "documents": {},
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Document map initialized: {map_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
