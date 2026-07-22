"""Tests for run_mechanical_course_batch.py (tmp_path + mocks only; no real videos)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

import scripts.run_mechanical_course_batch as batch


PACKET_FILES = batch.PACKET_FILES


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _qa(path: Path, status: str = "pass") -> None:
    _write_json(path, {"status": status})


def _touch_packet(root: Path, course_id: str, *, with_report: bool = True, ok: bool = True) -> None:
    course_dir = root / "chat-coach" / "source-material" / course_id
    course_dir.mkdir(parents=True, exist_ok=True)
    for name in PACKET_FILES:
        (course_dir / name).write_text(f"{course_id}:{name}\n", encoding="utf-8")
    if with_report:
        _write_json(
            course_dir / "validation-report.json",
            {
                "course_id": course_id,
                "status": "ok" if ok else "failed",
                "all_ok": ok,
                "reason": None if ok else "failed",
                "warning_count": 0,
                "failed_checks_count": 0 if ok else 1,
                "rerun_hash_check": {"passed": ok},
            },
        )


def _configure_batch_roots(tmp_path: Path, monkeypatch) -> Path:
    data_root = tmp_path / "data"
    monkeypatch.setattr(batch, "WORKSPACE", tmp_path)
    monkeypatch.setattr(batch, "DATA_ROOT", data_root)
    monkeypatch.setattr(batch, "CATALOG_COURSES", data_root / "catalog" / "courses.jsonl")
    monkeypatch.setattr(batch, "CATALOG_SOURCES", data_root / "catalog" / "sources.jsonl")
    monkeypatch.setattr(batch, "DEFAULT_STATE_DIR", data_root / "batches" / "MECHANICAL-QUEUE")
    return data_root


def _seed_course_artifacts(
    data_root: Path,
    workspace: Path,
    course_id: str,
    *,
    legacy_qa: bool = False,
    include_packet: bool = True,
    output_version: str = "knowledge-v003",
) -> None:
    course_dir = data_root / "courses" / course_id
    video = workspace / "videos" / f"{course_id}.mp4"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"fake-video")
    _write_json(
        course_dir / "source.json",
        {
            "original_path": str(video),
            "size_bytes": video.stat().st_size,
            "sha256": "",
        },
    )
    run_id = f"RUN-{course_id}"
    transcript = course_dir / "01_raw" / run_id / "transcript.txt"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("hello\n", encoding="utf-8")
    _qa(course_dir / "qa" / f"{run_id}.json")

    norm = course_dir / "02_normalized"
    cases = course_dir / "03_cases"
    norm.mkdir(parents=True, exist_ok=True)
    cases.mkdir(parents=True, exist_ok=True)
    (norm / f"P01-{output_version}.json").write_text("{}", encoding="utf-8")
    (norm / f"P02-{output_version}.json").write_text("{}", encoding="utf-8")
    (cases / f"P03-{output_version}.json").write_text("{}", encoding="utf-8")
    qa_dir = course_dir / "qa"
    if legacy_qa:
        _qa(qa_dir / f"qa-P01-{course_id}.json")
        _qa(qa_dir / f"qa-P02-{course_id}.json")
        _qa(qa_dir / f"qa-P03-{course_id}.json")
    else:
        _qa(qa_dir / f"P01-{output_version}-qa.json")
        _qa(qa_dir / f"P02-{output_version}-qa.json")
        _qa(qa_dir / f"P03-{output_version}-qa.json")
    if include_packet:
        _touch_packet(workspace, course_id)


def test_real_catalog_unique_count_and_mappings() -> None:
    queue = batch.build_unique_video_queue()
    assert queue["unique_count"] == 95
    assert len(queue["unique_video_courses"]) == 95
    assert len(set(queue["unique_video_courses"])) == 95
    assert "C078" not in queue["unique_video_courses"]
    assert "C087" not in queue["unique_video_courses"]
    assert "VIDEO001" not in queue["unique_video_courses"]
    assert "PDF001" not in queue["unique_video_courses"]
    assert batch.DUPLICATE_MAP["C078"] == "C068"
    assert batch.DUPLICATE_MAP["VIDEO001"] == "C012"
    # Catalog may omit duplicate/PDF course rows entirely; still enforce fixed facts.
    sources = batch._load_jsonl(batch.CATALOG_SOURCES)
    by_id = {row["source_id"]: row for row in sources}
    assert by_id["C078"].get("duplicate_of") == "C068" or batch.DUPLICATE_MAP["C078"] == "C068"
    assert by_id["VIDEO001"].get("duplicate_of") == "C012" or batch.DUPLICATE_MAP["VIDEO001"] == "C012"
    assert by_id["PDF001"].get("kind") == "pdf" or "PDF001" in batch.PDF_SOURCE_IDS
    assert not any(row["course_id"] == "C087" for row in batch._load_jsonl(batch.CATALOG_COURSES))


def test_default_waves_groups_of_five() -> None:
    unique = [f"C{i:03d}" for i in range(23, 50) if i != 87]
    waves = batch.default_waves(unique)
    assert waves[0] == ["C023", "C024", "C025"]
    assert waves[1] == ["C026", "C027", "C028", "C029", "C030"]
    assert waves[2] == ["C031", "C032", "C033", "C034", "C035"]
    assert all(len(wave) <= 5 for wave in waves)


def test_atomic_write_json(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    batch._write_json(target, {"ok": True, "n": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"n": 1, "ok": True}
    leftovers = list(tmp_path.glob(".state.json.*.tmp"))
    assert leftovers == []


def test_single_instance_lock_and_stale_recovery(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "queue"
    state_dir.mkdir()
    monkeypatch.setattr(batch, "_pid_alive", lambda pid: pid == 111)
    batch._write_json(
        state_dir / batch.LOCK_FILENAME,
        {"pid": 111, "command": ["old"], "wave": 1, "state_dir": str(state_dir)},
    )
    with pytest.raises(RuntimeError, match="another mechanical batch"):
        batch.acquire_batch_lock(state_dir, command=["new"], wave=2)

    monkeypatch.setattr(batch, "_pid_alive", lambda pid: False)
    lock_path = batch.acquire_batch_lock(state_dir, command=["recovered"], wave=3)
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["pid"] == os.getpid()
    assert payload["wave"] == 3
    assert payload["command"] == ["recovered"]
    batch.release_batch_lock(state_dir)
    assert not lock_path.exists()


def test_discover_and_reconcile_legacy_qa(tmp_path: Path, monkeypatch) -> None:
    data_root = _configure_batch_roots(tmp_path, monkeypatch)
    _seed_course_artifacts(data_root, tmp_path, "C021", legacy_qa=True)
    _seed_course_artifacts(data_root, tmp_path, "C022", legacy_qa=True)
    state_dir = data_root / "batches" / "MECHANICAL-QUEUE"
    state = {
        "schema_version": "1.0",
        "script_version": batch.SCRIPT_VERSION,
        "output_version": "knowledge-v003",
        "raw_run_id": "RUN-X",
        "current_wave_index": 0,
        "waves": [["C021", "C022"]],
        "queue": {"unique_count": 2, "unique_video_courses": ["C021", "C022"], "skipped": []},
        "courses": {
            "C021": {
                "course_id": "C021",
                "status": "pending",
                "stage": "raw",
                "attempts": {},
                "errors": [{"error": "old"}],
                "completed_stages": [],
            },
            "C022": {
                "course_id": "C022",
                "status": "failed",
                "stage": "p03",
                "attempts": {"p03": 2},
                "errors": [{"error": "boom", "resolved": False}],
                "completed_stages": ["source_lock"],
            },
        },
        "coverage": {"raw": 0, "p02_p03": 0, "source_packet": 0, "unique_total": 2},
    }
    _write_json(
        state_dir / "wave-002-report.json",
        {
            "wave_index": 2,
            "failed_courses": ["C022", "C031"],
            "results": {"C022": "retry:failed", "C031": "retry:failed"},
        },
    )
    # C031 not in this mini state; only repair C022 here.
    summary = batch.reconcile_state(state_dir, state)
    assert "C021" in summary["succeeded"]
    assert "C022" in summary["succeeded"]
    assert state["courses"]["C021"]["status"] == "succeeded"
    assert state["courses"]["C021"]["stage"] is None
    assert set(state["courses"]["C021"]["completed_stages"]) == set(batch.STAGES)
    assert state["courses"]["C022"]["status"] == "succeeded"
    assert state["courses"]["C022"]["stage"] is None
    assert state["courses"]["C022"]["errors"][0]["resolved"] is True
    wave = json.loads((state_dir / "wave-002-report.json").read_text(encoding="utf-8"))
    assert "C022" not in wave["failed_courses"]
    assert wave["results"]["C022"] == "resolved:succeeded"


def test_reconcile_resolves_c031_style_wave_report(tmp_path: Path, monkeypatch) -> None:
    data_root = _configure_batch_roots(tmp_path, monkeypatch)
    _seed_course_artifacts(data_root, tmp_path, "C031")
    state_dir = data_root / "batches" / "MECHANICAL-QUEUE"
    state = {
        "schema_version": "1.0",
        "output_version": "knowledge-v003",
        "raw_run_id": "RUN-X",
        "current_wave_index": 3,
        "waves": [["C031"]],
        "queue": {"unique_count": 1, "unique_video_courses": ["C031"], "skipped": []},
        "courses": {
            "C031": {
                "course_id": "C031",
                "status": "succeeded",
                "stage": "source_packet",
                "attempts": {},
                "errors": [{"error": "old export fail"}],
                "completed_stages": list(batch.STAGES),
            }
        },
        "coverage": {"raw": 1, "p02_p03": 1, "source_packet": 1, "unique_total": 1},
    }
    _write_json(
        state_dir / "wave-002-report.json",
        {"failed_courses": ["C031"], "results": {"C031": "retry:failed"}},
    )
    batch.reconcile_state(state_dir, state)
    assert state["courses"]["C031"]["stage"] is None
    assert state["courses"]["C031"]["status"] == "succeeded"
    wave = json.loads((state_dir / "wave-002-report.json").read_text(encoding="utf-8"))
    assert wave["failed_courses"] == []
    assert wave["results"]["C031"] == "resolved:succeeded"


def test_reconcile_accepts_knowledge_v002_artifacts(tmp_path: Path, monkeypatch) -> None:
    data_root = _configure_batch_roots(tmp_path, monkeypatch)
    _seed_course_artifacts(data_root, tmp_path, "C001", output_version="knowledge-v002")
    state_dir = data_root / "batches" / "MECHANICAL-QUEUE"
    state = {
        "schema_version": "1.0",
        "output_version": "knowledge-v003",
        "raw_run_id": "RUN-X",
        "current_wave_index": 0,
        "waves": [["C001"]],
        "queue": {"unique_count": 1, "unique_video_courses": ["C001"], "skipped": []},
        "courses": {
            "C001": {
                "course_id": "C001",
                "status": "pending",
                "stage": None,
                "attempts": {},
                "errors": [],
                "completed_stages": [],
            }
        },
        "coverage": {"raw": 0, "p02_p03": 0, "source_packet": 0, "unique_total": 1},
    }
    summary = batch.reconcile_state(state_dir, state)
    assert "C001" in summary["succeeded"]
    assert state["courses"]["C001"]["status"] == "succeeded"
    assert state["courses"]["C001"]["stage"] is None
    assert set(state["courses"]["C001"]["completed_stages"]) == set(batch.STAGES)
    assert state["coverage"]["source_packet"] == 1


def test_process_course_skips_completed_stages(tmp_path: Path, monkeypatch) -> None:
    data_root = _configure_batch_roots(tmp_path, monkeypatch)
    state_dir = data_root / "batches" / "Q"
    state_dir.mkdir(parents=True)
    calls: list[str] = []

    def fake_runner(name: str):
        def _inner(*_a, **_k):
            calls.append(name)

        return _inner

    monkeypatch.setattr(batch, "stage_source_lock", fake_runner("source_lock"))
    monkeypatch.setattr(batch, "stage_duplicate_check", fake_runner("duplicate_check"))
    monkeypatch.setattr(batch, "stage_raw", fake_runner("raw"))
    monkeypatch.setattr(batch, "stage_p01", fake_runner("p01"))
    monkeypatch.setattr(batch, "stage_p02", fake_runner("p02"))
    monkeypatch.setattr(batch, "stage_p03", fake_runner("p03"))
    monkeypatch.setattr(batch, "stage_source_packet", fake_runner("source_packet"))

    state = {
        "raw_run_id": "RUN",
        "output_version": "knowledge-v003",
        "prompt_root": "p",
        "compact_prompt_root": "c",
        "queue": {"skipped": [], "unique_count": 1},
        "courses": {
            "C099": {
                "course_id": "C099",
                "status": "running",
                "stage": None,
                "attempts": {},
                "errors": [],
                "completed_stages": ["source_lock", "duplicate_check", "raw", "p01", "p02"],
            }
        },
        "coverage": {},
        "waves": [["C099"]],
        "current_wave_index": 0,
    }
    result = batch.process_course(state_dir, state, "C099", max_attempts=2)
    assert result == "succeeded"
    assert calls == ["p03", "source_packet"]


def test_wave_continues_after_failure_then_retry_resolves(tmp_path: Path, monkeypatch) -> None:
    data_root = _configure_batch_roots(tmp_path, monkeypatch)
    state_dir = data_root / "batches" / "Q"
    state_dir.mkdir(parents=True)
    attempts = {"C001": 0, "C002": 0}

    def fake_process(_state_dir, state, course_id, max_attempts):
        attempts[course_id] += 1
        info = state["courses"][course_id]
        if course_id == "C001" and attempts[course_id] == 1:
            info["status"] = "failed"
            return "failed"
        info["status"] = "succeeded"
        info["stage"] = None
        info["completed_stages"] = list(batch.STAGES)
        return "succeeded"

    monkeypatch.setattr(batch, "process_course", fake_process)
    monkeypatch.setattr(batch, "_disk_gate", lambda _min: (True, {"D": 100.0, "E": 100.0}))
    monkeypatch.setattr(
        batch,
        "_run",
        lambda *_a, **_k: type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})(),
    )

    state = {
        "min_free_gb": 1,
        "current_wave_index": 0,
        "waves": [["C001", "C002"]],
        "queue": {"unique_count": 2},
        "courses": {
            "C001": {
                "course_id": "C001",
                "status": "pending",
                "stage": None,
                "attempts": {},
                "errors": [],
                "completed_stages": [],
            },
            "C002": {
                "course_id": "C002",
                "status": "pending",
                "stage": None,
                "attempts": {},
                "errors": [],
                "completed_stages": [],
            },
        },
        "coverage": {},
    }
    report = batch.run_wave(state_dir, state, 0, max_attempts=2)
    assert report["results"]["C002"] == "succeeded"
    assert report["results"]["C001"] == "resolved:succeeded"
    assert report["failed_courses"] == []
    assert attempts == {"C001": 2, "C002": 1}


def test_disk_gate_stops_new_courses(tmp_path: Path, monkeypatch) -> None:
    data_root = _configure_batch_roots(tmp_path, monkeypatch)
    state_dir = data_root / "batches" / "Q"
    state_dir.mkdir(parents=True)
    monkeypatch.setattr(batch, "_disk_gate", lambda _min: (False, {"D": 1.0, "E": 1.0}))
    called: list[str] = []

    def fake_process(*_a, **_k):
        called.append("x")
        return "succeeded"

    monkeypatch.setattr(batch, "process_course", fake_process)
    state = {
        "min_free_gb": 20,
        "current_wave_index": 0,
        "waves": [["C001", "C002"]],
        "queue": {"unique_count": 2},
        "courses": {
            "C001": {"status": "pending", "stage": None, "attempts": {}, "errors": [], "completed_stages": []},
            "C002": {"status": "pending", "stage": None, "attempts": {}, "errors": [], "completed_stages": []},
        },
        "coverage": {},
    }
    report = batch.run_wave(state_dir, state, 0, max_attempts=1)
    assert report["stopped_for_disk"] is True
    assert called == []
    assert report["results"].get("C001") == "blocked_disk" or report["results"] == {}


def test_main_rejects_second_instance(tmp_path: Path, monkeypatch) -> None:
    data_root = _configure_batch_roots(tmp_path, monkeypatch)
    state_dir = data_root / "batches" / "MECHANICAL-QUEUE"
    # Initialize empty state without catalog by writing directly.
    state = {
        "schema_version": "1.0",
        "script_version": batch.SCRIPT_VERSION,
        "current_wave_index": 0,
        "waves": [],
        "queue": {"unique_count": 0, "unique_video_courses": [], "skipped": []},
        "courses": {},
        "coverage": {"raw": 0, "p02_p03": 0, "source_packet": 0, "unique_total": 0},
        "min_free_gb": 1,
        "output_version": "knowledge-v003",
        "raw_run_id": "RUN",
        "prompt_root": "p",
        "compact_prompt_root": "c",
    }
    batch._save_state(state_dir, state)
    monkeypatch.setattr(batch, "_pid_alive", lambda pid: True)
    batch._write_json(
        state_dir / batch.LOCK_FILENAME,
        {"pid": 99999, "command": ["other"], "wave": 1, "state_dir": str(state_dir)},
    )
    monkeypatch.setattr(
        "sys.argv",
        ["run_mechanical_course_batch.py", "--state-dir", str(state_dir), "--status"],
    )
    # --status does not take lock
    assert batch.main() == 0

    monkeypatch.setattr(
        "sys.argv",
        ["run_mechanical_course_batch.py", "--state-dir", str(state_dir), "--wave-index", "0"],
    )
    with pytest.raises(RuntimeError, match="another mechanical batch"):
        batch.main()


def test_single_course_report_does_not_shrink_global(tmp_path: Path, monkeypatch) -> None:
    import scripts.export_chat_coach_source_packets as exporter

    output_root = tmp_path / "chat-coach" / "source-material"
    monkeypatch.setattr(exporter, "OUTPUT_ROOT", output_root)
    for course_id in ("C001", "C002"):
        course_dir = output_root / course_id
        course_dir.mkdir(parents=True)
        for name in exporter.OUTPUT_FILES:
            (course_dir / name).write_text(f"{course_id}-{name}", encoding="utf-8")
        _write_json(
            course_dir / "validation-report.json",
            {
                "course_id": course_id,
                "status": "ok",
                "all_ok": True,
                "reason": None,
                "warning_count": 0,
                "failed_checks_count": 0,
                "rerun_hash_check": {"passed": True},
            },
        )
    # Simulate exporting only C002 writing its report, then aggregating all completed.
    _write_json(
        output_root / "C002" / "validation-report.json",
        {
            "course_id": "C002",
            "status": "ok",
            "all_ok": True,
            "reason": None,
            "warning_count": 1,
            "failed_checks_count": 0,
            "rerun_hash_check": {"passed": True},
        },
    )
    report_path = exporter.aggregate_validation_reports()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["total_courses"] == 2
    assert report["exported"] == 2
    assert report["failed_count"] == 0
    assert report["failed_checks_count"] == 0
    assert report["all_passed"] is True
    assert report["warning_count"] == 1
    ids = {row["course_id"] for row in report["courses"]}
    assert ids == {"C001", "C002"}


def test_aggregate_excludes_failed_hash_course(tmp_path: Path, monkeypatch) -> None:
    import scripts.export_chat_coach_source_packets as exporter

    output_root = tmp_path / "chat-coach" / "source-material"
    monkeypatch.setattr(exporter, "OUTPUT_ROOT", output_root)
    for course_id, ok in (("C001", True), ("C002", False)):
        course_dir = output_root / course_id
        course_dir.mkdir(parents=True)
        for name in exporter.OUTPUT_FILES:
            (course_dir / name).write_text(name, encoding="utf-8")
        _write_json(
            course_dir / "validation-report.json",
            {
                "course_id": course_id,
                "status": "ok" if ok else "failed",
                "all_ok": ok,
                "reason": None if ok else "cross-second rerun hash comparison failed",
                "warning_count": 0,
                "failed_checks_count": 0 if ok else 1,
                "rerun_hash_check": {"passed": ok},
            },
        )
    report = json.loads(exporter.aggregate_validation_reports().read_text(encoding="utf-8"))
    assert report["total_courses"] == 2
    assert report["exported"] == 1
    assert report["failed_count"] == 1
    assert report["all_passed"] is False
