"""Baseline-driven Afeng pilot preparation and deterministic dry-run reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.afeng import (
    build_afeng_evidence_package,
    build_external_payload,
    content_hash,
    validate_evidence_package,
)
from course_video_analyzer.knowledge.afeng_models import (
    AfengEvidencePackage,
    ExternalSegmentProfile,
    RightsStatus,
)

DEFAULT_PILOT_COURSES = ("C003", "C006", "C010")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BaselineCase(StrictModel):
    case_id: str
    p04_version: str
    p04_input_version: str | None = None
    source_case_changed: bool = False
    qa_status: str


class BaselineCourse(StrictModel):
    course_id: str
    p01_version: str
    p02_version: str
    p03_version: str
    cases: list[BaselineCase]


class EvidenceBaseline(StrictModel):
    schema_version: str = "1.0"
    generated_at: str | None = None
    policy: str | None = None
    generated_from: str | None = None
    courses: list[BaselineCourse]


class PilotCaseResult(StrictModel):
    course_id: str
    case_id: str
    p04_version: str
    evidence_path: str
    input_hash: str
    evidence_qa_status: str
    segment_count: int = Field(ge=0)
    external_segment_count: int = Field(ge=0)
    omitted_external_segment_count: int = Field(ge=0)
    required_evidence_coverage: float = Field(ge=0, le=1)
    statement_count: int = Field(ge=0)
    evidence_review_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    pii_finding_count: int = Field(ge=0)
    external_payload_safe: bool
    estimated_input_characters: int = Field(ge=0)


class PilotManifest(StrictModel):
    schema_version: str = "1.0"
    pipeline_version: str = "afeng-method-v001"
    pilot_id: str
    baseline_path: str
    baseline_hash: str
    generated_at: str
    course_ids: list[str]
    external_segment_profile: ExternalSegmentProfile = "evidence_focused"
    external_context_window: int = Field(default=1, ge=0)
    status: str
    cases: list[PilotCaseResult]
    failures: list[dict[str, str]] = Field(default_factory=list)


class ManualReviewItem(StrictModel):
    course_id: str
    case_id: str
    knowledge_id: str = ""
    review_status: str = "pending"
    method_complete: bool | None = None
    no_external_additions: bool | None = None
    attribution_correct: bool | None = None
    outcomes_not_upgraded: bool | None = None
    generalization_correct: bool | None = None
    conditions_and_limits_complete: bool | None = None
    evidence_supports_fields: bool | None = None
    adaptations_preserve_meaning: bool | None = None
    required_corrections: list[str] = Field(default_factory=list)
    reviewer_notes: str = ""


class ManualReviewWorkbook(StrictModel):
    schema_version: str = "1.0"
    pipeline_version: str = "afeng-method-v001"
    pilot_id: str
    created_at: str
    items: list[ManualReviewItem]


def load_evidence_baseline(path: Path) -> EvidenceBaseline:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    baseline = EvidenceBaseline.model_validate(payload)
    course_ids = [course.course_id for course in baseline.courses]
    if len(course_ids) != len(set(course_ids)):
        raise ValueError("baseline contains duplicate course IDs")
    for course in baseline.courses:
        case_ids = [case.case_id for case in course.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError(f"baseline contains duplicate case IDs: {course.course_id}")
        for case in course.cases:
            if case.qa_status != "pass":
                raise ValueError(
                    f"baseline contains non-passing P04: {course.course_id}/{case.case_id}"
                )
    return baseline


def build_legacy_baseline(
    data_root: Path,
    course_ids: list[str],
    *,
    version: str = "knowledge-v002",
) -> EvidenceBaseline:
    """Create an in-memory temporary baseline for pre-freeze dry-runs only."""
    courses: list[BaselineCourse] = []
    for course_id in course_ids:
        course_dir = Path(data_root) / "courses" / course_id
        p03_path = course_dir / "03_cases" / f"P03-{version}.json"
        p03 = json.loads(p03_path.read_text(encoding="utf-8-sig"))
        cases: list[BaselineCase] = []
        for item in p03.get("cases") or []:
            if not isinstance(item, dict) or not item.get("case_id"):
                continue
            case_id = str(item["case_id"])
            qa_path = course_dir / "qa" / f"P04-{case_id}-{version}-qa.json"
            qa = json.loads(qa_path.read_text(encoding="utf-8-sig"))
            cases.append(
                BaselineCase(
                    case_id=case_id,
                    p04_version=version,
                    p04_input_version=version,
                    qa_status=str(qa.get("status") or "unknown"),
                )
            )
        courses.append(
            BaselineCourse(
                course_id=course_id,
                p01_version=version,
                p02_version=version,
                p03_version=version,
                cases=cases,
            )
        )
    baseline = EvidenceBaseline(courses=courses, generated_at=None)
    for course in baseline.courses:
        for case in course.cases:
            if case.qa_status != "pass":
                raise ValueError(f"legacy P04 QA is not pass: {course.course_id}/{case.case_id}")
    return baseline


def write_baseline(path: Path, baseline: EvidenceBaseline) -> Path:
    target = Path(path)
    if target.exists():
        existing = EvidenceBaseline.model_validate_json(target.read_text(encoding="utf-8"))
        if existing.model_dump(mode="json") == baseline.model_dump(mode="json"):
            return target
        raise FileExistsError(f"baseline path already contains different data: {target}")
    atomic_write_text(target, baseline.model_dump_json(indent=2))
    return target


def _resolve_case_paths(
    data_root: Path,
    course: BaselineCourse,
    case: BaselineCase,
    *,
    historical_p05_version: str | None,
) -> tuple[Path, Path, Path | None, Path]:
    course_dir = Path(data_root) / "courses" / course.course_id
    input_version = case.p04_input_version or case.p04_version
    case_input = (
        course_dir
        / "04_knowledge"
        / f"P04-input-{input_version}"
        / f"{case.case_id}.json"
    )
    p04 = (
        course_dir / "04_knowledge" / f"P04-{case.p04_version}" / f"{case.case_id}.json"
    )
    p05 = None
    if historical_p05_version and not case.source_case_changed:
        candidate = (
            course_dir
            / "04_knowledge"
            / f"P05-{historical_p05_version}"
            / f"{case.case_id}.json"
        )
        if candidate.is_file():
            p05 = candidate
    source = course_dir / "source.json"
    for required in (case_input, p04, source):
        if not required.is_file():
            raise FileNotFoundError(f"baseline artifact is missing: {required}")
    return case_input, p04, p05, source


def prepare_afeng_pilot(
    baseline: EvidenceBaseline,
    baseline_path: Path,
    data_root: Path,
    output_root: Path,
    *,
    pilot_id: str,
    course_ids: list[str] | None = None,
    historical_p05_version: str | None = "knowledge-v002",
    rights_status: RightsStatus = RightsStatus.RESEARCH_ONLY,
    external_segment_profile: ExternalSegmentProfile = "evidence_focused",
    external_context_window: int = 1,
) -> PilotManifest:
    selected = course_ids or list(DEFAULT_PILOT_COURSES)
    course_map = {course.course_id: course for course in baseline.courses}
    missing = sorted(set(selected) - set(course_map))
    if missing:
        raise ValueError(f"pilot courses are missing from baseline: {missing}")
    results: list[PilotCaseResult] = []
    failures: list[dict[str, str]] = []
    for course_id in selected:
        course = course_map[course_id]
        for case in course.cases:
            try:
                case_input, p04, p05, source = _resolve_case_paths(
                    data_root,
                    course,
                    case,
                    historical_p05_version=historical_p05_version,
                )
                evidence_path = (
                    Path(output_root)
                    / pilot_id
                    / "evidence"
                    / course_id
                    / f"{case.case_id}.json"
                )
                build_afeng_evidence_package(
                    course_id,
                    case.case_id,
                    case_input,
                    p04,
                    evidence_path,
                    p05_path=p05,
                    source_path=source,
                    rights_status=rights_status,
                    source_pipeline_version=case.p04_version,
                )
                package = AfengEvidencePackage.model_validate_json(
                    evidence_path.read_text(encoding="utf-8")
                )
                qa = validate_evidence_package(package)
                external = build_external_payload(
                    package,
                    segment_profile=external_segment_profile,
                    context_window=external_context_window,
                )
                results.append(
                    PilotCaseResult(
                        course_id=course_id,
                        case_id=case.case_id,
                        p04_version=case.p04_version,
                        evidence_path=str(evidence_path.resolve()),
                        input_hash=package.input_hash,
                        evidence_qa_status=str(qa["status"]),
                        segment_count=len(package.segments),
                        external_segment_count=external.selected_segment_count,
                        omitted_external_segment_count=external.omitted_segment_count,
                        required_evidence_coverage=external.required_evidence_coverage,
                        statement_count=len(package.statements),
                        evidence_review_count=len(package.evidence_reviews),
                        warning_count=len(package.source_warnings),
                        pii_finding_count=sum(item.count for item in external.pii_findings),
                        external_payload_safe=external.external_payload_safe,
                        estimated_input_characters=len(
                            json.dumps(external.redacted_package, ensure_ascii=False)
                        ),
                    )
                )
            except Exception as exc:
                failures.append(
                    {"course_id": course_id, "case_id": case.case_id, "error": str(exc)}
                )
    manifest = PilotManifest(
        pilot_id=pilot_id,
        baseline_path=str(Path(baseline_path).resolve()),
        baseline_hash=content_hash(baseline.model_dump(mode="json")),
        generated_at=_utc_now(),
        course_ids=selected,
        external_segment_profile=external_segment_profile,
        external_context_window=external_context_window,
        status="ready" if not failures and all(item.external_payload_safe for item in results) else "needs_review",
        cases=results,
        failures=failures,
    )
    manifest_path = Path(output_root) / pilot_id / "manifest.json"
    if manifest_path.exists():
        existing = PilotManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        comparable_existing = existing.model_copy(update={"generated_at": manifest.generated_at})
        if comparable_existing != manifest:
            raise FileExistsError(f"pilot manifest already exists with different data: {manifest_path}")
        return existing
    atomic_write_text(manifest_path, manifest.model_dump_json(indent=2))
    return manifest


def write_pilot_summary(manifest: PilotManifest, output_path: Path) -> Path:
    total_segments = sum(item.segment_count for item in manifest.cases)
    total_statements = sum(item.statement_count for item in manifest.cases)
    total_characters = sum(item.estimated_input_characters for item in manifest.cases)
    lines = [
        f"# 阿峰三课试验准备报告：{manifest.pilot_id}",
        "",
        f"- 状态：`{manifest.status}`",
        f"- baseline：`{manifest.baseline_path}`",
        f"- 课程：{', '.join(manifest.course_ids)}",
        f"- 外发 segment profile：`{manifest.external_segment_profile}`",
        f"- 相邻上下文窗口：`{manifest.external_context_window}`",
        f"- 案例数：{len(manifest.cases)}",
        f"- 失败数：{len(manifest.failures)}",
        f"- 证据 segments：{total_segments}",
        f"- P04 statements：{total_statements}",
        f"- 脱敏后输入字符估算：{total_characters}",
        "",
        "| Course | Case | P04 | Local segs | External segs | Evidence coverage | Statements | Reviews | Warnings | PII | External safe |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in manifest.cases:
        lines.append(
            f"| {item.course_id} | {item.case_id} | {item.p04_version} | "
            f"{item.segment_count} | {item.external_segment_count} | {item.required_evidence_coverage:.1%} | "
            f"{item.statement_count} | "
            f"{item.evidence_review_count} | "
            f"{item.warning_count} | {item.pii_finding_count} | {item.external_payload_safe} |"
        )
    if manifest.failures:
        lines.extend(["", "## 失败", ""])
        for failure in manifest.failures:
            lines.append(
                f"- `{failure['course_id']}/{failure['case_id']}`：{failure['error']}"
            )
    atomic_write_text(output_path, "\n".join(lines) + "\n")
    return Path(output_path)


def write_manual_review_template(
    manifest: PilotManifest,
    json_path: Path,
    markdown_path: Path,
) -> tuple[Path, Path]:
    workbook = ManualReviewWorkbook(
        pilot_id=manifest.pilot_id,
        created_at=_utc_now(),
        items=[
            ManualReviewItem(course_id=item.course_id, case_id=item.case_id)
            for item in manifest.cases
        ],
    )
    if Path(json_path).exists():
        existing = ManualReviewWorkbook.model_validate_json(
            Path(json_path).read_text(encoding="utf-8")
        )
        if [(item.course_id, item.case_id) for item in existing.items] != [
            (item.course_id, item.case_id) for item in workbook.items
        ]:
            raise FileExistsError(f"manual review template contains different cases: {json_path}")
    else:
        atomic_write_text(json_path, workbook.model_dump_json(indent=2))
    lines = [
        f"# 阿峰人工忠实度复核：{manifest.pilot_id}",
        "",
        "每个案例完成模型运行后逐项填写。判断标准只涉及课程忠实度，不评价课程是否正确或安全。",
        "",
    ]
    checks = (
        "方法是否完整",
        "是否没有课程外新增内容",
        "讲师观点和课程观点归属是否正确",
        "课程声称结果是否没有被升级为客观事实",
        "单案例是否没有被扩大为普遍规律",
        "条件、限制、失败和例外是否完整",
        "evidence ID 是否真实支持主要字段",
        "直接改写和组合是否保持课程原意",
    )
    for item in manifest.cases:
        lines.extend(
            [
                f"## {item.course_id} / {item.case_id}",
                "",
                *[f"- [ ] {check}" for check in checks],
                "- 必须修正：",
                "- 复核备注：",
                "",
            ]
        )
    atomic_write_text(markdown_path, "\n".join(lines))
    return Path(json_path), Path(markdown_path)
