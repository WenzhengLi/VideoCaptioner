"""Discover local course material and initialize a non-destructive data workspace."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.models import (
    BatchItem,
    BatchManifest,
    CourseRecord,
    SourceKind,
    SourceRecord,
)

COURSE_NUMBER_RE = re.compile(r"^\[(\d+)]")
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi", ".webm"}


def _utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _json_line(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, default=str)


def _title(path: Path) -> str:
    name = path.stem
    name = COURSE_NUMBER_RE.sub("", name).lstrip("-—_ ")
    return name or path.stem


def discover_sources(source_root: Path) -> list[SourceRecord]:
    """Return numbered videos plus PDFs, without guessing missing course numbers."""
    source_root = Path(source_root).resolve()
    records: list[SourceRecord] = []
    extra_video_index = 1
    pdf_index = 1
    for path in sorted(source_root.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file():
            continue
        suffix = path.suffix.casefold()
        match = COURSE_NUMBER_RE.match(path.name)
        if suffix in SUPPORTED_VIDEO_SUFFIXES and match:
            ordinal = int(match.group(1))
            source_id = f"C{ordinal:03d}"
            kind = SourceKind.VIDEO
        elif suffix in SUPPORTED_VIDEO_SUFFIXES:
            ordinal = None
            source_id = f"VIDEO{extra_video_index:03d}"
            extra_video_index += 1
            kind = SourceKind.VIDEO
        elif suffix == ".pdf":
            ordinal = None
            source_id = f"PDF{pdf_index:03d}"
            pdf_index += 1
            kind = SourceKind.PDF
        else:
            continue
        records.append(
            SourceRecord(
                source_id=source_id,
                kind=kind,
                ordinal=ordinal,
                title=_title(path),
                original_name=path.name,
                original_path=path,
                size_bytes=path.stat().st_size,
            )
        )
    return _mark_duplicates(records)


def _mark_duplicates(records: list[SourceRecord]) -> list[SourceRecord]:
    """Hash only same-sized files; this catches likely duplicates without hashing all media."""
    by_size: dict[int, list[SourceRecord]] = defaultdict(list)
    for record in records:
        if record.kind is SourceKind.VIDEO:
            by_size[record.size_bytes].append(record)
    for group in by_size.values():
        if len(group) < 2:
            continue
        by_hash: dict[str, list[SourceRecord]] = defaultdict(list)
        for record in group:
            record.sha256 = _sha256(record.original_path)
            by_hash[record.sha256].append(record)
        for identical in by_hash.values():
            if len(identical) < 2:
                continue
            canonical = sorted(
                identical,
                key=lambda item: (item.ordinal is None, item.ordinal or 999999, item.source_id),
            )[0]
            for record in identical:
                if record is not canonical:
                    record.duplicate_of = canonical.source_id
    return records


def initialize_knowledge_workspace(
    source_root: Path,
    data_root: Path,
    *,
    prompt_version: str = "knowledge-v001",
    batch_id: str | None = None,
) -> tuple[list[SourceRecord], list[CourseRecord], Path]:
    """Create catalogs, per-course directories and a resumable batch manifest."""
    data_root = Path(data_root).resolve()
    catalog_dir = data_root / "catalog"
    courses_dir = data_root / "courses"
    batches_dir = data_root / "batches"
    for path in (catalog_dir, courses_dir, batches_dir):
        path.mkdir(parents=True, exist_ok=True)

    sources = discover_sources(source_root)
    courses = [
        CourseRecord(
            course_id=record.source_id,
            source_id=record.source_id,
            ordinal=record.ordinal,
            title=record.title,
        )
        for record in sources
        if record.kind is SourceKind.VIDEO
        and record.ordinal is not None
        and record.duplicate_of is None
    ]
    courses.sort(key=lambda item: item.ordinal)

    atomic_write_text(
        catalog_dir / "sources.jsonl",
        "\n".join(_json_line(record) for record in sources) + "\n",
    )
    atomic_write_text(
        catalog_dir / "courses.jsonl",
        "\n".join(_json_line(record) for record in courses) + "\n",
    )

    source_lookup = {record.source_id: record for record in sources}
    for course in courses:
        course_dir = courses_dir / course.course_id
        for relative in (
            "01_raw",
            "02_normalized",
            "03_cases",
            "04_knowledge",
            "05_tidy",
            "qa",
            "runs",
        ):
            (course_dir / relative).mkdir(parents=True, exist_ok=True)
        source_json = course_dir / "source.json"
        if not source_json.exists():
            atomic_write_text(
                source_json,
                source_lookup[course.source_id].model_dump_json(indent=2),
            )

    effective_batch_id = batch_id or f"BATCH-{_utc_compact()}"
    batch_dir = batches_dir / effective_batch_id
    if batch_dir.exists():
        raise FileExistsError(f"批次已存在，拒绝覆盖: {batch_dir}")
    batch_dir.mkdir(parents=True)
    manifest = BatchManifest(
        batch_id=effective_batch_id,
        created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        prompt_version=prompt_version,
        items=[BatchItem(course_id=c.course_id, source_id=c.source_id) for c in courses],
    )
    manifest_path = batch_dir / "manifest.json"
    atomic_write_text(manifest_path, manifest.model_dump_json(indent=2))
    atomic_write_text(batch_dir / "status.jsonl", "")
    atomic_write_text(batch_dir / "failures.jsonl", "")
    return sources, courses, manifest_path
