from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from course_video_analyzer.knowledge.afeng_dify import build_afeng_dify_bundle
from course_video_analyzer.knowledge.afeng_models import (
    AfengMethodDraft,
    AfengRunManifest,
    FidelityAudit,
    PublicationRecord,
)


def _write(path: Path, value: dict[str, Any] | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    path.write_text(content, encoding="utf-8")
    return path


def _draft() -> AfengMethodDraft:
    evidence = ["SEG-C001-000001"]
    return AfengMethodDraft.model_validate(
        {
            "knowledge_id": "KN-C001-001",
            "course_id": "C001",
            "case_id": "CASE-C001-001",
            "method_name": "示例方法",
            "problem_addressed": {"content": "示例问题", "evidence_ids": evidence},
            "course_perspective": {"content": "按照课程方法", "evidence_ids": evidence},
            "core_logic": {
                "content": "课程逻辑",
                "evidence_ids": evidence,
                "evidence_level": "explicit",
            },
            "course_reported_outcome": {
                "content": "",
                "evidence_ids": [],
                "evidence_level": "unknown",
            },
            "source_time_range": {"start_ms": 1000, "end_ms": 2500},
            "draft_fidelity_status": "reviewed",
        }
    )


def _audit() -> FidelityAudit:
    return FidelityAudit.model_validate(
        {
            "course_id": "C001",
            "case_id": "CASE-C001-001",
            "knowledge_id": "KN-C001-001",
            "audit_result": "pass",
            "fidelity_score": 98,
            "field_reviews": [
                {
                    "field": "method_draft",
                    "status": "supported",
                    "evidence_ids": ["SEG-C001-000001"],
                    "required_action": "keep",
                }
            ],
            "release_allowed": True,
        }
    )


def _publication() -> PublicationRecord:
    return PublicationRecord.model_validate(
        {
            "knowledge_id": "KN-C001-001",
            "course_id": "C001",
            "case_id": "CASE-C001-001",
            "publication_class": "case_derived_method",
            "generalization_level": "single_case",
            "classification_rationale": "单案例方法。",
            "evidence_ids": ["SEG-C001-000001"],
            "publishable": True,
        }
    )


def test_bundle_includes_published_and_excludes_manual_review(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    method_path = _write(artifacts / "method.json", _draft().model_dump(mode="json"))
    audit_path = _write(artifacts / "audit.json", _audit().model_dump(mode="json"))
    publication_path = _write(
        artifacts / "publication.json", _publication().model_dump(mode="json")
    )
    markdown_path = _write(
        artifacts / "KN-C001-001.md",
        "---\nknowledge_id: KN-C001-001\nfidelity_status: passed\n---\n# 示例方法\n",
    )
    published = AfengRunManifest(
        model="test",
        course_id="C001",
        case_id="CASE-C001-001",
        knowledge_id="KN-C001-001",
        input_hash="hash-1",
        status="published",
        artifact_paths={
            "approved_method": str(method_path),
            "fidelity_audit_r0": str(audit_path),
            "publication": str(publication_path),
            "markdown": str(markdown_path),
        },
    )
    manual = AfengRunManifest(
        model="test",
        course_id="C001",
        case_id="CASE-C001-002",
        knowledge_id="KN-C001-002",
        input_hash="hash-2",
        status="manual_review",
    )
    summary = _write(
        tmp_path / "summary.json",
        {"results": [published.model_dump(mode="json"), manual.model_dump(mode="json")]},
    )

    result = build_afeng_dify_bundle(
        [summary], tmp_path / "bundle" / "documents", tmp_path / "bundle" / "manifest.json"
    )

    assert result["document_count"] == 1
    assert result["excluded_count"] == 1
    document = result["documents"][0]
    # Canonical id overrides the model-authored knowledge id.
    assert document["knowledge_id"] == "AFENG-C001-CASE-C001-001"
    assert document["prompt_version"] == "mimo-method-v002"
    # Model lineage is recorded per document.
    assert document["model"] == "test"
    assert document["input_hash"] == "hash-1"
    assert document["source_summary"].endswith("summary.json")
    assert document["publication_class"] == "case_derived_method"
    assert len(document["content_sha256"]) == 64
    document_path = Path(document["document_path"])
    assert document_path.is_file()
    assert document_path.name == "AFENG-C001-CASE-C001-001.md"
    # The shipped markdown frontmatter carries the canonical id, not the model id.
    shipped = document_path.read_text(encoding="utf-8")
    assert 'knowledge_id: "AFENG-C001-CASE-C001-001"' in shipped
    assert "KN-C001-001" not in shipped
    assert result["excluded"][0]["status"] == "manual_review"


def test_bundle_canonicalizes_model_authored_identity(tmp_path: Path) -> None:
    """A model that emits a non-canonical knowledge id still publishes under the canonical id."""
    artifacts = tmp_path / "artifacts"
    draft = _draft().model_copy(update={"knowledge_id": "mimo-junk-C001-001"})
    audit = _audit().model_copy(update={"knowledge_id": "mimo-junk-C001-001"})
    publication = _publication().model_copy(update={"knowledge_id": "mimo-junk-C001-001"})
    method_path = _write(artifacts / "method.json", draft.model_dump(mode="json"))
    audit_path = _write(artifacts / "audit.json", audit.model_dump(mode="json"))
    publication_path = _write(artifacts / "publication.json", publication.model_dump(mode="json"))
    markdown_path = _write(
        artifacts / "mimo-junk-C001-001.md",
        '---\nknowledge_id: "mimo-junk-C001-001"\nfidelity_status: passed\n---\n# 示例方法\n',
    )
    # The run manifest also carries the model-authored id; the bundle must ignore it.
    published = AfengRunManifest(
        model="mimo-v2.5-pro",
        course_id="C001",
        case_id="CASE-C001-001",
        knowledge_id="mimo-junk-C001-001",
        input_hash="hash-1",
        status="published",
        artifact_paths={
            "approved_method": str(method_path),
            "fidelity_audit_r0": str(audit_path),
            "publication": str(publication_path),
            "markdown": str(markdown_path),
        },
    )
    summary = _write(
        tmp_path / "summary.json",
        {"results": [published.model_dump(mode="json")]},
    )

    result = build_afeng_dify_bundle(
        [summary], tmp_path / "bundle" / "documents", tmp_path / "bundle" / "manifest.json"
    )

    assert result["document_count"] == 1
    document = result["documents"][0]
    assert document["knowledge_id"] == "AFENG-C001-CASE-C001-001"
    assert document["model"] == "mimo-v2.5-pro"
    shipped = Path(document["document_path"]).read_text(encoding="utf-8")
    assert 'knowledge_id: "AFENG-C001-CASE-C001-001"' in shipped
    assert "mimo-junk" not in shipped
    # Original model artifacts are untouched.
    assert json.loads(method_path.read_text(encoding="utf-8"))["knowledge_id"] == "mimo-junk-C001-001"


def test_bundle_rejects_duplicate_canonical_id_with_different_content(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    method_path = _write(artifacts / "method.json", _draft().model_dump(mode="json"))
    audit_path = _write(artifacts / "audit.json", _audit().model_dump(mode="json"))
    publication_path = _write(artifacts / "publication.json", _publication().model_dump(mode="json"))
    markdown_a = _write(
        artifacts / "a.md",
        "---\nknowledge_id: KN-A\nfidelity_status: passed\n---\n# 示例方法 A\n",
    )
    markdown_b = _write(
        artifacts / "b.md",
        "---\nknowledge_id: KN-B\nfidelity_status: passed\n---\n# 示例方法 B\n",
    )
    run_a = AfengRunManifest(
        model="test",
        course_id="C001",
        case_id="CASE-C001-001",
        knowledge_id="KN-A",
        input_hash="hash-a",
        status="published",
        artifact_paths={
            "approved_method": str(method_path),
            "fidelity_audit_r0": str(audit_path),
            "publication": str(publication_path),
            "markdown": str(markdown_a),
        },
    )
    run_b = AfengRunManifest(
        model="test",
        course_id="C001",
        case_id="CASE-C001-001",
        knowledge_id="KN-B",
        input_hash="hash-b",
        status="published",
        artifact_paths={
            "approved_method": str(method_path),
            "fidelity_audit_r0": str(audit_path),
            "publication": str(publication_path),
            "markdown": str(markdown_b),
        },
    )
    summary = _write(
        tmp_path / "summary.json",
        {"results": [run_a.model_dump(mode="json"), run_b.model_dump(mode="json")]},
    )

    with pytest.raises(ValueError, match="duplicate canonical knowledge_id"):
        build_afeng_dify_bundle(
            [summary], tmp_path / "bundle" / "documents", tmp_path / "bundle" / "manifest.json"
        )
