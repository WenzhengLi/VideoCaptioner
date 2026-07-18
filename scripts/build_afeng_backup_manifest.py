#!/usr/bin/env python3
"""Build a backup manifest for the Afeng production baseline.

Records path, size, SHA-256, purpose, and generation time for all critical artifacts.
Read-only; does not modify any source files.

Usage:
    python scripts/build_afeng_backup_manifest.py [--output data/dify/afeng-backup-manifest.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


def _file_info(path: Path, purpose: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_bytes()
    return {
        "path": str(path).replace("\\", "/"),
        "size_bytes": len(text),
        "sha256": hashlib.sha256(text).hexdigest(),
        "purpose": purpose,
    }


def build_manifest() -> dict[str, Any]:
    """Build the backup manifest."""
    artifacts: list[dict[str, Any]] = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # v002.6 immutable bundle
    bundle_dir = Path("data/dify/afeng-release-v002.6")
    for f in sorted(bundle_dir.glob("**/*")):
        if f.is_file():
            info = _file_info(f, "v002.6 immutable bundle")
            if info:
                artifacts.append(info)

    # v002.7 retrieval-optimized documents
    v0027_dir = Path("data/dify/afeng-release-v002.7")
    if v0027_dir.exists():
        for f in sorted(v0027_dir.glob("**/*")):
            if f.is_file():
                info = _file_info(f, "v002.7 retrieval-optimized documents")
                if info:
                    artifacts.append(info)

    # Formal document map
    for map_file in [
        Path("data/dify/document-map-v1.json"),
    ]:
        info = _file_info(map_file, "formal document map")
        if info:
            artifacts.append(info)

    # Workflow DSL
    wf = _file_info(Path("deploy/dify/workflows/afeng-chatflow.yml"), "Workflow DSL")
    if wf:
        artifacts.append(wf)

    # Test sets
    for test_file in [
        Path("data/dify/afeng-retrieval-test-v001.json"),
        Path("data/dify/afeng-retrieval-test-v002.json"),
    ]:
        info = _file_info(test_file, "retrieval test set")
        if info:
            artifacts.append(info)

    # Reports
    for report_file in [
        Path("data/dify/afeng-retrieval-report.json"),
        Path("data/dify/afeng-app-acceptance-report.json"),
        Path("data/dify/afeng-production-final-audit.json"),
    ]:
        info = _file_info(report_file, "validation report")
        if info:
            artifacts.append(info)

    # Scripts
    for script_file in [
        Path("scripts/audit_afeng_production.py"),
        Path("scripts/deploy_afeng_dify_app.py"),
        Path("scripts/prepare_afeng_app_index.py"),
        Path("scripts/run_afeng_app_acceptance.py"),
        Path("scripts/run_afeng_retrieval_test.py"),
        Path("scripts/validate_afeng_citations.py"),
        Path("scripts/build_afeng_backup_manifest.py"),
        Path("scripts/dry_run_afeng_restore.py"),
    ]:
        info = _file_info(script_file, "deployment/validation script")
        if info:
            artifacts.append(info)

    # Dify non-sensitive config
    bootstrap = _file_info(Path("D:/Dev/dify-deploy/bootstrap-status.json"), "Dify bootstrap status")
    if bootstrap:
        artifacts.append(bootstrap)

    return {
        "schema_version": "1.0",
        "manifest_type": "afeng-backup-manifest",
        "generated_at": now,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/dify/afeng-backup-manifest.json"))
    args = parser.parse_args()

    manifest = build_manifest()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Backup manifest: {manifest['artifact_count']} artifacts -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
