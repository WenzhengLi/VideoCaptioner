"""Resumable three-stage Afeng method production state machine."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.afeng import (
    PROMPT_VERSION,
    approve_method,
    build_external_payload,
    cache_key,
    canonical_knowledge_id,
    content_hash,
    normalize_method_evidence_id_aliases,
    normalize_method_knowledge_id,
    normalize_method_source_time_range,
    normalize_publication_knowledge_id,
    normalize_unbacked_method_conditions,
    render_afeng_markdown,
    validate_evidence_package,
    validate_fidelity_audit,
    validate_method_draft,
    validate_publication,
    iter_method_evidence_ids,
)
from course_video_analyzer.knowledge.afeng_models import (
    AfengEvidencePackage,
    AfengMethodDraft,
    AfengRunEvent,
    AfengRunManifest,
    AfengStage,
    ExternalSegmentProfile,
    FidelityAudit,
    FidelityFieldReview,
    PublicationRecord,
)


class AfengStageExecutor(Protocol):
    """Adapter boundary for MiMo, another API model, or a deterministic test double."""

    @property
    def model_name(self) -> str: ...

    def execute(
        self, stage: str, payload: dict[str, Any]
    ) -> dict[str, Any] | "StageExecutionResult": ...


@dataclass(frozen=True)
class StageExecutionResult:
    output: dict[str, Any]
    metadata: dict[str, Any]


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"artifact root must be an object: {path}")
    return value


def _artifact(
    executor: AfengStageExecutor,
    stage: AfengStage,
    payload: dict[str, Any],
    path: Path,
    *,
    revision_number: int = 0,
) -> tuple[dict[str, Any], AfengRunEvent]:
    input_digest = content_hash(payload)
    started = time.monotonic()
    if path.is_file():
        output = _read_object(path)
        return output, AfengRunEvent(
            stage=stage,
            status="cached",
            revision_number=revision_number,
            input_hash=input_digest,
            output_hash=content_hash(output),
            duration_ms=0,
        )
    response = executor.execute(stage, payload)
    metadata: dict[str, Any] = {}
    if isinstance(response, StageExecutionResult):
        output = response.output
        metadata = response.metadata
    else:
        output = response
    if not isinstance(output, dict):
        raise ValueError(f"stage {stage} did not return a JSON object")
    atomic_write_text(path, json.dumps(output, ensure_ascii=False, indent=2))
    return output, AfengRunEvent(
        stage=stage,
        status="completed",
        revision_number=revision_number,
        input_hash=input_digest,
        output_hash=content_hash(output),
        duration_ms=int((time.monotonic() - started) * 1000),
        model_metadata=metadata,
    )


def _write_manifest(path: Path, manifest: AfengRunManifest) -> None:
    atomic_write_text(path, manifest.model_dump_json(indent=2))


def _load_and_normalize_method_draft(
    package: AfengEvidencePackage, data: dict[str, Any], path: Path
) -> AfengMethodDraft:
    """Validate model output and persist deterministic fields calculated from evidence."""
    draft = AfengMethodDraft.model_validate(data)
    normalized = normalize_unbacked_method_conditions(draft)
    normalized = normalize_method_evidence_id_aliases(package, normalized)
    normalized = normalize_method_source_time_range(package, normalized)
    normalized = normalize_method_knowledge_id(normalized)
    if normalized != draft:
        atomic_write_text(path, normalized.model_dump_json(indent=2))
    return normalized


def _load_and_normalize_fidelity_audit(
    data: dict[str, Any], path: Path, revision_number: int, draft: AfengMethodDraft
) -> FidelityAudit:
    """Persist the orchestrator-owned revision number instead of model bookkeeping."""
    audit = FidelityAudit.model_validate(data)
    invalid_ids = [
        item
        for item in audit.invalid_evidence_ids
        if item.startswith("SEG-") and not any(character.isspace() for character in item)
    ]
    field_reviews = list(audit.field_reviews)
    if audit.audit_result == "pass" and not field_reviews:
        field_reviews.append(
            FidelityFieldReview(
                field="method_draft",
                status="supported",
                issue="",
                evidence_ids=list(dict.fromkeys(iter_method_evidence_ids(draft))),
                required_action="keep",
            )
        )
    normalized = audit.model_copy(
        update={
            "revision_number": revision_number,
            "invalid_evidence_ids": invalid_ids,
            "field_reviews": field_reviews,
            "knowledge_id": canonical_knowledge_id(audit.course_id, audit.case_id),
        }
    )
    if normalized != audit:
        atomic_write_text(path, normalized.model_dump_json(indent=2))
    return normalized


def run_afeng_method_pipeline(
    evidence_path: Path,
    course_dir: Path,
    executor: AfengStageExecutor,
    *,
    max_revisions: int = 2,
    external_segment_profile: ExternalSegmentProfile = "evidence_focused",
    external_context_window: int = 1,
) -> AfengRunManifest:
    """Run extraction, fidelity audit, publication classification, and rendering.

    The renderer is deterministic. Model stages receive only the redacted external payload.
    Existing valid artifacts are reused, making retries resumable without repeated model calls.
    """
    if not 0 <= max_revisions <= 2:
        raise ValueError("max_revisions must be between 0 and 2")
    package = AfengEvidencePackage.model_validate(_read_object(Path(evidence_path)))
    evidence_report = validate_evidence_package(package)
    if evidence_report["status"] != "pass":
        raise ValueError(f"evidence package failed deterministic QA: {evidence_report}")
    external = build_external_payload(
        package,
        segment_profile=external_segment_profile,
        context_window=external_context_window,
    )
    if not external.external_payload_safe:
        raise ValueError("evidence package could not be safely redacted for an external model")

    root = Path(course_dir) / "06_afeng_methods"
    draft_dir = root / "method-draft-v001"
    audit_dir = root / "fidelity-audit-v001"
    approved_dir = root / "approved-v001"
    publication_dir = root / "publication-v001"
    markdown_dir = root / "markdown-v001"
    run_dir = root / "runs"
    for directory in (draft_dir, audit_dir, approved_dir, publication_dir, markdown_dir, run_dir):
        directory.mkdir(parents=True, exist_ok=True)

    run_token = content_hash(
        {
            "input_hash": package.input_hash,
            "prompt_version": PROMPT_VERSION,
            "model": executor.model_name,
            "external_segment_profile": external_segment_profile,
            "external_context_window": external_context_window,
            "selected_evidence_ids_hash": external.selected_evidence_ids_hash,
        }
    )[:12]
    run_path = run_dir / f"{package.case_id}-{run_token}.json"
    initial_knowledge_id = canonical_knowledge_id(package.course_id, package.case_id)
    manifest = AfengRunManifest(
        model=executor.model_name,
        course_id=package.course_id,
        case_id=package.case_id,
        knowledge_id=initial_knowledge_id,
        input_hash=package.input_hash,
        status="running",
        artifact_paths={"evidence_package": str(Path(evidence_path).resolve())},
    )
    if run_path.is_file():
        previous = AfengRunManifest.model_validate(_read_object(run_path))
        if (
            previous.input_hash == package.input_hash
            and previous.model == executor.model_name
            and previous.status in {"published", "rejected", "manual_review"}
        ):
            return previous
        if previous.input_hash == package.input_hash and previous.model == executor.model_name:
            manifest = manifest.model_copy(
                update={
                    "knowledge_id": previous.knowledge_id,
                    "events": list(previous.events),
                    "artifact_paths": {
                        **previous.artifact_paths,
                        "evidence_package": str(Path(evidence_path).resolve()),
                    },
                }
            )
    _write_manifest(run_path, manifest)
    current_stage: AfengStage = "extract_method"
    current_revision = 0
    model_input_hash = content_hash(
        {
            "source_input_hash": package.input_hash,
            "segment_profile": external.segment_profile,
            "selected_evidence_ids_hash": external.selected_evidence_ids_hash,
        }
    )

    try:
        draft_payload = {
            "prompt_version": PROMPT_VERSION,
            "cache_key": cache_key(
                model_input_hash, PROMPT_VERSION, executor.model_name, "extract_method"
            ),
            "evidence_package": external.redacted_package,
        }
        draft_data, event = _artifact(
            executor,
            "extract_method",
            draft_payload,
            draft_dir / f"{package.case_id}-{run_token}-r0.json",
        )
        manifest.events.append(event)
        manifest.artifact_paths["method_draft_r0"] = str(
            draft_dir / f"{package.case_id}-{run_token}-r0.json"
        )
        draft = _load_and_normalize_method_draft(
            package,
            draft_data,
            draft_dir / f"{package.case_id}-{run_token}-r0.json",
        )
        manifest.knowledge_id = canonical_knowledge_id(package.course_id, package.case_id)
        draft_report = validate_method_draft(package, draft)
        if draft_report["status"] != "pass":
            raise ValueError(f"method draft failed deterministic QA: {draft_report}")

        audit: FidelityAudit | None = None
        revision_number = 0
        while True:
            current_stage = "audit_fidelity"
            current_revision = revision_number
            audit_payload = {
                "prompt_version": PROMPT_VERSION,
                "revision_number": revision_number,
                "evidence_package": external.redacted_package,
                "method_draft": draft.model_dump(mode="json"),
            }
            audit_data, event = _artifact(
                executor,
                "audit_fidelity",
                audit_payload,
                audit_dir / f"{package.case_id}-{run_token}-r{revision_number}.json",
                revision_number=revision_number,
            )
            manifest.events.append(event)
            manifest.artifact_paths[f"fidelity_audit_r{revision_number}"] = str(
                audit_dir / f"{package.case_id}-{run_token}-r{revision_number}.json"
            )
            audit = _load_and_normalize_fidelity_audit(
                audit_data,
                audit_dir / f"{package.case_id}-{run_token}-r{revision_number}.json",
                revision_number,
                draft,
            )
            audit_report = validate_fidelity_audit(
                package,
                draft,
                audit,
                expected_revision_number=revision_number,
            )
            if audit_report["status"] != "pass":
                raise ValueError(f"fidelity audit failed deterministic QA: {audit_report}")
            if audit.audit_result == "pass":
                break
            if audit.audit_result == "reject":
                manifest.status = "rejected"
                manifest.revision_count = revision_number
                _write_manifest(run_path, manifest)
                return manifest
            if revision_number >= max_revisions:
                manifest.status = "manual_review"
                manifest.revision_count = revision_number
                _write_manifest(run_path, manifest)
                return manifest
            revision_number += 1
            current_stage = "revise"
            current_revision = revision_number
            revision_payload = {
                "prompt_version": PROMPT_VERSION,
                "revision_number": revision_number,
                "evidence_package": external.redacted_package,
                "method_draft": draft.model_dump(mode="json"),
                "fidelity_audit": audit.model_dump(mode="json"),
            }
            revised_data, event = _artifact(
                executor,
                "revise",
                revision_payload,
                draft_dir / f"{package.case_id}-{run_token}-r{revision_number}.json",
                revision_number=revision_number,
            )
            manifest.events.append(event)
            manifest.artifact_paths[f"method_draft_r{revision_number}"] = str(
                draft_dir / f"{package.case_id}-{run_token}-r{revision_number}.json"
            )
            draft = _load_and_normalize_method_draft(
                package,
                revised_data,
                draft_dir / f"{package.case_id}-{run_token}-r{revision_number}.json",
            )
            draft_report = validate_method_draft(package, draft)
            if draft_report["status"] != "pass":
                raise ValueError(f"revised method failed deterministic QA: {draft_report}")

        if audit is None:
            raise RuntimeError("fidelity audit was not executed")
        approved = approve_method(draft, audit)
        approved_path = approved_dir / f"{package.case_id}-{run_token}.json"
        if not approved_path.exists():
            atomic_write_text(approved_path, approved.model_dump_json(indent=2))
        manifest.artifact_paths["approved_method"] = str(approved_path)

        current_stage = "classify_publication"
        current_revision = revision_number
        classification_payload = {
            "prompt_version": PROMPT_VERSION,
            "evidence_package": external.redacted_package,
            "approved_method": approved.model_dump(mode="json"),
            "fidelity_audit": audit.model_dump(mode="json"),
        }
        publication_data, event = _artifact(
            executor,
            "classify_publication",
            classification_payload,
            publication_dir / f"{package.case_id}-{run_token}.json",
            revision_number=revision_number,
        )
        manifest.events.append(event)
        publication_raw = PublicationRecord.model_validate(publication_data)
        publication = normalize_publication_knowledge_id(publication_raw)
        if publication != publication_raw:
            atomic_write_text(
                publication_dir / f"{package.case_id}-{run_token}.json",
                publication.model_dump_json(indent=2),
            )
        validate_publication(package, approved, audit, publication)
        manifest.artifact_paths["publication"] = str(
            publication_dir / f"{package.case_id}-{run_token}.json"
        )
        if not publication.publishable:
            manifest.status = "rejected"
            manifest.revision_count = revision_number
            _write_manifest(run_path, manifest)
            return manifest

        current_stage = "render_markdown"
        markdown_path = markdown_dir / f"{approved.knowledge_id}-{run_token}.md"
        markdown = render_afeng_markdown(package, approved, audit, publication)
        markdown_existed = markdown_path.exists()
        if not markdown_existed:
            atomic_write_text(markdown_path, markdown)
        manifest.events.append(
            AfengRunEvent(
                stage="render_markdown",
                status="cached" if markdown_existed else "completed",
                revision_number=revision_number,
                input_hash=content_hash(publication.model_dump(mode="json")),
                output_hash=content_hash(markdown),
            )
        )
        manifest.artifact_paths["markdown"] = str(markdown_path)
        manifest.status = "published"
        manifest.revision_count = revision_number
        _write_manifest(run_path, manifest)
        return manifest
    except Exception as exc:
        manifest.status = "failed"
        manifest.events.append(
            AfengRunEvent(
                stage=current_stage,
                status="failed",
                revision_number=current_revision,
                input_hash=package.input_hash,
                error=str(exc),
            )
        )
        _write_manifest(run_path, manifest)
        raise
