#!/usr/bin/env python3
"""Build the app-specific Afeng document package and citation index.

The release bundles are treated as immutable.  Retrieval-optimized v002.7
documents are copied to a separate runtime directory, while canonical citation
records are extracted from v002.6 into a machine-readable Workflow lookup.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)
EVIDENCE_RE = re.compile(
    r"^- `\[(?P<id>SEG-C\d{3}-\d{6})\]` "
    r"\[(?P<time>[^\]]+)\] \[(?P<kind>[^\]]+)\]\s*(?P<text>.*)$",
    re.MULTILINE,
)


def _frontmatter_value(frontmatter: str, key: str) -> str:
    match = re.search(rf'^\s*{re.escape(key)}:\s*["\']?(.*?)["\']?\s*$', frontmatter, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _format_ms(value: str) -> str:
    milliseconds = int(value)
    seconds = milliseconds // 1000
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _select_evidence(text: str, limit: int) -> list[dict[str, str]]:
    evidence = [match.groupdict() for match in EVIDENCE_RE.finditer(text)]
    if not evidence:
        raise ValueError("document has no parseable source evidence")

    def score(item: dict[str, str]) -> tuple[int, int]:
        kind = item["kind"].lower()
        priority = 0 if "instructor_explanation/speech" in kind else 1 if "speech" in kind else 2
        return priority, evidence.index(item)

    return sorted(evidence, key=score)[:limit]


def transform_document(text: str, evidence_text: str, *, evidence_limit: int = 8) -> str:
    if not FRONTMATTER_RE.match(text):
        raise ValueError("document has no YAML frontmatter")
    _select_evidence(evidence_text, evidence_limit)  # fail fast if the source evidence is unusable
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/dify/afeng-release-v002.7/documents"))
    parser.add_argument(
        "--evidence-source",
        type=Path,
        default=Path("data/dify/afeng-release-v002.6/documents"),
    )
    parser.add_argument("--output", type=Path, default=Path("data/dify/afeng-app-index-v1/documents"))
    parser.add_argument("--evidence-limit", type=int, default=8)
    args = parser.parse_args()
    if args.evidence_limit < 1:
        parser.error("--evidence-limit must be positive")

    files = sorted(args.source.glob("*.md"))
    if not files:
        raise SystemExit(f"no Markdown documents found in {args.source}")
    args.output.mkdir(parents=True, exist_ok=True)

    generated: list[dict[str, str | int]] = []
    citation_index: dict[str, dict[str, object]] = {}
    for source in files:
        evidence_source = args.evidence_source / source.name
        if not evidence_source.exists():
            raise SystemExit(f"missing evidence source: {evidence_source}")
        source_text = source.read_text(encoding="utf-8")
        evidence_text = evidence_source.read_text(encoding="utf-8")
        transformed = transform_document(source_text, evidence_text, evidence_limit=args.evidence_limit)
        target = args.output / source.name
        target.write_text(transformed, encoding="utf-8")
        generated.append({"knowledge_id": source.stem, "bytes": len(transformed.encode("utf-8"))})
        frontmatter_match = FRONTMATTER_RE.match(source_text)
        assert frontmatter_match is not None
        frontmatter = frontmatter_match.group("body")
        selected = _select_evidence(evidence_text, args.evidence_limit)
        citation_index[source.stem] = {
            "knowledge_id": source.stem,
            "course_id": _frontmatter_value(frontmatter, "course_id"),
            "case_id": _frontmatter_value(frontmatter, "case_id"),
            "publication_class": _frontmatter_value(frontmatter, "publication_class"),
            "generalization_level": _frontmatter_value(frontmatter, "generalization_level"),
            "time_range": (
                f"{_format_ms(_frontmatter_value(frontmatter, 'source_start_ms'))}–"
                f"{_format_ms(_frontmatter_value(frontmatter, 'source_end_ms'))}"
            ),
            "evidence_ids": [item["id"] for item in selected],
        }

    report = {
        "schema_version": "1.0",
        "source": str(args.source).replace("\\", "/"),
        "evidence_source": str(args.evidence_source).replace("\\", "/"),
        "output": str(args.output).replace("\\", "/"),
        "document_count": len(generated),
        "evidence_limit_per_capsule": args.evidence_limit,
        "documents": generated,
    }
    report_path = args.output.parent / "build-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    citation_path = args.output.parent / "citation-index.json"
    citation_path.write_text(
        json.dumps(citation_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"generated": len(generated), "report": str(report_path), "citation_index": str(citation_path)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
