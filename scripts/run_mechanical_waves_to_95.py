#!/usr/bin/env python3
"""Run remaining MECHANICAL-QUEUE waves to completion with per-wave commit/push.

Does not start a second instance while batch.lock is held by a live PID.
Only touches mechanical source packets + validation-report + batch scripts/tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
STATE_DIR = WORKSPACE / "data" / "batches" / "MECHANICAL-QUEUE"
PYTHON = WORKSPACE / ".venv" / "Scripts" / "python.exe"
BATCH = WORKSPACE / "scripts" / "run_mechanical_course_batch.py"
LOCK = STATE_DIR / "batch.lock"
SUPERVISOR_LOCK = STATE_DIR / "supervisor.lock"
LOG = STATE_DIR / "logs" / "supervisor-to-95.log"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{_utc()} {msg}\n"
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line)
    print(line, end="", flush=True)


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


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x00100000, 0, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        os.kill(pid, 0)
    except (OSError, SystemError):
        return False
    else:
        return True


def _load_state() -> dict:
    return json.loads((STATE_DIR / "state.json").read_text(encoding="utf-8"))


def _wait_for_idle(poll_seconds: float = 30.0) -> None:
    """Wait until no live batch lock remains."""
    while True:
        if not LOCK.exists():
            _log("idle: no lock")
            return
        try:
            payload = json.loads(LOCK.read_text(encoding="utf-8"))
            pid = int(payload.get("pid") or 0)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pid = 0
        if pid and _pid_alive(pid):
            _log(f"waiting for live batch pid={pid}")
            time.sleep(poll_seconds)
            continue
        # Stale lock
        try:
            LOCK.unlink()
            _log(f"cleared stale lock pid={pid}")
        except OSError as exc:
            _log(f"failed to clear stale lock: {exc}")
            time.sleep(poll_seconds)


def _wave_report_path(wave_index: int) -> Path:
    return STATE_DIR / f"wave-{wave_index:03d}-report.json"


def _courses_for_wave(wave_index: int) -> list[str]:
    state = _load_state()
    return list(state["waves"][wave_index])


def _paths_dirty(course_ids: list[str]) -> bool:
    paths = [f"chat-coach/source-material/{cid}" for cid in course_ids]
    paths.append("chat-coach/source-material/validation-report.json")
    status = _run(["git", "status", "--porcelain", "--", *paths])
    return bool((status.stdout or "").strip())


def _post_wave(wave_index: int, course_ids: list[str], *, force_tests: bool = False) -> None:
    _log(f"post-wave {wave_index}: reconcile")
    rec = _run([str(PYTHON), str(BATCH), "--reconcile-only"], timeout=600)
    _log(f"reconcile rc={rec.returncode}")

    dirty = _paths_dirty(course_ids)
    if not dirty and not force_tests:
        _log(f"wave {wave_index}: packets already committed, skip tests/commit")
        return

    tests = _run(
        [
            str(PYTHON),
            "-m",
            "pytest",
            "tests/test_scripts/test_run_mechanical_course_batch.py",
            "tests/test_scripts/test_export_chat_coach_source_packets.py",
            "-q",
            "--tb=line",
        ],
        timeout=300,
    )
    _log(f"pytest rc={tests.returncode} out={(tests.stdout or '')[-200:]}")
    if tests.returncode != 0:
        raise RuntimeError(f"mechanical tests failed for wave {wave_index}")

    paths = [f"chat-coach/source-material/{cid}" for cid in course_ids]
    paths.append("chat-coach/source-material/validation-report.json")
    add = _run(["git", "add", *paths])
    _log(f"git add rc={add.returncode}")
    staged = _run(["git", "diff", "--cached", "--name-only"])
    staged_files = [line for line in (staged.stdout or "").splitlines() if line.strip()]
    if not staged_files:
        _log(f"wave {wave_index}: nothing to commit")
    else:
        first, last = course_ids[0], course_ids[-1]
        coverage = _load_state().get("coverage", {})
        done = coverage.get("source_packet", "?")
        msg = (
            f"feat: 完成 {first}-{last} 机械资料包（wave{wave_index}）\n\n"
            f"本波课程与全局聚合均通过，覆盖推进至 {done}/95。\n"
        )
        msg_path = WORKSPACE / ".git" / "COMMIT_MSG_TMP.txt"
        msg_path.write_text(msg, encoding="utf-8", newline="\n")
        commit = _run(["git", "commit", "-F", str(msg_path)])
        try:
            msg_path.unlink()
        except OSError:
            pass
        _log(f"git commit rc={commit.returncode} {(commit.stdout or commit.stderr or '')[-300:]}")
        if commit.returncode != 0:
            raise RuntimeError(f"commit failed for wave {wave_index}")

    push = _run(["git", "push"], timeout=600)
    _log(f"git push rc={push.returncode} {(push.stdout or push.stderr or '')[-300:]}")


def _run_wave(wave_index: int) -> dict:
    report_path = _wave_report_path(wave_index)
    state = _load_state()
    courses = list(state["waves"][wave_index])
    # Skip if already fully succeeded on disk and report exists with no failures.
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not report.get("failed_courses") and all(
            state["courses"][cid].get("status") == "succeeded" for cid in courses
        ):
            _log(f"wave {wave_index} already complete: {courses}")
            return report

    _log(f"starting wave {wave_index}: {courses}")
    wave_log = STATE_DIR / "logs" / f"wave-{wave_index:03d}-runner.log"
    with wave_log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n=== supervisor start {_utc()} ===\n")
        proc = subprocess.Popen(
            [
                str(PYTHON),
                str(BATCH),
                "--wave-index",
                str(wave_index),
                "--max-attempts",
                "2",
            ],
            cwd=str(WORKSPACE),
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        _log(f"wave {wave_index} pid={proc.pid}")
        rc = proc.wait()
    _log(f"wave {wave_index} exited rc={rc}")
    if not report_path.exists():
        raise RuntimeError(f"wave {wave_index} finished without report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("failed_courses"):
        _log(f"wave {wave_index} has failures: {report.get('failed_courses')}")
    return report


def _wave_fully_succeeded(wave_index: int) -> bool:
    state = _load_state()
    courses = list(state["waves"][wave_index])
    report_path = _wave_report_path(wave_index)
    if not report_path.exists():
        return False
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("failed_courses"):
        return False
    return all(state["courses"][cid].get("status") == "succeeded" for cid in courses)


def _acquire_supervisor_lock() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "started_at": _utc(),
        "command": list(sys.argv),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(SUPERVISOR_LOCK), flags)
    except FileExistsError:
        try:
            existing = json.loads(SUPERVISOR_LOCK.read_text(encoding="utf-8"))
            existing_pid = int(existing.get("pid") or 0)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            existing_pid = 0
            existing = {}
        if existing_pid and _pid_alive(existing_pid):
            raise RuntimeError(
                f"another supervisor is running: pid={existing_pid} command={existing.get('command')}"
            )
        try:
            SUPERVISOR_LOCK.unlink()
        except OSError as exc:
            raise RuntimeError(f"unable to clear stale supervisor lock: {SUPERVISOR_LOCK}") from exc
        fd = os.open(str(SUPERVISOR_LOCK), flags)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _release_supervisor_lock() -> None:
    if not SUPERVISOR_LOCK.exists():
        return
    try:
        payload = json.loads(SUPERVISOR_LOCK.read_text(encoding="utf-8"))
        if int(payload.get("pid") or 0) not in {0, os.getpid()}:
            return
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    try:
        SUPERVISOR_LOCK.unlink()
    except OSError:
        pass


def main() -> int:
    _log("supervisor start → 95")
    _acquire_supervisor_lock()
    try:
        return _main_locked()
    finally:
        _release_supervisor_lock()


def _main_locked() -> int:
    _wait_for_idle()
    state = _load_state()
    total_waves = len(state["waves"])
    _log(f"total_waves={total_waves} current_wave_index={state.get('current_wave_index')}")

    # Commit any waves that already finished while this supervisor was waiting.
    for wave_index in range(total_waves):
        if _wave_fully_succeeded(wave_index):
            courses = _courses_for_wave(wave_index)
            _post_wave(wave_index, courses)
    push = _run(["git", "push"], timeout=600)
    _log(f"catch-up push rc={push.returncode} {(push.stdout or push.stderr or '')[-200:]}")

    for wave_index in range(total_waves):
        _wait_for_idle()
        if _wave_fully_succeeded(wave_index):
            _log(f"skip completed wave {wave_index}")
            continue
        courses = _courses_for_wave(wave_index)
        report = _run_wave(wave_index)
        _post_wave(wave_index, courses)
        state = _load_state()
        cov = state.get("coverage", {})
        _log(f"coverage after wave {wave_index}: {cov}")
        if report.get("failed_courses"):
            # One more reconcile+retry pass for this wave only.
            _log(f"retrying failed wave {wave_index}: {report.get('failed_courses')}")
            _run([str(PYTHON), str(BATCH), "--reset-failed", "--wave-index", str(wave_index), "--max-attempts", "2"])
            report = json.loads(_wave_report_path(wave_index).read_text(encoding="utf-8"))
            _post_wave(wave_index, courses)
            if report.get("failed_courses"):
                _log("stopping due to unresolved failed courses")
                return 1

    state = _load_state()
    cov = state.get("coverage", {})
    _log(f"DONE coverage={cov}")
    if cov.get("source_packet") != 95 or cov.get("raw") != 95 or cov.get("p02_p03") != 95:
        _log("coverage not yet 95/95 after all waves")
        return 2
    # Final push for any remaining commits.
    push = _run(["git", "push"], timeout=600)
    _log(f"final push rc={push.returncode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
