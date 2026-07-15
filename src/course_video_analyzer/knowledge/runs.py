"""Archive successful analyzer jobs and compare transcript versions."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from course_video_analyzer.jobs.workspace import atomic_write_text

TIMESTAMP_RE = re.compile(
    r"\[(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+->\s+"
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})]"
)


def file_sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp_ms(parts: tuple[str, ...]) -> int:
    hour, minute, second, millis = (int(value) for value in parts)
    return ((hour * 60 + minute) * 60 + second) * 1000 + millis


def transcript_metrics(path: Path) -> dict[str, Any]:
    path = Path(path).resolve()
    text = path.read_text(encoding="utf-8")
    timestamps = TIMESTAMP_RE.findall(text)
    return {
        "path": str(path),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
        "line_count": len(text.splitlines()),
        "non_whitespace_chars": sum(not char.isspace() for char in text),
        "timestamp_count": len(timestamps),
        "first_timestamp_ms": _timestamp_ms(timestamps[0][:4]) if timestamps else None,
        "last_timestamp_ms": _timestamp_ms(timestamps[-1][4:]) if timestamps else None,
    }


def compare_transcripts(candidate: Path, baseline: Path) -> dict[str, Any]:
    candidate = Path(candidate).resolve()
    baseline = Path(baseline).resolve()
    candidate_text = candidate.read_text(encoding="utf-8")
    baseline_text = baseline.read_text(encoding="utf-8")
    candidate_metrics = transcript_metrics(candidate)
    baseline_metrics = transcript_metrics(baseline)
    exact_match = candidate_metrics["sha256"] == baseline_metrics["sha256"]
    similarity = (
        1.0
        if exact_match
        else SequenceMatcher(
            None,
            candidate_text.splitlines(),
            baseline_text.splitlines(),
            autojunk=True,
        ).ratio()
    )
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "exact_match": exact_match,
        "text_similarity": similarity,
        "candidate": candidate_metrics,
        "baseline": baseline_metrics,
        "delta": {
            key: candidate_metrics[key] - baseline_metrics[key]
            for key in ("size_bytes", "line_count", "non_whitespace_chars", "timestamp_count")
        },
    }


def archive_successful_job(
    course_id: str,
    job_dir: Path,
    data_root: Path,
    *,
    run_id: str,
    baseline: Path | None = None,
) -> Path:
    """Copy lightweight final artifacts into an immutable course run directory."""
    job_dir = Path(job_dir).resolve()
    data_root = Path(data_root).resolve()
    job_state = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    export_state = job_state.get("stages", {}).get("export", {})
    if export_state.get("status") != "completed":
        raise ValueError(f"任务尚未成功导出: {job_dir}")
    transcript = job_dir / "artifacts/transcript.txt"
    if not transcript.is_file() or transcript.stat().st_size == 0:
        raise ValueError(f"任务 TXT 不存在或为空: {transcript}")

    run_dir = data_root / "courses" / course_id / "01_raw" / run_id
    if run_dir.exists():
        raise FileExistsError(f"运行目录已存在，拒绝覆盖: {run_dir}")
    run_dir.mkdir(parents=True)
    copied: dict[str, str] = {}
    for relative in (
        "job.json",
        "media.json",
        "artifacts/transcript.txt",
        "artifacts/transcript.srt",
        "artifacts/analysis.json",
        "artifacts/timeline.json",
    ):
        source = job_dir / relative
        if not source.is_file():
            continue
        destination = run_dir / Path(relative).name
        shutil.copy2(source, destination)
        copied[destination.name] = file_sha256(destination)

    run_record = {
        "schema_version": "1.0",
        "course_id": course_id,
        "run_id": run_id,
        "source_job_id": job_state.get("job_id"),
        "archived_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "artifacts": copied,
    }
    if baseline is not None:
        report = compare_transcripts(run_dir / "transcript.txt", baseline)
        atomic_write_text(
            run_dir / "comparison.json",
            json.dumps(report, ensure_ascii=False, indent=2),
        )
        run_record["comparison"] = "comparison.json"
    atomic_write_text(run_dir / "run.json", json.dumps(run_record, ensure_ascii=False, indent=2))
    return run_dir
