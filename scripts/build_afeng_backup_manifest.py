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


REQUIRED_ARTIFACTS = [
    Path("data/dify/afeng-release-v002.6/manifest.json"),
    Path("data/dify/document-map-v1.json"),
    Path("deploy/dify/workflows/afeng-chatflow.yml"),
    Path("data/dify/afeng-retrieval-test-v002.json"),
    Path("data/dify/afeng-retrieval-report.json"),
    Path("data/dify/afeng-app-acceptance.json"),
    Path("docs/evaluation/afeng-app-acceptance.md"),
    Path("docs/evaluation/afeng-retrieval-report.md"),
    Path("docs/operations/afeng-operations-manual.md"),
    Path("docs/cursor-handoff/DIFY-STATUS.md"),
    Path("docs/deployment/afeng-dify-operations.md"),
    Path("scripts/audit_afeng_production.py"),
    Path("scripts/deploy_afeng_dify_app.py"),
    Path("scripts/run_afeng_app_acceptance.py"),
    Path("scripts/run_afeng_retrieval_test.py"),
    Path("scripts/validate_afeng_citations.py"),
]


def build_manifest() -> tuple[dict[str, Any], list[str]]:
    """Build the backup manifest. Returns (manifest, missing_required)."""
    artifacts: list[dict[str, Any]] = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    found_paths: set[str] = set()

    def _collect(directory: Path, purpose: str) -> None:
        if directory.exists():
            for f in sorted(directory.glob("**/*")):
                if f.is_file():
                    info = _file_info(f, purpose)
                    if info:
                        artifacts.append(info)
                        found_paths.add(info["path"])

    def _add(path: Path, purpose: str) -> None:
        info = _file_info(path, purpose)
        if info:
            artifacts.append(info)
            found_paths.add(info["path"])

    # v002.6 immutable bundle
    _collect(Path("data/dify/afeng-release-v002.6"), "v002.6 immutable bundle")

    # v002.7 retrieval-optimized documents
    _collect(Path("data/dify/afeng-release-v002.7"), "v002.7 retrieval-optimized documents")

    # Formal document map
    _add(Path("data/dify/document-map-v1.json"), "formal document map")

    # Workflow DSL
    _add(Path("deploy/dify/workflows/afeng-chatflow.yml"), "Workflow DSL")

    # Test sets
    for f in [Path("data/dify/afeng-retrieval-test-v001.json"), Path("data/dify/afeng-retrieval-test-v002.json")]:
        _add(f, "retrieval test set")

    # Reports
    for f in [
        Path("data/dify/afeng-retrieval-report.json"),
        Path("data/dify/afeng-app-acceptance.json"),
        Path("data/dify/afeng-production-final-audit.json"),
    ]:
        _add(f, "validation report")

    # Documentation
    for f in [
        Path("docs/evaluation/afeng-app-acceptance.md"),
        Path("docs/evaluation/afeng-retrieval-report.md"),
        Path("docs/operations/afeng-operations-manual.md"),
        Path("docs/cursor-handoff/DIFY-STATUS.md"),
        Path("docs/deployment/afeng-dify-operations.md"),
    ]:
        _add(f, "documentation")

    # Scripts
    for f in [
        Path("scripts/audit_afeng_production.py"),
        Path("scripts/deploy_afeng_dify_app.py"),
        Path("scripts/prepare_afeng_app_index.py"),
        Path("scripts/run_afeng_app_acceptance.py"),
        Path("scripts/run_afeng_retrieval_test.py"),
        Path("scripts/validate_afeng_citations.py"),
        Path("scripts/build_afeng_backup_manifest.py"),
        Path("scripts/dry_run_afeng_restore.py"),
    ]:
        _add(f, "deployment/validation script")

    # Dify non-sensitive config
    _add(Path("D:/Dev/dify-deploy/bootstrap-status.json"), "Dify bootstrap status")

    # Check required artifacts
    missing_required: list[str] = []
    for req in REQUIRED_ARTIFACTS:
        normalized = str(req).replace("\\", "/")
        if normalized not in found_paths:
            missing_required.append(normalized)

    manifest = {
        "schema_version": "1.0",
        "manifest_type": "afeng-backup-manifest",
        "generated_at": now,
        "artifact_count": len(artifacts),
        "required_count": len(REQUIRED_ARTIFACTS),
        "missing_required": len(missing_required),
        "artifacts": artifacts,
    }
    return manifest, missing_required


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/dify/afeng-backup-manifest.json"))
    args = parser.parse_args()

    manifest, missing_required = build_manifest()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Backup manifest: {manifest['artifact_count']} artifacts -> {args.output}")
    print(f"Required: {manifest['required_count']}, Missing: {manifest['missing_required']}")

    if missing_required:
        print("FAIL: Missing required artifacts:")
        for m in missing_required:
            print(f"  - {m}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
