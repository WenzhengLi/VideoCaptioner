"""Evidence-layer wave helpers (through P04 only; never P05/P06)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text

ALLOWED_THROUGH_STAGES = ("P01", "P02", "P03", "P04")
FORBIDDEN_STAGES = ("P05", "P06")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _qa_status(path: Path) -> str:
    if not path.exists():
        return "missing"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        return "invalid"
    return str(payload.get("status", "unknown"))


def enabled_stages(through_stage: str) -> list[str]:
    through_stage = through_stage.upper()
    if through_stage not in ALLOWED_THROUGH_STAGES:
        raise ValueError(f"through_stage must be one of {ALLOWED_THROUGH_STAGES}")
    return list(ALLOWED_THROUGH_STAGES[: ALLOWED_THROUGH_STAGES.index(through_stage) + 1])


def assert_evidence_only(through_stage: str) -> None:
    """Guardrail: evidence waves must stop at or before P04."""
    stages = enabled_stages(through_stage)
    for forbidden in FORBIDDEN_STAGES:
        if forbidden in stages:
            raise ValueError(f"evidence wave must not include {forbidden}")


def collect_course_evidence_status(
    data_root: Path,
    course_id: str,
    output_version: str,
    *,
    through_stage: str = "P04",
) -> dict[str, Any]:
    assert_evidence_only(through_stage)
    course_dir = Path(data_root) / "courses" / course_id
    qa_dir = course_dir / "qa"
    stages = enabled_stages(through_stage)
    raw_reports = sorted(qa_dir.glob("RUN-*.json")) if qa_dir.exists() else []
    stage_qa: dict[str, str] = {
        "raw": _qa_status(raw_reports[0]) if raw_reports else "missing"
    }
    for stage in stages:
        if stage == "P04":
            continue
        stage_qa[stage] = _qa_status(qa_dir / f"{stage}-{output_version}-qa.json")

    case_ids: list[str] = []
    p03_path = course_dir / "03_cases" / f"P03-{output_version}.json"
    if p03_path.exists():
        p03 = json.loads(p03_path.read_text(encoding="utf-8-sig"))
        for case in p03.get("cases") or []:
            if isinstance(case, dict) and case.get("case_id"):
                case_ids.append(str(case["case_id"]))

    case_qa: dict[str, str] = {}
    failed_cases: list[str] = []
    if "P04" in stages:
        for case_id in case_ids:
            status = _qa_status(qa_dir / f"P04-{case_id}-{output_version}-qa.json")
            case_qa[case_id] = status
            if status != "pass":
                failed_cases.append(case_id)

    failed_stages = [name for name, status in stage_qa.items() if status != "pass"]
    ok = not failed_stages and not failed_cases
    return {
        "course_id": course_id,
        "output_version": output_version,
        "through_stage": through_stage,
        "stage_qa": stage_qa,
        "case_ids": case_ids,
        "case_qa": case_qa,
        "failed_stages": failed_stages,
        "failed_cases": failed_cases,
        "ok": ok,
    }


def finalize_evidence_wave(
    data_root: Path,
    batch_id: str,
    wave_id: str,
    *,
    start_ordinal: int,
    end_ordinal: int,
    output_version: str,
    through_stage: str = "P04",
) -> Path:
    """Write evidence-pipeline-<wave>-complete.json after validating P01–P04 QA."""
    assert_evidence_only(through_stage)
    data_root = Path(data_root).resolve()
    courses = [f"C{i:03d}" for i in range(start_ordinal, end_ordinal + 1)]
    course_reports = [
        collect_course_evidence_status(
            data_root,
            course_id,
            output_version,
            through_stage=through_stage,
        )
        for course_id in courses
    ]
    failed_courses = [c["course_id"] for c in course_reports if not c["ok"]]
    failed_cases = [
        f"{c['course_id']}:{case_id}"
        for c in course_reports
        for case_id in c["failed_cases"]
    ]
    payload = {
        "schema_version": "1.0",
        "status": "complete" if not failed_courses and not failed_cases else "needs_review",
        "wave_id": wave_id,
        "through_stage": through_stage,
        "output_version": output_version,
        "courses": courses,
        "failed_courses": failed_courses,
        "failed_cases": failed_cases,
        "enabled_stages": enabled_stages(through_stage),
        "forbidden_stages": list(FORBIDDEN_STAGES),
        "course_reports": course_reports,
        "completed_at": _utc_now(),
    }
    out = (
        data_root
        / "batches"
        / batch_id
        / f"evidence-pipeline-{wave_id}-complete.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, json.dumps(payload, ensure_ascii=False, indent=2))
    return out


def build_evidence_baseline(
    data_root: Path,
    *,
    start_ordinal: int,
    end_ordinal: int,
    p01_version: str,
    p02_version: str,
    p03_version: str,
    p04_version: str,
    previous_p03_version: str | None = None,
) -> dict[str, Any]:
    """Build evidence-baseline manifest for a course range."""
    data_root = Path(data_root).resolve()
    courses_out: list[dict[str, Any]] = []
    for ordinal in range(start_ordinal, end_ordinal + 1):
        course_id = f"C{ordinal:03d}"
        course_dir = data_root / "courses" / course_id
        p03_path = course_dir / "03_cases" / f"P03-{p03_version}.json"
        prev_path = (
            course_dir / "03_cases" / f"P03-{previous_p03_version}.json"
            if previous_p03_version
            else None
        )
        prev_payload = None
        if prev_path and prev_path.exists():
            prev_payload = json.loads(prev_path.read_text(encoding="utf-8-sig"))
        cases_payload = []
        if p03_path.exists():
            p03 = json.loads(p03_path.read_text(encoding="utf-8-sig"))
            prev_cases = {
                str(c.get("case_id")): c
                for c in ((prev_payload or {}).get("cases") or [])
                if isinstance(c, dict)
            }
            for case in p03.get("cases") or []:
                if not isinstance(case, dict):
                    continue
                case_id = str(case.get("case_id"))
                changed = True
                if case_id in prev_cases:
                    prev = prev_cases[case_id]
                    changed = (
                        prev.get("start_segment_id") != case.get("start_segment_id")
                        or prev.get("end_segment_id") != case.get("end_segment_id")
                    )
                qa_status = _qa_status(
                    course_dir / "qa" / f"P04-{case_id}-{p04_version}-qa.json"
                )
                cases_payload.append(
                    {
                        "case_id": case_id,
                        "p04_version": p04_version,
                        "source_case_changed": changed,
                        "qa_status": qa_status,
                    }
                )
        courses_out.append(
            {
                "course_id": course_id,
                "p01_version": p01_version,
                "p02_version": p02_version,
                "p03_version": p03_version,
                "cases": cases_payload,
            }
        )
    return {
        "schema_version": "1.0",
        "generated_at": _utc_now(),
        "courses": courses_out,
    }


def write_evidence_baseline(path: Path, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path
