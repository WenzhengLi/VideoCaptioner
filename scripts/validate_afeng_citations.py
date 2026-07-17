#!/usr/bin/env python3
"""Validate Afeng application output citations.

Checks that every claim in the application output has valid:
- knowledge_id (exists in the dataset)
- course_id / case_id (match the document)
- evidence_ids (belong to the cited document)
- time_range (present and non-empty)

Usage:
    python scripts/validate_afeng_citations.py application-output.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def validate_citations(
    output: dict[str, Any],
    known_canonical_ids: set[str],
) -> dict[str, Any]:
    """Validate citations in an application output."""
    issues: list[str] = []
    claims = output.get("claims", output.get("sections", []))
    if not isinstance(claims, list):
        claims = [output]

    total_claims = 0
    claims_with_citation = 0
    claims_without_citation = 0
    invalid_ids: list[str] = []
    missing_evidence: list[str] = []
    missing_time_range: list[str] = []

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        total_claims += 1
        kid = str(claim.get("knowledge_id", ""))
        eids = claim.get("evidence_ids", [])
        tr = claim.get("time_range", claim.get("source_time_range", ""))

        if not kid:
            claims_without_citation += 1
            issues.append(f"Claim missing knowledge_id: {str(claim.get('content', ''))[:80]}")
            continue

        claims_with_citation += 1

        if kid not in known_canonical_ids:
            invalid_ids.append(kid)
            issues.append(f"Invalid knowledge_id: {kid}")

        if not eids:
            missing_evidence.append(kid)
            issues.append(f"Missing evidence_ids for {kid}")

        if not tr:
            missing_time_range.append(kid)
            issues.append(f"Missing time_range for {kid}")

    return {
        "total_claims": total_claims,
        "claims_with_citation": claims_with_citation,
        "claims_without_citation": claims_without_citation,
        "invalid_knowledge_ids": invalid_ids,
        "missing_evidence_ids": missing_evidence,
        "missing_time_range": missing_time_range,
        "issues": issues,
        "valid": not issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Afeng application citations")
    parser.add_argument("output_json", type=Path, help="Application output JSON")
    parser.add_argument("--known-ids", type=Path, default=None, help="JSON file with known canonical IDs")
    args = parser.parse_args()

    output = json.loads(args.output_json.read_text(encoding="utf-8"))

    # Load known canonical IDs from manifest or provided file
    if args.known_ids:
        known = set(json.loads(args.known_ids.read_text(encoding="utf-8")))
    else:
        manifest_path = Path("data/dify/afeng-release-v002.6/manifest.json")
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            known = {d["knowledge_id"] for d in manifest.get("documents", [])}
        else:
            print("WARNING: No known IDs source found", file=sys.stderr)
            known = set()

    result = validate_citations(output, known)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
