"""Versioned contracts for the Afeng course-method layer."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EvidenceStatementType = Literal[
    "observation",
    "instructor_claim",
    "alternative_explanation",
    "claimed_outcome",
    "quoted_expression",
]
AfengStage = Literal[
    "extract_method", "audit_fidelity", "revise", "classify_publication", "render_markdown"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RightsStatus(str, Enum):
    RESEARCH_ONLY = "research_only"
    AUTHORIZED = "authorized"


class EvidenceStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    NOT_REVIEWED = "not_reviewed"


class PublicationClass(str, Enum):
    VERIFIED_METHOD = "verified_method"
    CASE_DERIVED_METHOD = "case_derived_method"
    COURSE_CLAIM = "course_claim"
    REPORTED_OUTCOME = "reported_outcome"
    PARTIAL_METHOD = "partial_method"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REJECT = "reject"


class SourceTimeRange(StrictModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> "SourceTimeRange":
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be greater than or equal to start_ms")
        return self


class EvidenceSegment(StrictModel):
    evidence_id: str
    segment_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    source_type: str
    speaker_role: str
    epistemic_type: str = "unknown"
    raw_text: str | None = None
    normalized_text: str


class EvidenceStatement(StrictModel):
    statement_id: str
    statement_type: EvidenceStatementType
    text: str
    evidence_ids: list[str]
    evidence_status: EvidenceStatus = EvidenceStatus.NOT_REVIEWED
    review_note: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class EvidenceReview(StrictModel):
    target_type: str
    target_id: str
    status: EvidenceStatus
    evidence_ids: list[str]
    note: str = ""


class SourceWarning(StrictModel):
    warning_type: Literal["uncertainty", "missing_context", "required_correction"]
    field: str = ""
    target_type: str = ""
    target_id: str = ""
    action: str = ""
    note: str
    evidence_ids: list[str] = Field(default_factory=list)


class AfengEvidencePackage(StrictModel):
    schema_version: str = "1.0"
    pipeline_version: str = "afeng-method-v001"
    prompt_version: str = "mimo-method-v001"
    source_pipeline_version: str
    course_id: str
    course_title: str = ""
    case_id: str
    case_title: str = ""
    case_summary: str = ""
    rights_status: RightsStatus = RightsStatus.RESEARCH_ONLY
    course_context: str = ""
    source_time_range: SourceTimeRange
    segments: list[EvidenceSegment]
    statements: list[EvidenceStatement]
    evidence_reviews: list[EvidenceReview] = Field(default_factory=list)
    source_warnings: list[SourceWarning] = Field(default_factory=list)
    input_hash: str


class SupportedText(StrictModel):
    content: str
    evidence_ids: list[str]


class SupportedCondition(StrictModel):
    condition: str
    evidence_ids: list[str]


class MethodLogic(StrictModel):
    content: str
    evidence_ids: list[str]
    evidence_level: Literal["explicit", "direct_summary", "insufficient"]


class MethodStep(StrictModel):
    order: int = Field(ge=1)
    action: str
    purpose_according_to_course: str = ""
    evidence_ids: list[str]


class CourseSignal(StrictModel):
    signal: str
    course_interpretation: str
    evidence_ids: list[str]


class ExampleExpression(StrictModel):
    text: str
    source: Literal["course_quote", "direct_adaptation", "course_combination"]
    evidence_ids: list[str]


class ReportedOutcome(StrictModel):
    content: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_level: Literal["observed", "instructor_claimed", "unknown"] = "unknown"


class AfengMethodDraft(StrictModel):
    schema_version: str = "1.0"
    pipeline_version: str = "afeng-method-v001"
    prompt_version: str = "mimo-method-v001"
    knowledge_id: str
    course_id: str
    case_id: str
    method_name: str
    problem_addressed: SupportedText
    course_perspective: SupportedText
    applicable_conditions: list[SupportedCondition] = Field(default_factory=list)
    not_applicable_conditions: list[SupportedCondition] = Field(default_factory=list)
    core_logic: MethodLogic
    steps: list[MethodStep] = Field(default_factory=list)
    signals_used_by_course: list[CourseSignal] = Field(default_factory=list)
    example_expressions: list[ExampleExpression] = Field(default_factory=list)
    course_reported_outcome: ReportedOutcome = Field(default_factory=ReportedOutcome)
    course_stated_limits: list[SupportedText] = Field(default_factory=list)
    insufficient_course_evidence: list[str] = Field(default_factory=list)
    source_time_range: SourceTimeRange
    draft_fidelity_status: Literal["pending_review", "reviewed"] = "pending_review"


class FidelityFieldReview(StrictModel):
    field: str
    status: Literal[
        "supported",
        "partially_supported",
        "unsupported",
        "misattributed",
        "missing_condition",
    ]
    issue: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    required_action: Literal[
        "keep", "delete", "downgrade", "reattribute", "rewrite_from_evidence"
    ]


class FidelityAudit(StrictModel):
    schema_version: str = "1.0"
    pipeline_version: str = "afeng-method-v001"
    prompt_version: str = "mimo-method-v001"
    course_id: str
    case_id: str
    knowledge_id: str
    revision_number: int = Field(default=0, ge=0, le=2)
    audit_result: Literal["pass", "revise", "reject"]
    fidelity_score: float = Field(ge=0, le=100)
    field_reviews: list[FidelityFieldReview]
    unsupported_additions: list[str] = Field(default_factory=list)
    misattributed_claims: list[str] = Field(default_factory=list)
    missing_course_conditions: list[str] = Field(default_factory=list)
    invalid_evidence_ids: list[str] = Field(default_factory=list)
    external_knowledge_detected: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    release_allowed: bool = False

    @model_validator(mode="after")
    def validate_release_gate(self) -> "FidelityAudit":
        if self.release_allowed != (self.audit_result == "pass"):
            raise ValueError("release_allowed may only be true for a passing audit")
        return self


class PublicationRecord(StrictModel):
    schema_version: str = "1.0"
    pipeline_version: str = "afeng-method-v001"
    prompt_version: str = "mimo-method-v001"
    knowledge_id: str
    course_id: str
    case_id: str
    publication_class: PublicationClass
    generalization_level: Literal["course_explicit", "single_case", "partial", "none"]
    classification_rationale: str
    evidence_ids: list[str]
    publishable: bool

    @model_validator(mode="after")
    def validate_publishable(self) -> "PublicationRecord":
        if self.publication_class == PublicationClass.REJECT and self.publishable:
            raise ValueError("reject records cannot be publishable")
        return self


class PiiFinding(StrictModel):
    kind: str
    count: int = Field(ge=1)


class ExternalPayload(StrictModel):
    schema_version: str = "1.0"
    source_input_hash: str
    redacted_package: dict[str, Any]
    pii_findings: list[PiiFinding] = Field(default_factory=list)
    external_payload_safe: bool


class AfengRunEvent(StrictModel):
    stage: AfengStage
    status: Literal["started", "completed", "failed", "cached"]
    revision_number: int = Field(default=0, ge=0, le=2)
    input_hash: str
    output_hash: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    error: str | None = None


class AfengRunManifest(StrictModel):
    schema_version: str = "1.0"
    pipeline_version: str = "afeng-method-v001"
    prompt_version: str = "mimo-method-v001"
    model: str
    course_id: str
    case_id: str
    knowledge_id: str
    input_hash: str
    status: Literal["running", "published", "rejected", "manual_review", "failed"]
    revision_count: int = Field(default=0, ge=0, le=2)
    events: list[AfengRunEvent] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
