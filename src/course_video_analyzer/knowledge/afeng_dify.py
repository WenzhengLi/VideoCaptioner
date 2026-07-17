"""Build an offline, release-gated Afeng document bundle for later Dify sync."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.afeng import (
    canonical_knowledge_id,
    normalize_fidelity_audit_knowledge_id,
    normalize_method_knowledge_id,
    normalize_publication_knowledge_id,
)
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


_RUN_TOKEN_TAIL = re.compile(r"[0-9a-f]{12}$")


def _extract_run_token(manifest: AfengRunManifest) -> str:
    """Recover the 12-hex run token embedded in artifact filenames.

    The run token ties a published document to the exact pipeline run that
    produced it. It is not stored as a manifest field, so it is recovered from
    the approved-method / publication artifact path stems.
    """
    for key in (
        "approved_method",
        "publication",
        "method_draft_r0",
        "fidelity_audit_r0",
        "markdown",
    ):
        value = manifest.artifact_paths.get(key) or ""
        stem = Path(value).stem
        match = _RUN_TOKEN_TAIL.search(stem)
        if match:
            return match.group(0)
    return ""


_KNOWLEDGE_ID_QUOTED_LINE = re.compile(r'(?m)^knowledge_id:\s*"[^"]*"\s*$')
_KNOWLEDGE_ID_BARE_LINE = re.compile(r"(?m)^knowledge_id:\s*\S+\s*$")


def _canonicalize_markdown(text: str, canonical_id: str) -> str:
    """Override the YAML frontmatter knowledge_id with the canonical value.

    The rendered body never references knowledge_id, so replacing only the
    frontmatter field is sufficient and avoids re-rendering from the evidence
    package (which the bundle builder does not load). This is the deterministic
    migration path for historical model-authored knowledge IDs.
    """
    if not text.startswith("---"):
        raise ValueError("afeng markdown must start with YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("afeng markdown has unclosed YAML frontmatter")
    frontmatter = parts[1]
    replacement = f'knowledge_id: "{canonical_id}"'
    new_frontmatter, count = _KNOWLEDGE_ID_QUOTED_LINE.subn(replacement, frontmatter, count=1)
    if count == 0:
        new_frontmatter, count = _KNOWLEDGE_ID_BARE_LINE.subn(replacement, frontmatter, count=1)
    if count == 0:
        raise ValueError("afeng markdown frontmatter has no knowledge_id field")
    return "---" + new_frontmatter + "---" + parts[2]


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
    """Collect only fully released Afeng Markdown documents into an immutable bundle.

    Each published document is re-identified under the program-controlled
    canonical knowledge id ``AFENG-{course_id}-{case_id}``, regardless of what
    the model wrote. Model lineage (model, run token, input hash, source
    summary) is recorded per document so MiMo- and GLM-sourced documents are
    distinguishable. Historical model artifacts are read only; they are never
    modified.
    """
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
            canonical_id = canonical_knowledge_id(run.course_id, run.case_id)
            method_path = _require_artifact(run, "approved_method")
            audit_path = _require_artifact(run, f"fidelity_audit_r{run.revision_count}")
            publication_path = _require_artifact(run, "publication")
            markdown_path = _require_artifact(run, "markdown")
            method = normalize_method_knowledge_id(
                AfengMethodDraft.model_validate(_read_object(method_path))
            )
            audit = normalize_fidelity_audit_knowledge_id(
                FidelityAudit.model_validate(_read_object(audit_path))
            )
            publication = normalize_publication_knowledge_id(
                PublicationRecord.model_validate(_read_object(publication_path))
            )
            for artifact, name in (
                (method, "approved_method"),
                (audit, "fidelity_audit"),
                (publication, "publication"),
            ):
                if (artifact.course_id, artifact.case_id) != (run.course_id, run.case_id):
                    raise ValueError(f"{name} course/case mismatch: {run.case_id}")
                if artifact.knowledge_id != canonical_id:
                    raise ValueError(f"{name} knowledge_id is not canonical: {run.case_id}")
            if method.draft_fidelity_status != "reviewed":
                raise ValueError(f"method is not approved for release: {run.case_id}")
            if audit.audit_result != "pass" or not audit.release_allowed:
                raise ValueError(f"fidelity audit is not releasable: {run.case_id}")
            if (
                not publication.publishable
                or publication.publication_class == PublicationClass.REJECT
            ):
                raise ValueError(f"publication is not publishable: {run.case_id}")
            markdown = _canonicalize_markdown(
                markdown_path.read_text(encoding="utf-8"), canonical_id
            )
            digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
            filename = f"{_safe_filename(canonical_id)}.md"
            target = output_dir / filename
            existing = documents.get(canonical_id)
            if existing and existing["content_sha256"] != digest:
                raise ValueError(
                    f"duplicate canonical knowledge_id has different content: {canonical_id}"
                )
            _write_new_or_same(target, markdown)
            documents[canonical_id] = {
                "knowledge_id": canonical_id,
                "course_id": run.course_id,
                "case_id": run.case_id,
                "model": run.model,
                "run_token": _extract_run_token(run),
                "input_hash": run.input_hash,
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
