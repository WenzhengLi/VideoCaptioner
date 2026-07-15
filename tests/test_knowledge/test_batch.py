import json
from pathlib import Path

from course_video_analyzer.knowledge.batch import (
    _load_source_paths,
    _persist_batch_item,
    mark_batch_item,
)
from course_video_analyzer.knowledge.models import (
    BatchItem,
    BatchManifest,
    CourseStatus,
)


def test_load_source_paths_from_jsonl(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    source = tmp_path / "课程.mp4"
    source.write_bytes(b"video")
    (catalog / "sources.jsonl").write_text(
        json.dumps({"source_id": "C001", "original_path": str(source)}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    result = _load_source_paths(tmp_path)

    assert result == {"C001": source}


def test_mark_batch_item_reconciles_external_run(tmp_path: Path) -> None:
    batch_dir = tmp_path / "batches/BATCH-TEST"
    batch_dir.mkdir(parents=True)
    manifest = BatchManifest(
        batch_id="BATCH-TEST",
        created_at="2026-01-01T00:00:00+00:00",
        prompt_version="v1",
        items=[BatchItem(course_id="C001", source_id="C001")],
    )
    (batch_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    updated = mark_batch_item(
        "BATCH-TEST",
        "C001",
        CourseStatus.SUCCEEDED,
        tmp_path,
        run_id="RUN-001",
    )

    assert updated.items[0].status is CourseStatus.SUCCEEDED
    assert updated.items[0].last_run_id == "RUN-001"
    assert (batch_dir / "status.jsonl").is_file()


def test_persist_batch_item_preserves_concurrent_course_updates(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    stale = BatchManifest(
        batch_id="BATCH-TEST",
        created_at="2026-01-01T00:00:00+00:00",
        prompt_version="v1",
        items=[
            BatchItem(course_id="C001", source_id="C001"),
            BatchItem(course_id="C002", source_id="C002"),
        ],
    )
    manifest_path.write_text(stale.model_dump_json(indent=2), encoding="utf-8")

    mark_item = stale.items[0].model_copy(update={"status": CourseStatus.SUCCEEDED})
    _persist_batch_item(manifest_path, mark_item)
    stale_second = stale.items[1].model_copy(update={"status": CourseStatus.RUNNING})
    latest = _persist_batch_item(manifest_path, stale_second)

    assert latest.items[0].status is CourseStatus.SUCCEEDED
    assert latest.items[1].status is CourseStatus.RUNNING
