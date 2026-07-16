from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    assert result["documents"][0]["knowledge_id"] == "KN-C001-001"
    assert result["documents"][0]["prompt_version"] == "mimo-method-v002"
    assert Path(result["documents"][0]["document_path"]).is_file()
    assert result["excluded"][0]["status"] == "manual_review"
