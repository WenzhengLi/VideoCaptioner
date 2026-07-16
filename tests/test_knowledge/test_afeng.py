from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from course_video_analyzer.knowledge.afeng import (
    approve_method,
    build_afeng_evidence_package,
    build_external_payload,
    render_afeng_markdown,
    validate_evidence_package,
    validate_fidelity_audit,
    validate_method_draft,
)
from course_video_analyzer.knowledge.afeng_models import (
    AfengEvidencePackage,
    AfengMethodDraft,
    FidelityAudit,
    PublicationRecord,
)
from course_video_analyzer.knowledge.afeng_pipeline import run_afeng_method_pipeline


def _write(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _build_package(tmp_path: Path, *, text: str = "按照课程方法先确认当前信号。") -> AfengEvidencePackage:
    case_input = {
        "schema_version": "1.0",
        "prompt_version": "knowledge-v003-p04-input",
        "course_id": "C001",
        "case": {"case_id": "CASE-C001-001", "title": "示例案例"},
        "segments": [
            {
                "segment_id": "SEG-C001-000001",
                "start_ms": 1000,
                "end_ms": 2500,
                "speaker": "speaker_0",
                "content_type": "speech",
                "source_role": "instructor_explanation",
                "epistemic_type": "instructor_claim",
                "text": text,
            }
        ],
    }
    p04 = {
        "schema_version": "1.0",
        "prompt_version": "knowledge-v003-p04",
        "course_id": "C001",
        "case_id": "CASE-C001-001",
        "case_title": "示例案例",
        "summary": "讲师说明了一个处理顺序。",
        "observations": [],
        "instructor_claims": [
            {
                "id": "CLM-001",
                "text": "课程主张先确认信号。",
                "evidence_segment_ids": ["SEG-C001-000001"],
            }
        ],
        "alternative_explanations": [],
        "outcomes": [],
        "quoted_expressions": [],
        "uncertainties": [],
    }
    p05 = {
        "evidence_reviews": [
            {
                "target_type": "instructor_claim",
                "target_id": "CLM-001",
                "status": "supported",
                "supported_by_segment_ids": ["SEG-C001-000001"],
                "note": "原文支持。",
            }
        ],
        "missing_context": [],
        "required_corrections": [],
        "safety_flags": [{"type": "must_not_leak"}],
        "unsafe_recommendation_candidates": [{"text": "must_not_leak"}],
    }
    source = {"title": "第一课"}
    output = tmp_path / "evidence.json"
    build_afeng_evidence_package(
        "C001",
        "CASE-C001-001",
        _write(tmp_path / "case-input.json", case_input),
        _write(tmp_path / "p04.json", p04),
        output,
        p05_path=_write(tmp_path / "p05.json", p05),
        source_path=_write(tmp_path / "source.json", source),
    )
    return AfengEvidencePackage.model_validate_json(output.read_text(encoding="utf-8"))


def _draft(status: str = "pending_review") -> dict[str, Any]:
    evidence = ["SEG-C001-000001"]
    return {
        "schema_version": "1.0",
        "pipeline_version": "afeng-method-v001",
        "prompt_version": "mimo-method-v001",
        "knowledge_id": "AFENG-C001-CASE-C001-001",
        "course_id": "C001",
        "case_id": "CASE-C001-001",
        "method_name": "先确认信号",
        "problem_addressed": {"content": "处理当前信号。", "evidence_ids": evidence},
        "course_perspective": {
            "content": "按照课程方法，应先确认当前信号。",
            "evidence_ids": evidence,
        },
        "applicable_conditions": [],
        "not_applicable_conditions": [],
        "core_logic": {
            "content": "课程将第一步概括为确认信号。",
            "evidence_ids": evidence,
            "evidence_level": "explicit",
        },
        "steps": [
            {
                "order": 1,
                "action": "确认当前信号",
                "purpose_according_to_course": "确定后续处理",
                "evidence_ids": evidence,
            }
        ],
        "signals_used_by_course": [],
        "example_expressions": [],
        "course_reported_outcome": {
            "content": "",
            "evidence_ids": [],
            "evidence_level": "unknown",
        },
        "course_stated_limits": [],
        "insufficient_course_evidence": ["课程未说明其他条件。"],
        "source_time_range": {"start_ms": 1000, "end_ms": 2500},
        "draft_fidelity_status": status,
    }


def _audit(result: str, revision: int = 0) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "pipeline_version": "afeng-method-v001",
        "prompt_version": "mimo-method-v001",
        "course_id": "C001",
        "case_id": "CASE-C001-001",
        "knowledge_id": "AFENG-C001-CASE-C001-001",
        "revision_number": revision,
        "audit_result": result,
        "fidelity_score": 95 if result == "pass" else 70,
        "field_reviews": [
            {
                "field": "core_logic",
                "status": "supported" if result == "pass" else "partially_supported",
                "issue": "" if result == "pass" else "需要重新归属。",
                "evidence_ids": ["SEG-C001-000001"],
                "required_action": "keep" if result == "pass" else "reattribute",
            }
        ],
        "unsupported_additions": [],
        "misattributed_claims": [],
        "missing_course_conditions": [],
        "invalid_evidence_ids": [],
        "external_knowledge_detected": [],
        "revision_instructions": [] if result == "pass" else ["使用课程归属表达。"],
        "release_allowed": result == "pass",
    }


def _publication() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "pipeline_version": "afeng-method-v001",
        "prompt_version": "mimo-method-v001",
        "knowledge_id": "AFENG-C001-CASE-C001-001",
        "course_id": "C001",
        "case_id": "CASE-C001-001",
        "publication_class": "case_derived_method",
        "generalization_level": "single_case",
        "classification_rationale": "该方法来自单个案例。",
        "evidence_ids": ["SEG-C001-000001"],
        "publishable": True,
    }


def test_evidence_builder_uses_only_evidence_fields_from_p05(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    dumped = package.model_dump_json()
    assert package.course_title == "第一课"
    assert package.source_time_range.start_ms == 1000
    assert package.statements[0].evidence_status.value == "supported"
    assert "must_not_leak" not in dumped
    assert "safety_flags" not in dumped
    assert "unsafe_recommendation_candidates" not in dumped
    assert validate_evidence_package(package)["status"] == "pass"


def test_evidence_hash_detects_tampering(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    tampered = package.model_copy(update={"course_title": "被修改"})
    report = validate_evidence_package(tampered)
    assert report["status"] == "needs_review"
    assert report["checks"]["input_hash"] is False


def test_external_payload_redacts_deterministic_pii(tmp_path: Path) -> None:
    package = _build_package(tmp_path, text="微信号 abcdef12，手机号 13800138000")
    payload = build_external_payload(package)
    serialized = json.dumps(payload.redacted_package, ensure_ascii=False)
    assert payload.external_payload_safe is True
    assert "13800138000" not in serialized
    assert "abcdef12" not in serialized
    assert {item.kind for item in payload.pii_findings} == {"mainland_phone", "wechat_id"}


def test_draft_audit_and_markdown_release_gate(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    draft = AfengMethodDraft.model_validate(_draft())
    assert validate_method_draft(package, draft)["status"] == "pass"
    audit = FidelityAudit.model_validate(_audit("pass"))
    assert validate_fidelity_audit(package, draft, audit)["status"] == "pass"
    approved = approve_method(draft, audit)
    publication = PublicationRecord.model_validate(_publication())
    markdown = render_afeng_markdown(package, approved, audit, publication)
    assert 'publication_class: "case_derived_method"' in markdown
    assert "按照课程方法" in markdown
    assert "SEG-C001-000001" in markdown


def test_audit_cannot_release_when_not_passed() -> None:
    value = _audit("revise")
    value["release_allowed"] = True
    with pytest.raises(ValidationError):
        FidelityAudit.model_validate(value)


def test_every_nonempty_method_element_requires_evidence(tmp_path: Path) -> None:
    package = _build_package(tmp_path)
    value = _draft()
    value["signals_used_by_course"] = [
        {"signal": "某信号", "course_interpretation": "某解释", "evidence_ids": []}
    ]
    draft = AfengMethodDraft.model_validate(value)
    report = validate_method_draft(package, draft)
    assert report["status"] == "needs_review"
    assert "signals_used_by_course[0]" in report["missing_core_evidence"]


class _ScriptedExecutor:
    model_name = "scripted-test"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.audit_calls = 0

    def execute(self, stage: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(stage)
        if stage == "extract_method":
            return _draft()
        if stage == "audit_fidelity":
            result = "revise" if self.audit_calls == 0 else "pass"
            output = _audit(result, self.audit_calls)
            self.audit_calls += 1
            return output
        if stage == "revise":
            return _draft()
        if stage == "classify_publication":
            return _publication()
        raise AssertionError(stage)


def test_pipeline_revises_once_and_reuses_completed_run(tmp_path: Path) -> None:
    package = _build_package(tmp_path / "input")
    evidence_path = tmp_path / "input" / "evidence.json"
    evidence_path.write_text(package.model_dump_json(indent=2), encoding="utf-8")
    executor = _ScriptedExecutor()
    manifest = run_afeng_method_pipeline(evidence_path, tmp_path / "course", executor)
    assert manifest.status == "published"
    assert manifest.revision_count == 1
    assert executor.calls == [
        "extract_method",
        "audit_fidelity",
        "revise",
        "audit_fidelity",
        "classify_publication",
    ]
    second_executor = _ScriptedExecutor()
    cached = run_afeng_method_pipeline(evidence_path, tmp_path / "course", second_executor)
    assert cached.status == "published"
    assert second_executor.calls == []
