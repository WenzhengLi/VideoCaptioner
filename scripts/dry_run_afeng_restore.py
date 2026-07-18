#!/usr/bin/env python3
"""Non-destructive restore dry-run for Afeng production baseline.

Verifies bundle/map/dataset binding and computes real create/update/skip plan
by comparing source document SHA-256 with document-map-v1.json content_sha256.

Usage:
    python scripts/dry_run_afeng_restore.py [--offline]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path


def _compute_sync_plan(source_dir: Path, map_path: Path) -> tuple[int, int, int]:
    """Compute real create/update/skip by comparing source SHA-256 with map."""
    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    map_docs = mapping.get("documents", {})

    create = 0
    update = 0
    skip = 0

    for md_file in sorted(source_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")

        # Extract canonical ID from frontmatter
        canonical_id = ""
        for line in text.splitlines()[:20]:
            if line.startswith("knowledge_id:"):
                canonical_id = line.split(":", 1)[1].strip().strip('"')
                break

        if not canonical_id:
            # Try filename
            canonical_id = md_file.stem

        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = map_docs.get(canonical_id)

        if not existing or not existing.get("document_id"):
            create += 1
        elif existing.get("content_sha256") == digest:
            skip += 1
        else:
            update += 1

    return create, update, skip


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Skip remote Dify checks")
    args = parser.parse_args()

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

    # 3. Compute real sync plan against v002.7
    source_dir = Path("data/dify/afeng-release-v002.7/documents")
    if not source_dir.exists():
        errors.append(f"Sync source missing: {source_dir}")
    elif not map_path.exists():
        errors.append("Cannot compute sync plan: map missing")
    else:
        create, update, skip = _compute_sync_plan(source_dir, map_path)
        print("\nSync plan (source: v002.7, map: v1):")
        print(f"  create={create}")
        print(f"  update={update}")
        print(f"  skip={skip}")
        if create > 0:
            errors.append(f"Sync plan: {create} would be created (expected 0)")
        if update > 0:
            print(f"  NOTE: {update} documents have different content hash")

    # 4. Remote verification (unless --offline)
    base_url = os.environ.get("DIFY_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("DIFY_API_KEY", "")
    dataset_id = os.environ.get("DIFY_DATASET_ID", "")

    if args.offline:
        print("\nRemote: SKIPPED (--offline)")
    elif not all([base_url, api_key, dataset_id]):
        errors.append("Remote: Dify env not configured and --offline not specified")
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

            if map_path.exists():
                mapping = json.loads(map_path.read_text(encoding="utf-8"))
                if mapping.get("dataset_id") != dataset_id:
                    errors.append("Map dataset_id mismatch")

            remote_count = ds.get("document_count", 0)
            if remote_count != 36:
                errors.append(f"Remote document count: {remote_count} (expected 36)")

        except Exception as exc:
            errors.append(f"Remote check failed: {exc}")

    # 5. Check for stale map entries
    if map_path.exists():
        mapping = json.loads(map_path.read_text(encoding="utf-8"))
        map_keys = set(mapping.get("documents", {}).keys())
        if bundle_path.exists():
            manifest = json.loads(bundle_path.read_text(encoding="utf-8"))
            bundle_ids = {f"AFENG-{d['course_id']}-{d['case_id']}" for d in manifest.get("documents", [])}
            stale = map_keys - bundle_ids
            if stale:
                errors.append(f"Stale map entries: {len(stale)}")

    # Summary
    print(f"\n{'='*40}")
    if args.offline:
        print("remote_verified=false")
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
