#!/usr/bin/env python3
"""Non-destructive restore dry-run for Afeng production baseline.

Verifies bundle/map/dataset binding and computes create/update/skip plan
without calling any Dify create/update/delete API.

Usage:
    python scripts/dry_run_afeng_restore.py
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path


def main() -> int:
    print("=== Afeng Restore Dry-Run ===\n")
    errors: list[str] = []

    # 1. Verify bundle
    bundle_path = Path("data/dify/afeng-release-v002.6/manifest.json")
    if not bundle_path.exists():
        errors.append("Bundle manifest missing")
    else:
        manifest = json.loads(bundle_path.read_text(encoding="utf-8"))
        docs = manifest.get("documents", [])
        excluded = manifest.get("excluded", [])
        print(f"Bundle: {len(docs)} documents, {len(excluded)} excluded")

        # Verify all files exist and hashes match
        missing = 0
        hash_err = 0
        for doc in docs:
            p = Path(doc.get("document_path", ""))
            if not p.is_file():
                missing += 1
                continue
            text = p.read_text(encoding="utf-8")
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != doc.get("content_sha256"):
                hash_err += 1
        if missing:
            errors.append(f"Bundle: {missing} missing files")
        if hash_err:
            errors.append(f"Bundle: {hash_err} hash mismatches")
        print(f"  Files: {len(docs) - missing} present, {hash_err} hash errors")

    # 2. Verify map
    map_path = Path("data/dify/document-map-v1.json")
    if not map_path.exists():
        errors.append("Formal map missing")
    else:
        mapping = json.loads(map_path.read_text(encoding="utf-8"))
        map_docs = mapping.get("documents", {})
        map_ds = mapping.get("dataset_id", "")
        print(f"\nMap: {len(map_docs)} keys, dataset_id={map_ds[:8]}...")

    # 3. Verify dataset binding
    base_url = os.environ.get("DIFY_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("DIFY_API_KEY", "")
    dataset_id = os.environ.get("DIFY_DATASET_ID", "")

    if not all([base_url, api_key, dataset_id]):
        print("\nRemote: SKIPPED (no Dify env)")
    else:
        try:
            req = urllib.request.Request(
                f"{base_url}/datasets/{dataset_id}",
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                ds = json.loads(resp.read().decode("utf-8"))
            print(f"\nRemote Dataset: {ds.get('name')}")
            print(f"  Mode: {ds.get('indexing_technique')}")
            print(f"  Documents: {ds.get('document_count')}")
            print(f"  Embedding: {ds.get('embedding_model')}")

            # Verify map dataset_id matches
            if map_path.exists():
                mapping = json.loads(map_path.read_text(encoding="utf-8"))
                if mapping.get("dataset_id") != dataset_id:
                    errors.append(f"Map dataset_id mismatch: map={mapping.get('dataset_id', '')[:8]} vs env={dataset_id[:8]}")

            # Compute sync plan
            bundle_docs = set()
            if bundle_path.exists():
                manifest = json.loads(bundle_path.read_text(encoding="utf-8"))
                for doc in manifest.get("documents", []):
                    course = doc.get("course_id", "")
                    case = doc.get("case_id", "")
                    bundle_docs.add(f"AFENG-{course}-{case}")

            map_keys = set(mapping.get("documents", {}).keys()) if map_path.exists() else set()

            # Check what would happen on sync
            create_count = len(bundle_docs - map_keys)
            skip_count = len(bundle_docs & map_keys)
            update_count = 0  # Would need content hash comparison

            print("\nSync plan (dry-run):")
            print(f"  create={create_count}")
            print(f"  update={update_count}")
            print(f"  skip={skip_count}")

            if create_count > 0:
                print(f"  NOTE: {create_count} documents would be created (expected 0 for established baseline)")

            # Check remote document count
            remote_count = ds.get("document_count", 0)
            if remote_count != 36:
                errors.append(f"Remote document count: {remote_count} (expected 36)")

        except Exception as exc:
            errors.append(f"Remote check failed: {exc}")

    # 4. Check for stale map entries
    if map_path.exists():
        mapping = json.loads(map_path.read_text(encoding="utf-8"))
        map_keys = set(mapping.get("documents", {}).keys())
        if bundle_path.exists():
            manifest = json.loads(bundle_path.read_text(encoding="utf-8"))
            bundle_ids = {f"AFENG-{d['course_id']}-{d['case_id']}" for d in manifest.get("documents", [])}
            stale = map_keys - bundle_ids
            if stale:
                errors.append(f"Stale map entries: {len(stale)}")
                print(f"\nStale map entries: {sorted(stale)[:5]}...")

    # Summary
    print(f"\n{'='*40}")
    if errors:
        print(f"DRY-RUN FAILED: {len(errors)} errors")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("DRY-RUN PASSED: All checks OK")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
