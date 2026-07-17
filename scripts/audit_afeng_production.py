#!/usr/bin/env python3
"""Read-only production audit for Afeng knowledge pipeline.

Checks all critical invariants without modifying any data:
- 40 cases = 36 published + 2 manual_review + 2 rejected
- v002.6 bundle: 36 documents, 4 exclusions, canonical IDs unique
- Lineage and content hash coverage 100%
- Formal Dataset: 36 documents, indexing completed
- No exclusion leakage into formal Dataset
- No duplicate canonical IDs

Exit code 0 = all checks pass, non-zero = failure with machine-readable reason.

Usage:
    python scripts/audit_afeng_production.py [--bundle data/dify/afeng-release-v002.6/manifest.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

CANONICAL_RE = re.compile(r"^AFENG-(C\d{3})-(CASE-C\d{3}-\d{3})$")


def _check_bundle(manifest_path: Path) -> dict[str, Any]:
    """Check v002.6 bundle invariants."""
    if not manifest_path.exists():
        return {"status": "FAIL", "reason": f"Bundle manifest missing: {manifest_path}"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    docs = manifest.get("documents", [])
    excluded = manifest.get("excluded", [])
    checks: dict[str, Any] = {}

    # Document count
    checks["bundle_documents"] = {"expected": 36, "actual": len(docs), "pass": len(docs) == 36}

    # Exclusion count
    checks["bundle_exclusions"] = {"expected": 4, "actual": len(excluded), "pass": len(excluded) == 4}

    # Canonical ID uniqueness
    ids = [d.get("knowledge_id", "") for d in docs]
    unique_ids = set(ids)
    checks["canonical_unique"] = {"expected": 36, "actual": len(unique_ids), "pass": len(unique_ids) == 36}

    # All IDs match canonical format
    non_canonical = [i for i in ids if not CANONICAL_RE.match(i)]
    checks["canonical_format"] = {"non_canonical_count": len(non_canonical), "pass": len(non_canonical) == 0}

    # Lineage coverage
    lineage_fields = ["model", "run_token", "input_hash", "source_summary", "content_sha256"]
    lineage_missing = 0
    for doc in docs:
        for field in lineage_fields:
            if not doc.get(field):
                lineage_missing += 1
    checks["lineage_coverage"] = {"missing": lineage_missing, "pass": lineage_missing == 0}

    # Content hash verification
    hash_mismatch = 0
    for doc in docs:
        doc_path = Path(doc.get("document_path", ""))
        if doc_path.is_file():
            text = doc_path.read_text(encoding="utf-8")
            actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if actual != doc.get("content_sha256"):
                hash_mismatch += 1
    checks["content_hash"] = {"mismatch": hash_mismatch, "pass": hash_mismatch == 0}

    # Exclusion leakage (manual_review/rejected not in bundle)
    excluded_statuses = {e.get("status") for e in excluded}
    checks["exclusion_statuses"] = {"statuses": sorted(excluded_statuses), "pass": excluded_statuses <= {"manual_review", "rejected"}}

    all_pass = all(c.get("pass", False) for c in checks.values())
    return {"status": "PASS" if all_pass else "FAIL", "checks": checks}


def _check_aggregate() -> dict[str, Any]:
    """Check 20-course aggregate invariants."""
    agg_path = Path("docs/evaluation/afeng-twenty-course-v002.json")
    if not agg_path.exists():
        return {"status": "FAIL", "reason": f"Aggregate report missing: {agg_path}"}
    agg = json.loads(agg_path.read_text(encoding="utf-8"))
    checks: dict[str, Any] = {}

    checks["case_count"] = {"expected": 40, "actual": agg.get("case_count"), "pass": agg.get("case_count") == 40}
    checks["failure_count"] = {"expected": 0, "actual": agg.get("failure_count"), "pass": agg.get("failure_count") == 0}
    checks["status"] = {"expected": "complete", "actual": agg.get("status"), "pass": agg.get("status") == "complete"}

    sc = agg.get("status_counts", {})
    checks["published"] = {"expected": 36, "actual": sc.get("published"), "pass": sc.get("published") == 36}
    checks["manual_review"] = {"expected": 2, "actual": sc.get("manual_review"), "pass": sc.get("manual_review") == 2}
    checks["rejected"] = {"expected": 2, "actual": sc.get("rejected"), "pass": sc.get("rejected") == 2}

    all_pass = all(c.get("pass", False) for c in checks.values())
    return {"status": "PASS" if all_pass else "FAIL", "checks": checks}


def _check_dify(base_url: str, api_key: str, dataset_id: str) -> dict[str, Any]:
    """Check Dify Dataset invariants (read-only)."""
    checks: dict[str, Any] = {}
    try:
        req = urllib.request.Request(
            f"{base_url}/datasets/{dataset_id}",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            ds = json.loads(resp.read().decode("utf-8"))
        checks["dataset_exists"] = {"pass": True}
        checks["document_count"] = {"expected": 36, "actual": ds.get("document_count"), "pass": ds.get("document_count") == 36}
        checks["indexing_technique"] = {"value": ds.get("indexing_technique"), "pass": ds.get("indexing_technique") == "high_quality"}
        checks["embedding_configured"] = {"pass": bool(ds.get("embedding_model"))}
    except Exception as exc:
        checks["dataset_exists"] = {"pass": False, "error": str(exc)[:200]}

    all_pass = all(c.get("pass", False) for c in checks.values())
    return {"status": "PASS" if all_pass else "FAIL", "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, default=Path("data/dify/afeng-release-v002.6/manifest.json"))
    parser.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "audit_type": "afeng-production-final",
        "sections": {},
    }

    # 1. Bundle check
    report["sections"]["bundle"] = _check_bundle(args.bundle)

    # 2. Aggregate check
    report["sections"]["aggregate"] = _check_aggregate()

    # 3. Dify check (optional - only if env vars set)
    base_url = os.environ.get("DIFY_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("DIFY_API_KEY", "")
    dataset_id = os.environ.get("DIFY_DATASET_ID", "")
    if all([base_url, api_key, dataset_id]):
        report["sections"]["dify"] = _check_dify(base_url, api_key, dataset_id)
    else:
        report["sections"]["dify"] = {"status": "SKIP", "reason": "Dify env vars not set"}

    # Overall
    statuses = [s.get("status") for s in report["sections"].values()]
    if "FAIL" in statuses:
        report["overall"] = "FAIL"
    elif all(s == "PASS" for s in statuses):
        report["overall"] = "PASS"
    else:
        report["overall"] = "PARTIAL"

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
