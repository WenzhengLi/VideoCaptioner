"""P06 atomic knowledge entries, QA, and Markdown export."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text

ALLOWED_ENTRY_TYPES = {"case", "principle", "risk", "counterexample", "expression"}


def build_p06_input(
    course_id: str,
    case_id: str,
    p04_path: Path,
    p05_path: Path,
    output_path: Path,
) -> Path:
    payload = {
        "schema_version": "1.0",
        "prompt_version": "knowledge-v002-p06-input",
        "source_ids": [course_id],
        "course_id": course_id,
        "case_id": case_id,
        "extraction": json.loads(Path(p04_path).read_text(encoding="utf-8")),
        "review": json.loads(Path(p05_path).read_text(encoding="utf-8")),
    }
    atomic_write_text(output_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return Path(output_path)


def validate_p06_output(
    course_id: str,
    case_id: str,
    input_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    source = json.loads(Path(input_path).read_text(encoding="utf-8"))
    output = json.loads(Path(output_path).read_text(encoding="utf-8"))
    extraction = source.get("extraction") or {}
    valid_segment_ids: set[str] = set()
    for span in extraction.get("evidence_spans", []):
        valid_segment_ids.update(span.get("segment_ids", []))
    for field, evidence_field in (
        ("participants", "evidence_segment_ids"),
        ("timeline", "evidence_segment_ids"),
        ("observations", "evidence_segment_ids"),
        ("instructor_claims", "evidence_segment_ids"),
        ("alternative_explanations", "basis_evidence_segment_ids"),
        ("outcomes", "evidence_segment_ids"),
        ("quoted_expressions", "evidence_segment_ids"),
        ("uncertainties", "evidence_segment_ids"),
    ):
        for item in extraction.get(field, []):
            valid_segment_ids.update(item.get(evidence_field, []))
    for review in (source.get("review") or {}).get("evidence_reviews", []):
        valid_segment_ids.update(review.get("supported_by_segment_ids", []))
    entries = output.get("entries") if isinstance(output.get("entries"), list) else []
    entry_ids: list[str] = []
    invalid_entries: list[int] = []
    invalid_evidence: list[str] = []
    required_lists = (
        "relationship_stage",
        "scenario",
        "observations",
        "instructor_claims",
        "alternative_explanations",
        "principles",
        "applicability",
        "contraindications",
        "risks",
        "safety_flags",
        "response_options",
    )
    blocked = (source.get("review") or {}).get("review_status") == "blocked"
    blocked_response_entries: list[int] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            invalid_entries.append(index)
            continue
        entry_id = str(entry.get("id", ""))
        entry_ids.append(entry_id)
        confidence = entry.get("confidence")
        evidence = entry.get("evidence_spans")
        if (
            not entry_id.startswith(f"KNOW-{course_id}-")
            or not str(entry.get("title", "")).strip()
            or entry.get("type") not in ALLOWED_ENTRY_TYPES
            or entry.get("source_ids") != [course_id]
            or entry.get("case_id") != case_id
            or not isinstance(evidence, list)
            or not evidence
            or any(not isinstance(entry.get(field), list) for field in required_lists)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            invalid_entries.append(index)
        if isinstance(evidence, list):
            invalid_evidence.extend(
                f"entries[{index}]:{segment_id}"
                for segment_id in evidence
                if segment_id not in valid_segment_ids
            )
        if blocked and entry.get("response_options"):
            blocked_response_entries.append(index)
    checks = {
        "schema_version": output.get("schema_version") == "1.0",
        "prompt_version": output.get("prompt_version") == "knowledge-v002-p06",
        "identity": output.get("source_ids") == [course_id]
        and output.get("course_id") == course_id
        and output.get("case_id") == case_id,
        "entries_present": bool(entries),
        "entry_contract": not invalid_entries,
        "entry_ids_unique": len(entry_ids) == len(set(entry_ids)),
        "evidence_valid": not invalid_evidence,
        "blocked_cases_have_no_responses": not blocked_response_entries,
    }
    return {
        "schema_version": "1.0",
        "course_id": course_id,
        "case_id": case_id,
        "stage": "P06",
        "status": "pass" if all(checks.values()) else "needs_review",
        "checks": checks,
        "metrics": {
            "entry_count": len(entries),
            "invalid_entry_count": len(invalid_entries),
            "invalid_evidence_count": len(invalid_evidence),
        },
        "samples": {
            "invalid_entry_indexes": invalid_entries[:20],
            "invalid_evidence": invalid_evidence[:20],
            "blocked_response_entry_indexes": blocked_response_entries[:20],
        },
    }


def write_p06_qa(
    course_id: str,
    case_id: str,
    input_path: Path,
    output_path: Path,
    report_path: Path,
) -> Path:
    report = validate_p06_output(course_id, case_id, input_path, output_path)
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    return Path(report_path)


def _safe_filename(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("_") or "entry"


def export_tidy_markdown(p06_path: Path, output_dir: Path) -> list[Path]:
    payload = json.loads(Path(p06_path).read_text(encoding="utf-8"))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for entry in payload.get("entries", []):
        path = output_dir / f"{_safe_filename(str(entry['id']))}.md"
        if path.exists():
            raise FileExistsError(f"Tidy Markdown 已存在，拒绝覆盖: {path}")
        frontmatter = {
            "id": entry["id"],
            "title": entry["title"],
            "type": entry["type"],
            "source_ids": entry["source_ids"],
            "case_id": entry["case_id"],
            "relationship_stage": entry["relationship_stage"],
            "scenario": entry["scenario"],
            "confidence": entry["confidence"],
        }
        lines = ["---"]
        for key, value in frontmatter.items():
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        lines.extend(["---", "", f"# {entry['title']}", ""])
        for field, title in (
            ("observations", "客观观察"),
            ("instructor_claims", "讲师观点"),
            ("alternative_explanations", "备选解释"),
            ("principles", "原则"),
            ("applicability", "适用条件"),
            ("contraindications", "不适用条件"),
            ("risks", "风险与边界"),
            ("response_options", "经审查的表达选项"),
        ):
            lines.extend([f"## {title}", ""])
            values = entry.get(field, [])
            lines.extend([f"- {value}" for value in values] or ["- 无"])
            lines.append("")
        lines.extend(["## 证据 Segment IDs", ""])
        lines.extend([f"- {value}" for value in entry.get("evidence_spans", [])])
        atomic_write_text(path, "\n".join(lines).rstrip() + "\n")
        written.append(path)
    return written
