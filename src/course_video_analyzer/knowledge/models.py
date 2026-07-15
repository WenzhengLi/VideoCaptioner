"""Stable contracts for course sources and resumable knowledge batches."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class SourceKind(str, Enum):
    VIDEO = "video"
    PDF = "pdf"


class CourseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class SourceRecord(BaseModel):
    schema_version: str = "1.0"
    source_id: str
    kind: SourceKind
    ordinal: int | None = Field(default=None, ge=1)
    title: str
    original_name: str
    original_path: Path
    size_bytes: int = Field(ge=0)
    sha256: str | None = None
    duplicate_of: str | None = None


class CourseRecord(BaseModel):
    schema_version: str = "1.0"
    course_id: str
    source_id: str
    ordinal: int = Field(ge=1)
    title: str
    status: CourseStatus = CourseStatus.PENDING
    latest_successful_run: str | None = None
    latest_prompt_version: str | None = None


class BatchItem(BaseModel):
    course_id: str
    source_id: str
    status: CourseStatus = CourseStatus.PENDING
    attempts: int = Field(default=0, ge=0)
    last_run_id: str | None = None
    error: str | None = None


class BatchManifest(BaseModel):
    schema_version: str = "1.0"
    batch_id: str
    created_at: str
    prompt_version: str
    items: list[BatchItem]
