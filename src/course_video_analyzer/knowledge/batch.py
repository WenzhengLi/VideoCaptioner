"""Serial, resumable batch orchestration with one subprocess per course."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.models import BatchManifest, CourseStatus


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    atomic_write_text(path, previous + json.dumps(payload, ensure_ascii=False) + "\n")


def _load_source_paths(data_root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    catalog = Path(data_root) / "catalog" / "sources.jsonl"
    for line in catalog.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        result[str(record["source_id"])] = Path(record["original_path"])
    return result


def run_batch(
    batch_id: str,
    data_root: Path,
    jobs_root: Path,
    *,
    start_ordinal: int | None = None,
    end_ordinal: int | None = None,
    run_version: str = "V001",
    processing_profile: str = "complete-v1",
    timeout_seconds: int = 14_400,
    max_attempts: int = 2,
    ffmpeg_bin: Path | None = None,
) -> BatchManifest:
    data_root = Path(data_root).resolve()
    jobs_root = Path(jobs_root).resolve()
    batch_dir = data_root / "batches" / batch_id
    manifest_path = batch_dir / "manifest.json"
    manifest = BatchManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    source_paths = _load_source_paths(data_root)
    logs_dir = batch_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    if ffmpeg_bin is not None:
        environment["PATH"] = str(Path(ffmpeg_bin).resolve()) + os.pathsep + environment["PATH"]

    for item in manifest.items:
        ordinal = int(item.course_id[1:])
        if start_ordinal is not None and ordinal < start_ordinal:
            continue
        if end_ordinal is not None and ordinal > end_ordinal:
            continue
        if item.status is CourseStatus.SUCCEEDED:
            continue

        run_id = f"RUN-{batch_id.removeprefix('BATCH-')}-{run_version}"
        archive_dir = data_root / "courses" / item.course_id / "01_raw" / run_id
        if (archive_dir / "run.json").is_file():
            item.status = CourseStatus.SUCCEEDED
            item.last_run_id = run_id
            atomic_write_text(manifest_path, manifest.model_dump_json(indent=2))
            continue

        job_id = f"{item.course_id}-{run_id}"
        command = [
            sys.executable,
            "-m",
            "course_video_analyzer.analysis_cli",
            str(source_paths[item.source_id]),
            "--jobs-root",
            str(jobs_root),
            "--job-id",
            job_id,
            "--processing-profile",
            processing_profile,
            "--archive-course",
            item.course_id,
            "--data-root",
            str(data_root),
            "--run-id",
            run_id,
        ]
        item.status = CourseStatus.RUNNING
        item.last_run_id = run_id
        atomic_write_text(manifest_path, manifest.model_dump_json(indent=2))

        while item.attempts < max_attempts:
            item.attempts += 1
            event = {
                "at": _utc_now(),
                "course_id": item.course_id,
                "run_id": run_id,
                "attempt": item.attempts,
                "event": "started",
            }
            _append_jsonl(batch_dir / "status.jsonl", event)
            log_path = logs_dir / f"{item.course_id}-attempt-{item.attempts}.log"
            try:
                with log_path.open("w", encoding="utf-8") as log:
                    completed = subprocess.run(
                        command,
                        cwd=Path.cwd(),
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=timeout_seconds,
                        check=False,
                    )
                if completed.returncode == 0:
                    item.status = CourseStatus.SUCCEEDED
                    item.error = None
                    _append_jsonl(
                        batch_dir / "status.jsonl",
                        {**event, "at": _utc_now(), "event": "succeeded"},
                    )
                    break
                item.error = f"exit_code={completed.returncode}; log={log_path}"
            except subprocess.TimeoutExpired:
                item.error = f"timeout={timeout_seconds}s; log={log_path}"
            _append_jsonl(
                batch_dir / "failures.jsonl",
                {**event, "at": _utc_now(), "event": "failed", "error": item.error},
            )
            atomic_write_text(manifest_path, manifest.model_dump_json(indent=2))

        if item.status is not CourseStatus.SUCCEEDED:
            item.status = CourseStatus.FAILED
        atomic_write_text(manifest_path, manifest.model_dump_json(indent=2))
    return manifest
