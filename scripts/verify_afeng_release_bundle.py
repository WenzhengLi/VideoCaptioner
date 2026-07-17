#!/usr/bin/env python3
"""Verify an Afeng release bundle uses stable canonical identity and full lineage.

The bundle builder canonicalizes knowledge ids and records model lineage, but a
separate verifier guards against regressions: every shipped document must carry a
canonical ``AFENG-{course_id}-{case_id}`` id, ids must be unique, model / run
token / input hash / source summary must be present, and the on-disk markdown's
frontmatter knowledge id and content sha256 must match the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

CANONICAL_RE = re.compile(r"^AFENG-(C\d{3})-(CASE-C\d{3}-\d{3})$")


def _read_frontmatter_knowledge_id(text: str) -> str:
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        if key.strip() == "knowledge_id":
            return value.strip().strip('"\'')
    return ""


def verify_bundle(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest.get("documents") or []
    seen: set[str] = set()
    problems: list[str] = []
    lineage_missing = 0
    content_mismatch = 0
    frontmatter_mismatch = 0
    for doc in documents:
        knowledge_id = str(doc.get("knowledge_id") or "")
        course_id = str(doc.get("course_id") or "")
        case_id = str(doc.get("case_id") or "")
        match = CANONICAL_RE.match(knowledge_id)
        if not match:
            problems.append(f"{knowledge_id}: knowledge_id is not canonical")
        elif match.group(1) != course_id or match.group(2) != case_id:
            problems.append(f"{knowledge_id}: canonical id does not match course/case")
        if knowledge_id in seen:
            problems.append(f"{knowledge_id}: duplicate canonical id")
        seen.add(knowledge_id)
        for field in ("model", "run_token", "input_hash", "source_summary", "content_sha256"):
            if not doc.get(field):
                lineage_missing += 1
                problems.append(f"{knowledge_id}: missing lineage field {field}")
        document_path = Path(str(doc.get("document_path") or ""))
        if not document_path.is_file():
            problems.append(f"{knowledge_id}: document file missing")
            continue
        text = document_path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != doc.get("content_sha256"):
            content_mismatch += 1
            problems.append(f"{knowledge_id}: content sha256 mismatch")
        frontmatter_id = _read_frontmatter_knowledge_id(text)
        if frontmatter_id != knowledge_id:
            frontmatter_mismatch += 1
            problems.append(
                f"{knowledge_id}: frontmatter knowledge_id is {frontmatter_id!r}"
            )
    return {
        "manifest_path": str(manifest_path),
        "document_count": len(documents),
        "excluded_count": int(manifest.get("excluded_count") or 0),
        "canonical_unique_count": len(seen),
        "lineage_missing": lineage_missing,
        "content_mismatch": content_mismatch,
        "frontmatter_mismatch": frontmatter_mismatch,
        "problems": problems,
        "ok": not problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args()
    report = verify_bundle(args.manifest)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        f"documents={report['document_count']} "
        f"canonical_unique={report['canonical_unique_count']} "
        f"lineage_missing={report['lineage_missing']} "
        f"content_mismatch={report['content_mismatch']} "
        f"frontmatter_mismatch={report['frontmatter_mismatch']} "
        f"ok={report['ok']}"
    )
    for problem in report["problems"][:20]:
        print(f"  - {problem}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
