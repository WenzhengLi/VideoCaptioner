#!/usr/bin/env python3
"""Resumable mechanical course batch runner (raw → P01/P02/P03 → source packet).

This script only performs mechanical pipeline work. It does not analyze lectures,
create tags/OBs/supplements, or modify chat-coach/courses or ob-knowledge-base.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "1.0.0"
WORKSPACE = Path(__file__).resolve().parents[1]
DATA_ROOT = WORKSPACE / "data"
CATALOG_COURSES = DATA_ROOT / "catalog" / "courses.jsonl"
CATALOG_SOURCES = DATA_ROOT / "catalog" / "sources.jsonl"
DEFAULT_STATE_DIR = DATA_ROOT / "batches" / "MECHANICAL-QUEUE"
DEFAULT_OUTPUT_VERSION = "knowledge-v003"
DEFAULT_PROMPT_ROOT = "prompts/knowledge-v003"
DEFAULT_COMPACT_PROMPT_ROOT = "prompts/knowledge-v003-compact"
DEFAULT_RAW_RUN_ID = "RUN-C021-C025-V003-V001"
MIN_FREE_GB = 20.0

# Fixed catalog facts
SKIP_COURSE_IDS = {"C078", "C087"}
DUPLICATE_MAP = {"C078": "C068", "VIDEO001": "C012"}
PDF_SOURCE_IDS = {"PDF001"}

STAGES = (
    "source_lock",
    "duplicate_check",
    "raw",
    "p01",
    "p02",
    "p03",
    "source_packet",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _disk_free_gb(drive: str) -> float:
    usage = shutil.disk_usage(f"{drive}:\\")
    return usage.free / (1024**3)


def _python() -> str:
    return str(WORKSPACE / ".venv" / "Scripts" / "python.exe")


def _run(cmd: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(WORKSPACE),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def build_unique_video_queue() -> dict[str, Any]:
    courses = _load_jsonl(CATALOG_COURSES)
    sources = _load_jsonl(CATALOG_SOURCES)
    source_by_id = {row["source_id"]: row for row in sources}
    unique: list[str] = []
    skipped: list[dict[str, str]] = []
    for course in sorted(courses, key=lambda row: int(row["ordinal"])):
        course_id = str(course["course_id"])
        source_id = str(course["source_id"])
        source = source_by_id.get(source_id, {})
        if course_id in SKIP_COURSE_IDS or source_id in SKIP_COURSE_IDS:
            skipped.append({"course_id": course_id, "reason": "skip_fixed_id"})
            continue
        if source_id in PDF_SOURCE_IDS or source.get("kind") == "pdf":
            skipped.append({"course_id": course_id, "reason": "pdf_separate"})
            continue
        duplicate_of = source.get("duplicate_of") or DUPLICATE_MAP.get(source_id)
        if duplicate_of:
            skipped.append(
                {
                    "course_id": course_id,
                    "reason": f"duplicate_of:{duplicate_of}",
                }
            )
            continue
        unique.append(course_id)
    return {
        "schema_version": "1.0",
        "script_version": SCRIPT_VERSION,
        "catalog_courses": len(courses),
        "catalog_sources": len(sources),
        "unique_video_courses": unique,
        "unique_count": len(unique),
        "skipped": skipped,
        "facts": {
            "sources": 98,
            "videos": 97,
            "unique_videos": 95,
            "duplicates": DUPLICATE_MAP,
            "missing_ids": ["C087"],
            "pdf": ["PDF001"],
        },
        "built_at": _utc_now(),
    }


def default_waves(unique_courses: list[str]) -> list[list[str]]:
    """C023-C025 first (if present), then C026-C030, then groups of 5."""
    remaining = [cid for cid in unique_courses if cid >= "C023"]
    waves: list[list[str]] = []
    bootstrap = [cid for cid in remaining if cid in {"C023", "C024", "C025"}]
    if bootstrap:
        waves.append(bootstrap)
        remaining = [cid for cid in remaining if cid not in set(bootstrap)]
    first = [cid for cid in remaining if "C026" <= cid <= "C030"]
    if first:
        waves.append(first)
        remaining = [cid for cid in remaining if cid not in set(first)]
    for index in range(0, len(remaining), 5):
        waves.append(remaining[index : index + 5])
    return waves


def _load_state(state_dir: Path) -> dict[str, Any]:
    path = state_dir / "state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    queue = build_unique_video_queue()
    waves = default_waves(queue["unique_video_courses"])
    state = {
        "schema_version": "1.0",
        "script_version": SCRIPT_VERSION,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "output_version": DEFAULT_OUTPUT_VERSION,
        "prompt_root": DEFAULT_PROMPT_ROOT,
        "compact_prompt_root": DEFAULT_COMPACT_PROMPT_ROOT,
        "raw_run_id": DEFAULT_RAW_RUN_ID,
        "min_free_gb": MIN_FREE_GB,
        "current_wave_index": 0,
        "waves": waves,
        "queue": queue,
        "courses": {
            course_id: {
                "course_id": course_id,
                "status": "pending",
                "stage": None,
                "attempts": {},
                "errors": [],
                "completed_stages": [],
            }
            for course_id in queue["unique_video_courses"]
        },
        "coverage": {
            "raw": 0,
            "p02_p03": 0,
            "source_packet": 0,
            "unique_total": queue["unique_count"],
        },
    }
    _save_state(state_dir, state)
    _write_json(state_dir / "queue.json", queue)
    return state


def _save_state(state_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = _utc_now()
    # Refresh coverage counts from filesystem.
    packet_root = WORKSPACE / "chat-coach" / "source-material"
    raw = p02 = packet = 0
    for course_id in state["courses"]:
        course_dir = DATA_ROOT / "courses" / course_id
        if any((course_dir / "01_raw").glob("*/transcript.txt")):
            raw += 1
        has_p02 = any((course_dir / "02_normalized").glob("P02-knowledge-*.json"))
        has_p03 = any((course_dir / "03_cases").glob("P03-knowledge-*.json")) or any(
            (course_dir / "02_normalized").glob("P03-knowledge-*.json")
        )
        if has_p02 and has_p03:
            p02 += 1
        if (packet_root / course_id / "课程原文.md").exists():
            packet += 1
    state["coverage"] = {
        "raw": raw,
        "p02_p03": p02,
        "source_packet": packet,
        "unique_total": state["queue"]["unique_count"],
    }
    _write_json(state_dir / "state.json", state)
    _write_json(
        state_dir / "coverage-report.json",
        {
            "schema_version": "1.0",
            "updated_at": state["updated_at"],
            "coverage": state["coverage"],
            "current_wave_index": state["current_wave_index"],
            "current_wave": state["waves"][state["current_wave_index"]]
            if state["current_wave_index"] < len(state["waves"])
            else [],
            "course_statuses": {
                course_id: {
                    "status": info.get("status"),
                    "stage": info.get("stage"),
                    "completed_stages": info.get("completed_stages", []),
                }
                for course_id, info in state["courses"].items()
            },
        },
    )


def _mark(
    state: dict[str, Any],
    course_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    error: str | None = None,
    completed_stage: str | None = None,
) -> None:
    info = state["courses"][course_id]
    if status is not None:
        info["status"] = status
    if stage is not None:
        info["stage"] = stage
        info.setdefault("attempts", {})
        info["attempts"][stage] = int(info["attempts"].get(stage, 0)) + (1 if status == "running" else 0)
    if error:
        info.setdefault("errors", []).append({"at": _utc_now(), "stage": stage, "error": error})
    if completed_stage and completed_stage not in info.setdefault("completed_stages", []):
        info["completed_stages"].append(completed_stage)


def _qa_passed(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("status") == "pass"


def _find_raw_transcript(course_id: str, preferred_run_id: str) -> Path | None:
    preferred = DATA_ROOT / "courses" / course_id / "01_raw" / preferred_run_id / "transcript.txt"
    if preferred.exists():
        return preferred
    raw_root = DATA_ROOT / "courses" / course_id / "01_raw"
    if not raw_root.exists():
        return None
    candidates = sorted(raw_root.glob("*/transcript.txt"))
    return candidates[-1] if candidates else None


def _disk_gate(min_free_gb: float) -> tuple[bool, dict[str, float]]:
    frees = {"D": _disk_free_gb("D"), "E": _disk_free_gb("E")}
    ok = frees["D"] >= min_free_gb and frees["E"] >= min_free_gb
    return ok, frees


def stage_source_lock(course_id: str) -> None:
    source_path = DATA_ROOT / "courses" / course_id / "source.json"
    if not source_path.exists():
        raise FileNotFoundError(f"{course_id} missing source.json")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    original = Path(str(source.get("original_path") or ""))
    if not original.exists():
        raise FileNotFoundError(f"{course_id} source video missing: {original}")
    expected_size = int(source.get("size_bytes") or 0)
    actual_size = original.stat().st_size
    if expected_size and actual_size != expected_size:
        raise ValueError(f"{course_id} size mismatch expected={expected_size} actual={actual_size}")
    expected_sha = str(source.get("sha256") or "")
    if expected_sha:
        actual_sha = _sha256_file(original)
        if actual_sha.lower() != expected_sha.lower():
            raise ValueError(f"{course_id} sha256 mismatch")


def stage_duplicate_check(course_id: str, queue: dict[str, Any]) -> None:
    for skipped in queue.get("skipped", []):
        if skipped.get("course_id") == course_id:
            raise RuntimeError(f"{course_id} should be skipped: {skipped.get('reason')}")
    if course_id in SKIP_COURSE_IDS:
        raise RuntimeError(f"{course_id} is in skip list")


def stage_raw(course_id: str, raw_run_id: str) -> None:
    transcript = _find_raw_transcript(course_id, raw_run_id)
    if transcript is None:
        raise FileNotFoundError(
            f"{course_id} raw transcript missing; run video analysis before mechanical stages"
        )
    qa_path = DATA_ROOT / "courses" / course_id / "qa" / f"{transcript.parent.name}.json"
    if not _qa_passed(qa_path):
        raise RuntimeError(f"{course_id} raw QA not pass: {qa_path}")


def stage_p01(course_id: str, output_version: str, prompt_root: str, raw_run_id: str) -> None:
    transcript = _find_raw_transcript(course_id, raw_run_id)
    if transcript is None:
        raise FileNotFoundError(f"{course_id} transcript missing")
    norm_dir = DATA_ROOT / "courses" / course_id / "02_normalized"
    qa_dir = DATA_ROOT / "courses" / course_id / "qa"
    norm_dir.mkdir(parents=True, exist_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)
    baseline = norm_dir / f"P01-baseline-{output_version}.json"
    output = norm_dir / f"P01-{output_version}.json"
    qa_output = qa_dir / f"P01-{output_version}-qa.json"
    if output.exists() and _qa_passed(qa_output):
        return
    if not baseline.exists():
        result = _run(
            [
                _python(),
                "-m",
                "course_video_analyzer.knowledge.cli",
                "normalize-p01",
                course_id,
                str(transcript),
                str(baseline),
                "--prompt-version",
                f"{output_version}-p01-baseline",
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(f"normalize-p01 failed: {result.stderr or result.stdout}")
    if output.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output.rename(Path(str(output) + f".invalid-{stamp}"))
    result = _run(
        [
            _python(),
            "-m",
            "course_video_analyzer.knowledge.cli",
            "cursor-stage",
            course_id,
            "P01",
            str(baseline),
            str(output),
            "--workspace",
            str(WORKSPACE),
            "--model",
            "auto",
            "--prompt-root",
            prompt_root,
            "--timeout-seconds",
            "3600",
        ],
        timeout=3900,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cursor P01 failed: {result.stderr or result.stdout}")
    result = _run(
        [
            _python(),
            "-m",
            "course_video_analyzer.knowledge.cli",
            "qa-p01",
            course_id,
            str(transcript),
            str(output),
            str(qa_output),
            "--prompt-version",
            f"{output_version}-p01",
        ]
    )
    if result.returncode != 0 or not _qa_passed(qa_output):
        raise RuntimeError(f"qa-p01 failed: {result.stderr or result.stdout}")


def stage_p02(
    course_id: str, output_version: str, prompt_root: str, compact_prompt_root: str
) -> None:
    norm_dir = DATA_ROOT / "courses" / course_id / "02_normalized"
    qa_dir = DATA_ROOT / "courses" / course_id / "qa"
    p01 = norm_dir / f"P01-{output_version}.json"
    baseline = norm_dir / f"P02-baseline-{output_version}.json"
    review_pack = norm_dir / f"P02-review-pack-{output_version}.json"
    review_decision = norm_dir / f"P02-review-decisions-{output_version}.json"
    output = norm_dir / f"P02-{output_version}.json"
    qa_output = qa_dir / f"P02-{output_version}-qa.json"
    if output.exists() and _qa_passed(qa_output):
        return
    if not baseline.exists():
        result = _run(
            [
                _python(),
                "-m",
                "course_video_analyzer.knowledge.cli",
                "classify-p02",
                course_id,
                str(p01),
                str(baseline),
                "--prompt-version",
                f"{output_version}-p02-baseline",
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(f"classify-p02 failed: {result.stderr or result.stdout}")
    if not review_pack.exists():
        result = _run(
            [
                _python(),
                "-m",
                "course_video_analyzer.knowledge.cli",
                "build-p02-review",
                course_id,
                str(baseline),
                str(review_pack),
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(f"build-p02-review failed: {result.stderr or result.stdout}")
    if review_decision.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        review_decision.rename(Path(str(review_decision) + f".invalid-{stamp}"))
    if output.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output.rename(Path(str(output) + f".invalid-{stamp}"))
    result = _run(
        [
            _python(),
            "-m",
            "course_video_analyzer.knowledge.cli",
            "cursor-stage",
            course_id,
            "P02",
            str(review_pack),
            str(review_decision),
            "--workspace",
            str(WORKSPACE),
            "--model",
            "auto",
            "--prompt-root",
            compact_prompt_root,
            "--timeout-seconds",
            "1200",
            "--finish-on-stable-output",
            "--output-stability-seconds",
            "30",
        ],
        timeout=1500,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cursor P02 failed: {result.stderr or result.stdout}")
    result = _run(
        [
            _python(),
            "-m",
            "course_video_analyzer.knowledge.cli",
            "apply-p02-review",
            course_id,
            str(baseline),
            str(review_pack),
            str(review_decision),
            str(output),
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(f"apply-p02-review failed: {result.stderr or result.stdout}")
    result = _run(
        [
            _python(),
            "-m",
            "course_video_analyzer.knowledge.cli",
            "qa-p02",
            course_id,
            str(p01),
            str(output),
            str(qa_output),
            "--prompt-version",
            f"{output_version}-p02",
        ]
    )
    if result.returncode != 0 or not _qa_passed(qa_output):
        raise RuntimeError(f"qa-p02 failed: {result.stderr or result.stdout}")


def stage_p03(course_id: str, output_version: str, prompt_root: str) -> None:
    norm_dir = DATA_ROOT / "courses" / course_id / "02_normalized"
    case_dir = DATA_ROOT / "courses" / course_id / "03_cases"
    qa_dir = DATA_ROOT / "courses" / course_id / "qa"
    case_dir.mkdir(parents=True, exist_ok=True)
    p02 = norm_dir / f"P02-{output_version}.json"
    timeline = case_dir / f"P03-input-{output_version}.json"
    output = case_dir / f"P03-{output_version}.json"
    qa_output = qa_dir / f"P03-{output_version}-qa.json"
    if output.exists() and _qa_passed(qa_output):
        return
    if not timeline.exists():
        result = _run(
            [
                _python(),
                "-m",
                "course_video_analyzer.knowledge.cli",
                "build-p03-input",
                course_id,
                str(p02),
                str(timeline),
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(f"build-p03-input failed: {result.stderr or result.stdout}")
    if output.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output.rename(Path(str(output) + f".invalid-{stamp}"))
    result = _run(
        [
            _python(),
            "-m",
            "course_video_analyzer.knowledge.cli",
            "cursor-stage",
            course_id,
            "P03",
            str(timeline),
            str(output),
            "--workspace",
            str(WORKSPACE),
            "--model",
            "auto",
            "--prompt-root",
            prompt_root,
            "--timeout-seconds",
            "3600",
        ],
        timeout=3900,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cursor P03 failed: {result.stderr or result.stdout}")
    result = _run(
        [
            _python(),
            "-m",
            "course_video_analyzer.knowledge.cli",
            "qa-p03",
            course_id,
            str(p02),
            str(output),
            str(qa_output),
            "--prompt-version",
            f"{output_version}-p03",
        ]
    )
    if result.returncode != 0 or not _qa_passed(qa_output):
        raise RuntimeError(f"qa-p03 failed: {result.stderr or result.stdout}")


def stage_source_packet(course_id: str) -> None:
    result = _run(
        [
            _python(),
            str(WORKSPACE / "scripts" / "export_chat_coach_source_packets.py"),
            "--courses",
            course_id,
            "--rerun-delay-seconds",
            "1.1",
        ],
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"source packet export failed: {result.stderr or result.stdout}")


def process_course(state_dir: Path, state: dict[str, Any], course_id: str, max_attempts: int) -> str:
    info = state["courses"][course_id]
    if info.get("status") == "succeeded" and set(STAGES).issubset(set(info.get("completed_stages", []))):
        return "skipped_done"

    stage_runners = {
        "source_lock": lambda: stage_source_lock(course_id),
        "duplicate_check": lambda: stage_duplicate_check(course_id, state["queue"]),
        "raw": lambda: stage_raw(course_id, state["raw_run_id"]),
        "p01": lambda: stage_p01(
            course_id, state["output_version"], state["prompt_root"], state["raw_run_id"]
        ),
        "p02": lambda: stage_p02(
            course_id,
            state["output_version"],
            state["prompt_root"],
            state["compact_prompt_root"],
        ),
        "p03": lambda: stage_p03(course_id, state["output_version"], state["prompt_root"]),
        "source_packet": lambda: stage_source_packet(course_id),
    }

    for stage in STAGES:
        if stage in info.get("completed_stages", []):
            continue
        attempts = int(info.get("attempts", {}).get(stage, 0))
        while attempts < max_attempts:
            _mark(state, course_id, status="running", stage=stage)
            _save_state(state_dir, state)
            try:
                stage_runners[stage]()
                _mark(state, course_id, status="running", completed_stage=stage)
                _save_state(state_dir, state)
                break
            except Exception as error:  # noqa: BLE001 - persist any stage failure
                attempts += 1
                _mark(
                    state,
                    course_id,
                    status="failed",
                    stage=stage,
                    error=f"{type(error).__name__}: {error}",
                )
                info["attempts"][stage] = attempts
                _save_state(state_dir, state)
                if attempts >= max_attempts:
                    return "failed"
                time.sleep(2)
        else:
            return "failed"
    _mark(state, course_id, status="succeeded", stage=None)
    _save_state(state_dir, state)
    return "succeeded"


def run_wave(state_dir: Path, state: dict[str, Any], wave_index: int, max_attempts: int) -> dict[str, Any]:
    if wave_index < 0 or wave_index >= len(state["waves"]):
        raise IndexError(f"wave_index out of range: {wave_index}")
    ok, frees = _disk_gate(float(state.get("min_free_gb", MIN_FREE_GB)))
    wave = state["waves"][wave_index]
    report: dict[str, Any] = {
        "wave_index": wave_index,
        "courses": wave,
        "started_at": _utc_now(),
        "disk": frees,
        "results": {},
        "stopped_for_disk": False,
    }
    if not ok:
        report["stopped_for_disk"] = True
        report["finished_at"] = _utc_now()
        _write_json(state_dir / f"wave-{wave_index:03d}-report.json", report)
        return report

    failed: list[str] = []
    for course_id in wave:
        ok, frees = _disk_gate(float(state.get("min_free_gb", MIN_FREE_GB)))
        report["disk"] = frees
        if not ok:
            report["stopped_for_disk"] = True
            report["results"][course_id] = "blocked_disk"
            break
        result = process_course(state_dir, state, course_id, max_attempts)
        report["results"][course_id] = result
        if result == "failed":
            failed.append(course_id)

    # Unified retry pass for failures in this wave.
    for course_id in list(failed):
        result = process_course(state_dir, state, course_id, max_attempts)
        report["results"][course_id] = f"retry:{result}"
        if result == "succeeded":
            failed.remove(course_id)

    state["current_wave_index"] = wave_index + (0 if report["stopped_for_disk"] else 1)
    _save_state(state_dir, state)
    report["failed_courses"] = failed
    report["finished_at"] = _utc_now()
    _write_json(state_dir / f"wave-{wave_index:03d}-report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Resumable mechanical course batch runner")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--init-only", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--wave-index", type=int, help="Run one wave by index")
    parser.add_argument("--courses", help="Comma-separated course IDs override for ad-hoc run")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--min-free-gb", type=float, default=MIN_FREE_GB)
    args = parser.parse_args()

    state_dir = args.state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    state = _load_state(state_dir)
    state["min_free_gb"] = args.min_free_gb

    if args.init_only:
        _save_state(state_dir, state)
        print(f"Initialized queue with {state['queue']['unique_count']} unique courses")
        print(f"Waves: {len(state['waves'])}; first={state['waves'][0] if state['waves'] else []}")
        return 0

    if args.status:
        print(json.dumps(state["coverage"], ensure_ascii=False, indent=2))
        print(f"current_wave_index={state['current_wave_index']}")
        if state["current_wave_index"] < len(state["waves"]):
            print(f"current_wave={state['waves'][state['current_wave_index']]}")
        return 0

    if args.courses:
        course_ids = [item.strip() for item in args.courses.split(",") if item.strip()]
        report = {"courses": course_ids, "started_at": _utc_now(), "results": {}}
        for course_id in course_ids:
            if course_id not in state["courses"]:
                state["courses"][course_id] = {
                    "course_id": course_id,
                    "status": "pending",
                    "stage": None,
                    "attempts": {},
                    "errors": [],
                    "completed_stages": [],
                }
            report["results"][course_id] = process_course(
                state_dir, state, course_id, args.max_attempts
            )
        report["finished_at"] = _utc_now()
        _write_json(state_dir / "ad-hoc-report.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if all(
            value in {"succeeded", "skipped_done"} or str(value).endswith("succeeded")
            for value in report["results"].values()
        ) else 1

    wave_index = args.wave_index if args.wave_index is not None else int(state["current_wave_index"])
    report = run_wave(state_dir, state, wave_index, args.max_attempts)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("stopped_for_disk"):
        return 2
    return 0 if not report.get("failed_courses") else 1


if __name__ == "__main__":
    raise SystemExit(main())
