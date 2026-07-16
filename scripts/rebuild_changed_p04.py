#!/usr/bin/env python3
"""Rebuild P04 only for cases marked source_case_changed in an evidence baseline."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"failed ({completed.returncode}): {' '.join(cmd)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("data/catalog/evidence-baseline-C001-C015.json"),
    )
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument(
        "--python-exe", type=Path, default=Path(".venv/Scripts/python.exe")
    )
    parser.add_argument("--prompt-root", type=Path, default=Path("prompts/knowledge-v003"))
    parser.add_argument("--model", default="auto")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--only-changed", action="store_true", default=True)
    args = parser.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    for course in baseline.get("courses") or []:
        course_id = course["course_id"]
        p03_version = course["p03_version"]
        p02 = args.data_root / "courses" / course_id / "02_normalized" / "P02-knowledge-v002.json"
        p03 = args.data_root / "courses" / course_id / "03_cases" / f"P03-{p03_version}.json"
        for case in course.get("cases") or []:
            if args.only_changed and not case.get("source_case_changed"):
                continue
            if case.get("qa_status") == "pass" and not case.get("source_case_changed"):
                continue
            case_id = case["case_id"]
            p04_version = case["p04_version"]
            input_dir = (
                args.data_root
                / "courses"
                / course_id
                / "04_knowledge"
                / f"P04-input-{p04_version}"
            )
            out_dir = (
                args.data_root / "courses" / course_id / "04_knowledge" / f"P04-{p04_version}"
            )
            input_dir.mkdir(parents=True, exist_ok=True)
            out_dir.mkdir(parents=True, exist_ok=True)
            case_input = input_dir / f"{case_id}.json"
            output = out_dir / f"{case_id}.json"
            qa_output = (
                args.data_root
                / "courses"
                / course_id
                / "qa"
                / f"P04-{case_id}-{p04_version}-qa.json"
            )
            if output.exists() and qa_output.exists():
                qa = json.loads(qa_output.read_text(encoding="utf-8"))
                if qa.get("status") == "pass":
                    print(f"skip existing pass {course_id} {case_id}")
                    continue
            prompt_version = f"{p04_version}-p04"
            if output.exists() and case_input.exists():
                _run(
                    [
                        str(args.python_exe),
                        "-m",
                        "course_video_analyzer.knowledge.cli",
                        "qa-p04",
                        course_id,
                        case_id,
                        str(case_input),
                        str(output),
                        str(qa_output),
                        "--prompt-version",
                        prompt_version,
                    ],
                    args.workspace,
                )
                qa = json.loads(qa_output.read_text(encoding="utf-8"))
                if qa.get("status") == "pass":
                    print(f"reused existing output after QA fix {course_id} {case_id}")
                    continue
            if case_input.exists():
                stamp = __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).strftime("%Y%m%dT%H%M%SZ")
                case_input.rename(Path(str(case_input) + f".bak-{stamp}"))
            _run(
                [
                    str(args.python_exe),
                    "-m",
                    "course_video_analyzer.knowledge.cli",
                    "build-p04-input",
                    course_id,
                    case_id,
                    str(p02),
                    str(p03),
                    str(case_input),
                ],
                args.workspace,
            )
            if output.exists():
                stamp = __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).strftime("%Y%m%dT%H%M%SZ")
                output.rename(Path(str(output) + f".invalid-{stamp}"))
            _run(
                [
                    str(args.python_exe),
                    "-m",
                    "course_video_analyzer.knowledge.cli",
                    "cursor-stage",
                    course_id,
                    "P04",
                    str(case_input),
                    str(output),
                    "--workspace",
                    str(args.workspace),
                    "--prompt-root",
                    str(args.prompt_root),
                    "--model",
                    args.model,
                    "--timeout-seconds",
                    str(args.timeout_seconds),
                    "--finish-on-stable-output",
                    "--output-stability-seconds",
                    "60",
                ],
                args.workspace,
            )
            _run(
                [
                    str(args.python_exe),
                    "-m",
                    "course_video_analyzer.knowledge.cli",
                    "qa-p04",
                    course_id,
                    case_id,
                    str(case_input),
                    str(output),
                    str(qa_output),
                    "--prompt-version",
                    prompt_version,
                ],
                args.workspace,
            )
            qa = json.loads(qa_output.read_text(encoding="utf-8"))
            print(f"{course_id} {case_id} qa={qa.get('status')}", flush=True)
            if qa.get("status") != "pass":
                raise RuntimeError(f"P04 QA failed: {qa_output}")
    print("changed-case P04 rebuild complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
