#!/usr/bin/env python3
"""Run P03 knowledge-v003 on a fixed regression set without overwriting v002."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_COURSES = ["C003", "C008", "C006", "C010"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(cmd)}")


def process_course(
    course_id: str,
    *,
    workspace: Path,
    data_root: Path,
    python_exe: Path,
    prompt_root: Path,
    source_p02_version: str,
    output_version: str,
    prompt_version: str,
    model: str,
    timeout_seconds: int,
    status_path: Path,
    force: bool,
) -> None:
    course_dir = data_root / "courses" / course_id
    p02 = course_dir / "02_normalized" / f"P02-{source_p02_version}.json"
    p02_qa = course_dir / "qa" / f"P02-{source_p02_version}-qa.json"
    if not p02.is_file():
        raise FileNotFoundError(f"missing P02: {p02}")
    if not p02_qa.is_file():
        raise FileNotFoundError(f"missing P02 QA: {p02_qa}")
    qa_payload = json.loads(p02_qa.read_text(encoding="utf-8"))
    if qa_payload.get("status") != "pass":
        raise RuntimeError(f"P02 QA not pass for {course_id}")

    cases_dir = course_dir / "03_cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = course_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    timeline = cases_dir / f"P03-input-{output_version}.json"
    output = cases_dir / f"P03-{output_version}.json"
    qa_output = qa_dir / f"P03-{output_version}-qa.json"

    if output.exists() and qa_output.exists() and not force:
        existing = json.loads(qa_output.read_text(encoding="utf-8"))
        if existing.get("status") == "pass":
            _append_jsonl(
                status_path,
                {
                    "at": _utc_now(),
                    "course_id": course_id,
                    "status": "skipped_existing_valid",
                },
            )
            return

    if not timeline.exists() or force:
        if timeline.exists() and force:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            timeline.rename(Path(str(timeline) + f".bak-{stamp}"))
        _run(
            [
                str(python_exe),
                "-m",
                "course_video_analyzer.knowledge.cli",
                "build-p03-input",
                course_id,
                str(p02),
                str(timeline),
            ],
            workspace,
        )

    if output.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output.rename(Path(str(output) + f".invalid-{stamp}"))

    _append_jsonl(
        status_path,
        {"at": _utc_now(), "course_id": course_id, "status": "started"},
    )
    _run(
        [
            str(python_exe),
            "-m",
            "course_video_analyzer.knowledge.cli",
            "cursor-stage",
            course_id,
            "P03",
            str(timeline),
            str(output),
            "--workspace",
            str(workspace),
            "--prompt-root",
            str(prompt_root),
            "--model",
            model,
            "--timeout-seconds",
            str(timeout_seconds),
            "--finish-on-stable-output",
        ],
        workspace,
    )
    _run(
        [
            str(python_exe),
            "-m",
            "course_video_analyzer.knowledge.cli",
            "qa-p03",
            course_id,
            str(p02),
            str(output),
            str(qa_output),
            "--prompt-version",
            prompt_version,
        ],
        workspace,
    )
    qa = json.loads(qa_output.read_text(encoding="utf-8"))
    _append_jsonl(
        status_path,
        {
            "at": _utc_now(),
            "course_id": course_id,
            "status": qa.get("status"),
        },
    )
    if qa.get("status") != "pass":
        raise RuntimeError(f"P03 v003 QA failed for {course_id}: {qa_output}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--python-exe",
        type=Path,
        default=Path(".venv/Scripts/python.exe"),
    )
    parser.add_argument(
        "--courses",
        default=",".join(DEFAULT_COURSES),
    )
    parser.add_argument("--source-p02-version", default="knowledge-v002")
    parser.add_argument("--output-version", default="knowledge-v003")
    parser.add_argument("--prompt-root", type=Path, default=Path("prompts/knowledge-v003"))
    parser.add_argument("--prompt-version", default="knowledge-v003-p03")
    parser.add_argument("--model", default="auto")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--status-path",
        type=Path,
        default=Path(
            "data/batches/BATCH-20260715-001/p03-v003-regression-status.jsonl"
        ),
    )
    args = parser.parse_args()

    courses = [c.strip() for c in args.courses.split(",") if c.strip()]
    for course_id in courses:
        process_course(
            course_id,
            workspace=args.workspace.resolve(),
            data_root=args.data_root.resolve(),
            python_exe=args.python_exe.resolve(),
            prompt_root=args.prompt_root,
            source_p02_version=args.source_p02_version,
            output_version=args.output_version,
            prompt_version=args.prompt_version,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
            status_path=args.status_path.resolve(),
            force=args.force,
        )
    print("P03 v003 regression courses finished:", ",".join(courses))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
