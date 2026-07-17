"""Deterministic evidence, validation, publication, and rendering for Afeng."""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ValidationError

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.afeng_models import (
    AfengEvidencePackage,
    AfengMethodDraft,
    EvidenceReview,
    EvidenceSegment,
    EvidenceStatement,
    EvidenceStatementType,
    EvidenceStatus,
    ExternalPayload,
    ExternalSegmentProfile,
    FidelityAudit,
    PiiFinding,
    PublicationClass,
    PublicationRecord,
    RightsStatus,
    SourceTimeRange,
    SourceWarning,
)

PIPELINE_VERSION = "afeng-method-v001"
EVIDENCE_PROMPT_VERSION = "mimo-method-v001"
PROMPT_VERSION = "mimo-method-v002"

_PII_PATTERNS = {
    "mainland_phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "mainland_id": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "wechat_id": re.compile(
        r"(?i)(微信(?:号|ID)?|wechat(?:\s*id)?)\s*[:：]?\s*[A-Za-z][-_A-Za-z0-9]{5,19}"
    ),
}
_PII_REPLACEMENTS = {
    "mainland_phone": "[手机号已脱敏]",
    "mainland_id": "[身份证号已脱敏]",
    "email": "[邮箱已脱敏]",
    "wechat_id": "[微信号已脱敏]",
}


def canonical_json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")

    def encode(item: Any) -> Any:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        if isinstance(item, Enum):
            return item.value
        if isinstance(item, Path):
            return str(item)
        raise TypeError(f"cannot encode {type(item).__name__}")

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=encode,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def cache_key(input_hash: str, prompt_version: str, model: str, stage: str) -> str:
    return content_hash(
        {
            "input_hash": input_hash,
            "prompt_version": prompt_version,
            "model": model,
            "stage": stage,
        }
    )


def canonical_knowledge_id(course_id: str, case_id: str) -> str:
    """Program-controlled stable knowledge id, independent of model output.

    Format: ``AFENG-{course_id}-{case_id}`` (e.g. ``AFENG-C007-CASE-C007-001``).
    The model is still free to emit a knowledge_id in its draft, but that value
    must never be used as the remote idempotency key; this canonical form is the
    only stable, cross-run, cross-model identity for a published document.
    """
    return f"AFENG-{course_id}-{case_id}"


def normalize_method_knowledge_id(draft: AfengMethodDraft) -> AfengMethodDraft:
    """Force a method draft's knowledge_id to the canonical program-controlled value."""
    canonical = canonical_knowledge_id(draft.course_id, draft.case_id)
    if draft.knowledge_id == canonical:
        return draft
    return draft.model_copy(update={"knowledge_id": canonical})


def normalize_fidelity_audit_knowledge_id(audit: FidelityAudit) -> FidelityAudit:
    """Force a fidelity audit's knowledge_id to the canonical value."""
    canonical = canonical_knowledge_id(audit.course_id, audit.case_id)
    if audit.knowledge_id == canonical:
        return audit
    return audit.model_copy(update={"knowledge_id": canonical})


def normalize_publication_knowledge_id(publication: PublicationRecord) -> PublicationRecord:
    """Force a publication record's knowledge_id to the canonical value."""
    canonical = canonical_knowledge_id(publication.course_id, publication.case_id)
    if publication.knowledge_id == canonical:
        return publication
    return publication.model_copy(update={"knowledge_id": canonical})



def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write_new_or_same(path: Path, content: str) -> Path:
    target = Path(path)
    if target.exists():
        if target.read_text(encoding="utf-8") == content:
            return target
        raise FileExistsError(f"artifact already exists with different content: {target}")
    atomic_write_text(target, content)
    return target


def _evidence_ids(item: dict[str, Any], field: str) -> list[str]:
    value = item.get(field, [])
    return [str(item) for item in value] if isinstance(value, list) else []


def _statement_text(item: dict[str, Any]) -> str:
    return str(item.get("text") or item.get("content") or "").strip()


def _build_review_map(p05: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    reviews: dict[tuple[str, str], dict[str, Any]] = {}
    for item in p05.get("evidence_reviews", []):
        if isinstance(item, dict):
            key = (str(item.get("target_type", "")), str(item.get("target_id", "")))
            reviews[key] = item
    return reviews


def build_afeng_evidence_package(
    course_id: str,
    case_id: str,
    case_input_path: Path,
    p04_path: Path,
    output_path: Path,
    *,
    p05_path: Path | None = None,
    source_path: Path | None = None,
    rights_status: RightsStatus = RightsStatus.RESEARCH_ONLY,
    source_pipeline_version: str | None = None,
) -> Path:
    """Build the local authoritative package. P06 and P05 safety fields are never read."""
    case_input = _load_json(case_input_path)
    p04 = _load_json(p04_path)
    p05 = _load_json(p05_path) if p05_path else {}
    source = _load_json(source_path) if source_path else {}
    if case_input.get("course_id") != course_id or p04.get("course_id") != course_id:
        raise ValueError("course_id does not match P04 inputs")
    if str((case_input.get("case") or {}).get("case_id", case_id)) != case_id:
        raise ValueError("case_id does not match case input")
    if p04.get("case_id") != case_id:
        raise ValueError("case_id does not match P04 output")

    raw_segments = case_input.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("case input has no segments")
    segments: list[EvidenceSegment] = []
    for item in raw_segments:
        if not isinstance(item, dict) or not item.get("segment_id"):
            raise ValueError("invalid segment in case input")
        segment_id = str(item["segment_id"])
        text = str(item.get("text") or item.get("normalized_text") or "")
        segments.append(
            EvidenceSegment(
                evidence_id=segment_id,
                segment_id=segment_id,
                start_ms=int(item.get("start_ms", 0)),
                end_ms=int(item.get("end_ms", item.get("start_ms", 0))),
                source_type=str(item.get("content_type") or item.get("source_type") or "unknown"),
                speaker_role=str(item.get("source_role") or item.get("speaker") or "unknown"),
                epistemic_type=str(item.get("epistemic_type") or "unknown"),
                raw_text=str(item["raw_text"]) if item.get("raw_text") is not None else None,
                normalized_text=text,
            )
        )
    valid_ids = {item.evidence_id for item in segments}
    review_map = _build_review_map(p05)
    statements: list[EvidenceStatement] = []
    field_specs: tuple[tuple[str, EvidenceStatementType, str], ...] = (
        ("observations", "observation", "evidence_segment_ids"),
        ("instructor_claims", "instructor_claim", "evidence_segment_ids"),
        ("alternative_explanations", "alternative_explanation", "basis_evidence_segment_ids"),
        ("outcomes", "claimed_outcome", "evidence_segment_ids"),
        ("quoted_expressions", "quoted_expression", "evidence_segment_ids"),
    )
    for field, statement_type, evidence_field in field_specs:
        review_target_type = "outcome" if statement_type == "claimed_outcome" else statement_type
        for index, item in enumerate(p04.get(field, []), start=1):
            if not isinstance(item, dict):
                continue
            statement_id = str(item.get("id") or f"{statement_type}-{index:03d}")
            ids = _evidence_ids(item, evidence_field)
            invalid = sorted(set(ids) - valid_ids)
            if invalid:
                raise ValueError(f"P04 statement references evidence outside case: {invalid[:5]}")
            review = review_map.get((review_target_type, statement_id), {})
            status_value = str(review.get("status") or EvidenceStatus.NOT_REVIEWED.value)
            try:
                status = EvidenceStatus(status_value)
            except ValueError:
                status = EvidenceStatus.NOT_REVIEWED
            attributes = {
                key: value
                for key, value in item.items()
                if key not in {"id", "text", "content", evidence_field}
            }
            statements.append(
                EvidenceStatement(
                    statement_id=statement_id,
                    statement_type=statement_type,
                    text=_statement_text(item),
                    evidence_ids=ids,
                    evidence_status=status,
                    review_note=str(review.get("note") or ""),
                    attributes=attributes,
                )
            )

    reviews: list[EvidenceReview] = []
    for item in p05.get("evidence_reviews", []):
        if not isinstance(item, dict):
            continue
        ids = _evidence_ids(item, "supported_by_segment_ids")
        invalid = sorted(set(ids) - valid_ids)
        if invalid:
            raise ValueError(f"P05 review references evidence outside case: {invalid[:5]}")
        reviews.append(
            EvidenceReview(
                target_type=str(item.get("target_type") or ""),
                target_id=str(item.get("target_id") or ""),
                status=EvidenceStatus(str(item.get("status") or "not_reviewed")),
                evidence_ids=ids,
                note=str(item.get("note") or ""),
            )
        )

    warnings: list[SourceWarning] = []
    for item in p04.get("uncertainties", []):
        if isinstance(item, dict):
            warnings.append(
                SourceWarning(
                    warning_type="uncertainty",
                    field=str(item.get("field") or ""),
                    note=str(item.get("note") or ""),
                    evidence_ids=_evidence_ids(item, "evidence_segment_ids"),
                )
            )
    for item in p05.get("missing_context", []):
        if isinstance(item, dict):
            warnings.append(
                SourceWarning(
                    warning_type="missing_context",
                    field=str(item.get("field") or ""),
                    note=str(item.get("note") or ""),
                    evidence_ids=_evidence_ids(item, "evidence_segment_ids"),
                )
            )
    for item in p05.get("required_corrections", []):
        if isinstance(item, dict):
            warnings.append(
                SourceWarning(
                    warning_type="required_correction",
                    target_type=str(item.get("target_type") or ""),
                    target_id=str(item.get("target_id") or ""),
                    action=str(item.get("action") or ""),
                    note=str(item.get("note") or ""),
                )
            )

    case = case_input.get("case") or {}
    start_ms = min(item.start_ms for item in segments)
    end_ms = max(item.end_ms for item in segments)
    package_without_hash = {
        "schema_version": "1.0",
        "pipeline_version": PIPELINE_VERSION,
        "prompt_version": EVIDENCE_PROMPT_VERSION,
        "source_pipeline_version": source_pipeline_version
        or str(p04.get("prompt_version") or case_input.get("prompt_version") or "unknown"),
        "course_id": course_id,
        "course_title": str(source.get("title") or ""),
        "case_id": case_id,
        "case_title": str(p04.get("case_title") or case.get("title") or ""),
        "case_summary": str(p04.get("summary") or ""),
        "rights_status": rights_status,
        "course_context": "",
        "source_time_range": SourceTimeRange(start_ms=start_ms, end_ms=end_ms),
        "segments": segments,
        "statements": statements,
        "evidence_reviews": reviews,
        "source_warnings": warnings,
    }
    package = AfengEvidencePackage(
        **package_without_hash,
        input_hash=content_hash(package_without_hash),
    )
    return _write_new_or_same(Path(output_path), package.model_dump_json(indent=2))


def build_afeng_course_evidence_packages(
    course_id: str,
    data_root: Path,
    *,
    p04_version: str,
    p05_version: str | None = None,
    output_version: str = "v001",
    rights_status: RightsStatus = RightsStatus.RESEARCH_ONLY,
) -> list[Path]:
    course_dir = Path(data_root) / "courses" / course_id
    input_dir = course_dir / "04_knowledge" / f"P04-input-{p04_version}"
    p04_dir = course_dir / "04_knowledge" / f"P04-{p04_version}"
    p05_dir = (
        course_dir / "04_knowledge" / f"P05-{p05_version}" if p05_version else None
    )
    source_path = course_dir / "source.json"
    if not input_dir.is_dir() or not p04_dir.is_dir() or not source_path.is_file():
        raise FileNotFoundError(f"course evidence inputs are incomplete: {course_dir}")
    p04_paths = sorted(path for path in p04_dir.glob("*.json") if ".cursor-task." not in path.name)
    if not p04_paths:
        raise ValueError(f"no P04 case outputs found: {p04_dir}")
    output_dir = course_dir / "06_afeng_methods" / f"evidence-package-{output_version}"
    outputs: list[Path] = []
    for p04_path in p04_paths:
        case_id = p04_path.stem
        case_input = input_dir / f"{case_id}.json"
        if not case_input.is_file():
            raise FileNotFoundError(f"missing P04 case input: {case_input}")
        p05_path = p05_dir / f"{case_id}.json" if p05_dir else None
        if p05_path is not None and not p05_path.is_file():
            p05_path = None
        outputs.append(
            build_afeng_evidence_package(
                course_id,
                case_id,
                case_input,
                p04_path,
                output_dir / f"{case_id}.json",
                p05_path=p05_path,
                source_path=source_path,
                rights_status=rights_status,
                source_pipeline_version=p04_version,
            )
        )
    return outputs


def _redact_string(value: str, counts: dict[str, int]) -> str:
    result = value
    for kind, pattern in _PII_PATTERNS.items():
        matches = pattern.findall(result)
        if matches:
            counts[kind] = counts.get(kind, 0) + len(matches)
            result = pattern.sub(_PII_REPLACEMENTS[kind], result)
    return result


def _redact_value(value: Any, counts: dict[str, int]) -> Any:
    if isinstance(value, str):
        return _redact_string(value, counts)
    if isinstance(value, list):
        return [_redact_value(item, counts) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item, counts) for key, item in value.items()}
    return value


def _select_external_segments(
    package: AfengEvidencePackage,
    segment_profile: ExternalSegmentProfile,
    context_window: int,
) -> list[EvidenceSegment]:
    if context_window < 0:
        raise ValueError("context_window must be non-negative")
    if segment_profile == "full":
        return list(package.segments)
    if segment_profile != "evidence_focused":
        raise ValueError("segment_profile must be full or evidence_focused")
    referenced = {
        evidence_id
        for statement in package.statements
        for evidence_id in statement.evidence_ids
    }
    referenced.update(
        evidence_id
        for review in package.evidence_reviews
        for evidence_id in review.evidence_ids
    )
    referenced.update(
        evidence_id
        for warning in package.source_warnings
        for evidence_id in warning.evidence_ids
    )
    indexes = {
        index
        for index, segment in enumerate(package.segments)
        if segment.evidence_id in referenced
    }
    selected_indexes: set[int] = set()
    for index in indexes:
        selected_indexes.update(
            range(
                max(0, index - context_window),
                min(len(package.segments), index + context_window + 1),
            )
        )
    return [package.segments[index] for index in sorted(selected_indexes)]


def build_external_payload(
    package: AfengEvidencePackage,
    *,
    segment_profile: ExternalSegmentProfile = "evidence_focused",
    context_window: int = 1,
) -> ExternalPayload:
    selected_segments = _select_external_segments(package, segment_profile, context_window)
    required_ids = {
        evidence_id
        for statement in package.statements
        for evidence_id in statement.evidence_ids
    }
    required_ids.update(
        evidence_id
        for review in package.evidence_reviews
        for evidence_id in review.evidence_ids
    )
    required_ids.update(
        evidence_id
        for warning in package.source_warnings
        for evidence_id in warning.evidence_ids
    )
    selected_ids = {item.evidence_id for item in selected_segments}
    selected_required = required_ids & selected_ids
    coverage = len(selected_required) / len(required_ids) if required_ids else 1.0
    counts: dict[str, int] = {}
    source = package.model_dump(mode="json")
    source["segments"] = [item.model_dump(mode="json") for item in selected_segments]
    source["model_payload_selection"] = {
        "segment_profile": segment_profile,
        "context_window": context_window,
        "original_segment_count": len(package.segments),
        "selected_segment_count": len(selected_segments),
        "omitted_segment_count": len(package.segments) - len(selected_segments),
        "selection_rule": "all P04/P05 referenced segments plus adjacent context",
        "required_evidence_count": len(required_ids),
        "selected_required_evidence_count": len(selected_required),
        "required_evidence_coverage": coverage,
        "local_full_package_input_hash": package.input_hash,
    }
    redacted = _redact_value(source, counts)
    remaining: dict[str, int] = {}
    _redact_value(redacted, remaining)
    return ExternalPayload(
        source_input_hash=package.input_hash,
        segment_profile=segment_profile,
        original_segment_count=len(package.segments),
        selected_segment_count=len(selected_segments),
        omitted_segment_count=len(package.segments) - len(selected_segments),
        required_evidence_count=len(required_ids),
        selected_required_evidence_count=len(selected_required),
        required_evidence_coverage=coverage,
        selected_evidence_ids_hash=content_hash(
            [item.evidence_id for item in selected_segments]
        ),
        redacted_package=redacted,
        pii_findings=[PiiFinding(kind=kind, count=count) for kind, count in sorted(counts.items())],
        external_payload_safe=not remaining,
    )


def validate_evidence_package(package: AfengEvidencePackage) -> dict[str, Any]:
    payload = package.model_dump(mode="json", exclude={"input_hash"})
    expected_hash = content_hash(payload)
    segment_ids = [item.segment_id for item in package.segments]
    evidence_ids = [item.evidence_id for item in package.segments]
    valid_ids = set(evidence_ids)
    invalid_statement_ids = sorted(
        {
            evidence_id
            for statement in package.statements
            for evidence_id in statement.evidence_ids
            if evidence_id not in valid_ids
        }
    )
    invalid_review_ids = sorted(
        {
            evidence_id
            for review in package.evidence_reviews
            for evidence_id in review.evidence_ids
            if evidence_id not in valid_ids
        }
    )
    invalid_warning_ids = sorted(
        {
            evidence_id
            for warning in package.source_warnings
            for evidence_id in warning.evidence_ids
            if evidence_id not in valid_ids
        }
    )
    checks = {
        "input_hash": package.input_hash == expected_hash,
        "segments_present": bool(package.segments),
        "segment_ids_unique": len(segment_ids) == len(set(segment_ids)),
        "evidence_ids_unique": len(evidence_ids) == len(set(evidence_ids)),
        "evidence_id_matches_segment_id": all(
            item.evidence_id == item.segment_id for item in package.segments
        ),
        "statement_evidence_valid": not invalid_statement_ids,
        "review_evidence_valid": not invalid_review_ids,
        "warning_evidence_valid": not invalid_warning_ids,
    }
    return {
        "schema_version": "1.0",
        "stage": "afeng_evidence_package",
        "status": "pass" if all(checks.values()) else "needs_review",
        "checks": checks,
        "expected_input_hash": expected_hash,
        "invalid_evidence_ids": sorted(
            set(invalid_statement_ids + invalid_review_ids + invalid_warning_ids)
        ),
    }


def write_external_payload(evidence_path: Path, output_path: Path) -> Path:
    package = AfengEvidencePackage.model_validate(_load_json(evidence_path))
    report = validate_evidence_package(package)
    if report["status"] != "pass":
        raise ValueError(f"evidence package failed deterministic QA: {report}")
    payload = build_external_payload(package)
    if not payload.external_payload_safe:
        raise ValueError("external payload still contains deterministic PII matches")
    return _write_new_or_same(Path(output_path), payload.model_dump_json(indent=2))


def iter_method_evidence_ids(draft: AfengMethodDraft) -> Iterable[str]:
    yield from draft.problem_addressed.evidence_ids
    yield from draft.course_perspective.evidence_ids
    yield from draft.core_logic.evidence_ids
    for item in draft.applicable_conditions:
        yield from item.evidence_ids
    for item in draft.not_applicable_conditions:
        yield from item.evidence_ids
    for item in draft.steps:
        yield from item.evidence_ids
    for item in draft.signals_used_by_course:
        yield from item.evidence_ids
    for item in draft.example_expressions:
        yield from item.evidence_ids
    yield from draft.course_reported_outcome.evidence_ids
    for item in draft.course_stated_limits:
        yield from item.evidence_ids


def validate_method_draft(
    package: AfengEvidencePackage, draft: AfengMethodDraft
) -> dict[str, Any]:
    valid_ids = {item.evidence_id for item in package.segments}
    referenced = list(iter_method_evidence_ids(draft))
    invalid_ids = sorted(set(referenced) - valid_ids)
    missing_core: list[str] = []
    for field, content, ids in (
        ("problem_addressed", draft.problem_addressed.content, draft.problem_addressed.evidence_ids),
        ("course_perspective", draft.course_perspective.content, draft.course_perspective.evidence_ids),
        ("core_logic", draft.core_logic.content, draft.core_logic.evidence_ids),
    ):
        if content.strip() and not ids:
            missing_core.append(field)
    evidence_backed_collections = (
        ("applicable_conditions", draft.applicable_conditions),
        ("not_applicable_conditions", draft.not_applicable_conditions),
        ("steps", draft.steps),
        ("signals_used_by_course", draft.signals_used_by_course),
        ("example_expressions", draft.example_expressions),
        ("course_stated_limits", draft.course_stated_limits),
    )
    for field, items in evidence_backed_collections:
        missing_core.extend(
            f"{field}[{index}]" for index, item in enumerate(items) if not item.evidence_ids
        )
    if draft.course_reported_outcome.content.strip() and not draft.course_reported_outcome.evidence_ids:
        missing_core.append("course_reported_outcome")
    identity_ok = (
        draft.course_id == package.course_id
        and draft.case_id == package.case_id
        and draft.pipeline_version == PIPELINE_VERSION
        and draft.prompt_version == PROMPT_VERSION
    )
    expected_range = evidence_time_range(package, referenced)
    time_range_ok = expected_range is not None and draft.source_time_range == expected_range
    checks = {
        "identity": identity_ok,
        "evidence_ids_valid": not invalid_ids,
        "core_evidence_present": not missing_core,
        "source_time_range_derived": time_range_ok,
        "steps_ordered": [item.order for item in draft.steps] == list(range(1, len(draft.steps) + 1)),
    }
    return {
        "schema_version": "1.0",
        "stage": "afeng_method_draft",
        "status": "pass" if all(checks.values()) else "needs_review",
        "checks": checks,
        "invalid_evidence_ids": invalid_ids,
        "missing_core_evidence": missing_core,
        "expected_source_time_range": expected_range.model_dump(mode="json") if expected_range else None,
    }


def evidence_time_range(
    package: AfengEvidencePackage, evidence_ids: Iterable[str]
) -> SourceTimeRange | None:
    wanted = set(evidence_ids)
    selected = [item for item in package.segments if item.evidence_id in wanted]
    if not selected:
        return None
    return SourceTimeRange(
        start_ms=min(item.start_ms for item in selected),
        end_ms=max(item.end_ms for item in selected),
    )


def normalize_method_source_time_range(
    package: AfengEvidencePackage, draft: AfengMethodDraft
) -> AfengMethodDraft:
    """Derive the draft time range from its cited evidence instead of model arithmetic."""
    expected = evidence_time_range(package, iter_method_evidence_ids(draft))
    if expected is None or draft.source_time_range == expected:
        return draft
    return draft.model_copy(update={"source_time_range": expected})


def normalize_method_evidence_id_aliases(
    package: AfengEvidencePackage, draft: AfengMethodDraft
) -> AfengMethodDraft:
    """Repair only unambiguous model aliases that resolve to a real segment ID.

    Models occasionally copy a segment number with the ``SIG-`` prefix used for
    a course signal. Conversion is allowed only when the exact ``SEG-`` form is
    present in the current evidence package; all other invalid IDs still fail QA.
    """
    valid_ids = {item.evidence_id for item in package.segments}
    value = draft.model_dump(mode="json")
    changed = False

    def visit(item: Any) -> None:
        nonlocal changed
        if isinstance(item, dict):
            for key, child in item.items():
                if key == "evidence_ids" and isinstance(child, list):
                    for index, evidence_id in enumerate(child):
                        if not isinstance(evidence_id, str) or not evidence_id.startswith("SIG-"):
                            continue
                        candidate = f"SEG-{evidence_id[4:]}"
                        if candidate in valid_ids:
                            child[index] = candidate
                            changed = True
                else:
                    visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return AfengMethodDraft.model_validate(value) if changed else draft


def normalize_unbacked_method_conditions(draft: AfengMethodDraft) -> AfengMethodDraft:
    """Move unsupported condition placeholders to the explicit evidence-gap list."""
    applicable = [item for item in draft.applicable_conditions if item.evidence_ids]
    not_applicable = [item for item in draft.not_applicable_conditions if item.evidence_ids]
    limits = [item for item in draft.course_stated_limits if item.evidence_ids]
    removed = [
        item.condition
        for item in (*draft.applicable_conditions, *draft.not_applicable_conditions)
        if not item.evidence_ids and item.condition.strip()
    ]
    removed.extend(
        item.content
        for item in draft.course_stated_limits
        if not item.evidence_ids and item.content.strip()
    )
    if not removed:
        return draft
    gaps = list(draft.insufficient_course_evidence)
    for content in removed:
        note = f"证据不足，不能作为方法条件或限制：{content}"
        if note not in gaps:
            gaps.append(note)
    return draft.model_copy(
        update={
            "applicable_conditions": applicable,
            "not_applicable_conditions": not_applicable,
            "course_stated_limits": limits,
            "insufficient_course_evidence": gaps,
        }
    )


def validate_fidelity_audit(
    package: AfengEvidencePackage,
    draft: AfengMethodDraft,
    audit: FidelityAudit,
    *,
    expected_revision_number: int | None = None,
) -> dict[str, Any]:
    valid_ids = {item.evidence_id for item in package.segments}
    audit_ids = {evidence_id for item in audit.field_reviews for evidence_id in item.evidence_ids}
    actual_invalid = sorted(audit_ids - valid_ids)
    declared_invalid = sorted(set(audit.invalid_evidence_ids))
    identity_ok = (
        audit.course_id == draft.course_id
        and audit.case_id == draft.case_id
        and audit.knowledge_id == draft.knowledge_id
    )
    pass_is_clean = audit.audit_result != "pass" or not (
        audit.unsupported_additions
        or audit.misattributed_claims
        or audit.missing_course_conditions
        or audit.invalid_evidence_ids
        or audit.external_knowledge_detected
    )
    pass_reviews_supported = audit.audit_result != "pass" or all(
        item.status == "supported" for item in audit.field_reviews
    )
    checks = {
        "identity": identity_ok,
        "revision_number": (
            expected_revision_number is None
            or audit.revision_number == expected_revision_number
        ),
        "audit_evidence_valid": not actual_invalid,
        "declared_invalid_accurate": declared_invalid == actual_invalid,
        "release_gate": audit.release_allowed == (audit.audit_result == "pass"),
        "passing_audit_has_no_open_issues": pass_is_clean,
        "passing_audit_reviews_supported": pass_reviews_supported,
        "field_reviews_present": bool(audit.field_reviews),
    }
    return {
        "schema_version": "1.0",
        "stage": "afeng_fidelity_audit",
        "status": "pass" if all(checks.values()) else "needs_review",
        "checks": checks,
        "actual_invalid_evidence_ids": actual_invalid,
    }


def approve_method(draft: AfengMethodDraft, audit: FidelityAudit) -> AfengMethodDraft:
    if audit.audit_result != "pass" or not audit.release_allowed:
        raise ValueError("fidelity audit did not pass")
    return draft.model_copy(update={"draft_fidelity_status": "reviewed"})


def write_approved_method(draft_path: Path, audit_path: Path, output_path: Path) -> Path:
    draft = AfengMethodDraft.model_validate(_load_json(draft_path))
    audit = FidelityAudit.model_validate(_load_json(audit_path))
    approved = approve_method(draft, audit)
    return _write_new_or_same(Path(output_path), approved.model_dump_json(indent=2))


def validate_publication(
    package: AfengEvidencePackage,
    method: AfengMethodDraft,
    audit: FidelityAudit,
    publication: PublicationRecord,
) -> None:
    if method.draft_fidelity_status != "reviewed":
        raise ValueError("method has not passed fidelity review")
    if audit.audit_result != "pass" or not audit.release_allowed:
        raise ValueError("publication requires a passing fidelity audit")
    if (publication.course_id, publication.case_id, publication.knowledge_id) != (
        method.course_id,
        method.case_id,
        method.knowledge_id,
    ):
        raise ValueError("publication identity does not match approved method")
    valid_ids = {item.evidence_id for item in package.segments}
    invalid = sorted(set(publication.evidence_ids) - valid_ids)
    if invalid:
        raise ValueError(f"publication references invalid evidence: {invalid[:5]}")
    if publication.publishable and not publication.evidence_ids:
        raise ValueError("publishable classification requires evidence")


def _format_ms(milliseconds: int) -> str:
    seconds = milliseconds // 1000
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _list_or_unspecified(items: list[str]) -> str:
    if not items:
        return "课程未明确说明"
    return "\n".join(f"- {item}" for item in items)


def render_afeng_markdown(
    package: AfengEvidencePackage,
    method: AfengMethodDraft,
    audit: FidelityAudit,
    publication: PublicationRecord,
) -> str:
    validate_publication(package, method, audit, publication)
    if not publication.publishable or publication.publication_class == PublicationClass.REJECT:
        raise ValueError("publication record is not publishable")
    evidence_ids = list(dict.fromkeys(iter_method_evidence_ids(method)))
    by_id = {item.evidence_id: item for item in package.segments}
    evidence_lines = []
    for evidence_id in evidence_ids:
        item = by_id[evidence_id]
        text = item.normalized_text.strip() or "（空文本）"
        evidence_lines.append(
            f"- `[{evidence_id}]` [{_format_ms(item.start_ms)}–{_format_ms(item.end_ms)}] "
            f"[{item.speaker_role}/{item.source_type}] {text}"
        )
    conditions = [f"按照课程方法，{item.condition}" for item in method.applicable_conditions]
    not_conditions = [
        f"按照课程方法，{item.condition}" for item in method.not_applicable_conditions
    ]
    steps = [
        f"{item.order}. {item.action}"
        + (f"（按照课程方法，目的：{item.purpose_according_to_course}）" if item.purpose_according_to_course else "")
        for item in method.steps
    ]
    signals = [
        f"{item.signal}：按照课程方法，可能被解释为{item.course_interpretation}"
        for item in method.signals_used_by_course
    ]
    expressions = [f"{item.text}（{item.source}）" for item in method.example_expressions]
    limits = [item.content for item in method.course_stated_limits]
    outcome = method.course_reported_outcome.content or "课程未明确说明"
    frontmatter = [
        "---",
        f'knowledge_id: "{method.knowledge_id}"',
        f'course_id: "{method.course_id}"',
        f'case_id: "{method.case_id}"',
        'content_type: "course_method"',
        f'rights_status: "{package.rights_status.value}"',
        'fidelity_status: "passed"',
        f'publication_class: "{publication.publication_class.value}"',
        f'generalization_level: "{publication.generalization_level}"',
        f'pipeline_version: "{PIPELINE_VERSION}"',
        f'prompt_version: "{PROMPT_VERSION}"',
        f'source_start_ms: {method.source_time_range.start_ms}',
        f'source_end_ms: {method.source_time_range.end_ms}',
        f'input_hash: "{package.input_hash}"',
        "evidence_ids:",
        *[f'  - "{item}"' for item in evidence_ids],
        "---",
    ]
    sections = [
        *frontmatter,
        "",
        f"# {method.method_name}",
        "",
        "## 这个方法解决什么问题",
        "",
        method.problem_addressed.content or "课程未明确说明",
        "",
        "## 按照课程方法如何理解这个情境",
        "",
        method.course_perspective.content or "课程未明确说明",
        "",
        "## 适用条件",
        "",
        _list_or_unspecified(conditions),
        "",
        "## 不适用条件",
        "",
        _list_or_unspecified(not_conditions),
        "",
        "## 核心逻辑",
        "",
        method.core_logic.content or "课程未明确说明",
        "",
        "## 操作步骤",
        "",
        _list_or_unspecified(steps),
        "",
        "## 课程使用的判断信号",
        "",
        _list_or_unspecified(signals),
        "",
        "## 课程示例表达",
        "",
        _list_or_unspecified(expressions),
        "",
        "## 课程中声称或展示的结果",
        "",
        outcome,
        "",
        "## 课程明确提出的限制",
        "",
        _list_or_unspecified(limits),
        "",
        "## 课程证据不足的部分",
        "",
        _list_or_unspecified(method.insufficient_course_evidence),
        "",
        "## 来源证据",
        "",
        *evidence_lines,
        "",
    ]
    return "\n".join(sections)


def write_afeng_markdown(
    evidence_path: Path,
    method_path: Path,
    audit_path: Path,
    publication_path: Path,
    output_path: Path,
) -> Path:
    package = AfengEvidencePackage.model_validate(_load_json(evidence_path))
    method = AfengMethodDraft.model_validate(_load_json(method_path))
    audit = FidelityAudit.model_validate(_load_json(audit_path))
    publication = PublicationRecord.model_validate(_load_json(publication_path))
    return _write_new_or_same(
        Path(output_path), render_afeng_markdown(package, method, audit, publication)
    )


def export_afeng_schemas(output_dir: Path) -> list[Path]:
    models = (
        AfengEvidencePackage,
        AfengMethodDraft,
        FidelityAudit,
        PublicationRecord,
        ExternalPayload,
    )
    paths: list[Path] = []
    for model in models:
        path = Path(output_dir) / f"{model.__name__}.schema.json"
        atomic_write_text(path, json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2))
        paths.append(path)
    return paths


def parse_model(path: Path, model: type[BaseModel]) -> BaseModel:
    try:
        return model.model_validate(_load_json(path))
    except ValidationError as exc:
        raise ValueError(f"schema validation failed for {path}: {exc}") from exc
