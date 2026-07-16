"""Build an offline, release-gated Afeng document bundle for later Dify sync."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.afeng_models import (
    AfengMethodDraft,
    AfengRunManifest,
    FidelityAudit,
    PublicationClass,
    PublicationRecord,
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write_new_or_same(path: Path, content: str) -> None:
    if path.is_file():
        if path.read_text(encoding="utf-8") != content:
            raise FileExistsError(f"Dify bundle artifact already differs: {path}")
        return
    atomic_write_text(path, content)


def _safe_filename(knowledge_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", knowledge_id).strip("-.")
    if not value:
        raise ValueError("knowledge_id cannot produce an empty bundle filename")
    return value


def _require_artifact(manifest: AfengRunManifest, key: str) -> Path:
    value = manifest.artifact_paths.get(key)
    if not value:
        raise ValueError(f"published run is missing artifact path {key}: {manifest.case_id}")
    path = Path(value)
    if not path.is_file():
        raise FileNotFoundError(f"published run artifact does not exist: {path}")
    return path


def build_afeng_dify_bundle(
    model_run_summaries: Iterable[Path],
    output_dir: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    """Collect only fully released Afeng Markdown documents into an immutable bundle."""
    output_dir = Path(output_dir)
    documents: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, str]] = []
    for summary_path in model_run_summaries:
        summary_path = Path(summary_path)
        summary = _read_object(summary_path)
        for raw in summary.get("results") or []:
            run = AfengRunManifest.model_validate(raw)
            if run.status != "published":
                excluded.append(
                    {
                        "course_id": run.course_id,
                        "case_id": run.case_id,
                        "status": run.status,
                    }
                )
                continue
            method_path = _require_artifact(run, "approved_method")
            audit_path = _require_artifact(
                run, f"fidelity_audit_r{run.revision_count}"
            )
            publication_path = _require_artifact(run, "publication")
            markdown_path = _require_artifact(run, "markdown")
            method = AfengMethodDraft.model_validate(_read_object(method_path))
            audit = FidelityAudit.model_validate(_read_object(audit_path))
            publication = PublicationRecord.model_validate(_read_object(publication_path))
            identity = (run.course_id, run.case_id, run.knowledge_id)
            if identity != (method.course_id, method.case_id, method.knowledge_id):
                raise ValueError(f"approved method identity mismatch: {run.case_id}")
            if identity != (audit.course_id, audit.case_id, audit.knowledge_id):
                raise ValueError(f"fidelity audit identity mismatch: {run.case_id}")
            if identity != (
                publication.course_id,
                publication.case_id,
                publication.knowledge_id,
            ):
                raise ValueError(f"publication identity mismatch: {run.case_id}")
            if method.draft_fidelity_status != "reviewed":
                raise ValueError(f"method is not approved for release: {run.case_id}")
            if audit.audit_result != "pass" or not audit.release_allowed:
                raise ValueError(f"fidelity audit is not releasable: {run.case_id}")
            if (
                not publication.publishable
                or publication.publication_class == PublicationClass.REJECT
            ):
                raise ValueError(f"publication is not publishable: {run.case_id}")
            markdown = markdown_path.read_text(encoding="utf-8")
            digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
            filename = f"{_safe_filename(run.knowledge_id)}.md"
            target = output_dir / filename
            existing = documents.get(run.knowledge_id)
            if existing and existing["content_sha256"] != digest:
                raise ValueError(f"duplicate knowledge_id has different content: {run.knowledge_id}")
            _write_new_or_same(target, markdown)
            documents[run.knowledge_id] = {
                "knowledge_id": run.knowledge_id,
                "course_id": run.course_id,
                "case_id": run.case_id,
                "publication_class": publication.publication_class.value,
                "generalization_level": publication.generalization_level,
                "source_start_ms": method.source_time_range.start_ms,
                "source_end_ms": method.source_time_range.end_ms,
                "prompt_version": method.prompt_version,
                "pipeline_version": method.pipeline_version,
                "content_sha256": digest,
                "document_path": str(target.resolve()),
                "source_summary": str(summary_path.resolve()),
            }
    ordered = [documents[key] for key in sorted(documents)]
    payload = {
        "schema_version": "1.0",
        "bundle_type": "afeng_dify_release",
        "document_count": len(ordered),
        "excluded_count": len(excluded),
        "documents": ordered,
        "excluded": sorted(excluded, key=lambda item: (item["course_id"], item["case_id"])),
    }
    _write_new_or_same(
        Path(manifest_path), json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    return payload
