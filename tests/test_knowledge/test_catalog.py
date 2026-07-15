from pathlib import Path

from course_video_analyzer.knowledge.catalog import (
    discover_sources,
    initialize_knowledge_workspace,
)


def test_discover_sources_preserves_missing_numbers_and_marks_duplicates(tmp_path: Path) -> None:
    (tmp_path / "[1]--第一课.mp4").write_bytes(b"same-video")
    (tmp_path / "[3]--第三课.mp4").write_bytes(b"different")
    (tmp_path / "副本.MP4").write_bytes(b"same-video")
    (tmp_path / "资料.pdf").write_bytes(b"pdf")

    records = discover_sources(tmp_path)
    by_id = {record.source_id: record for record in records}

    assert "C001" in by_id
    assert "C003" in by_id
    assert "C002" not in by_id
    assert by_id["VIDEO001"].duplicate_of == "C001"
    assert by_id["PDF001"].kind.value == "pdf"


def test_initialize_workspace_is_versioned_and_non_destructive(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "[1]--第一课.mp4").write_bytes(b"video")
    data_root = tmp_path / "data"

    _, courses, manifest = initialize_knowledge_workspace(
        source_root,
        data_root,
        batch_id="BATCH-TEST-001",
    )

    assert [course.course_id for course in courses] == ["C001"]
    assert (data_root / "courses/C001/01_raw").is_dir()
    assert (data_root / "courses/C001/05_tidy").is_dir()
    assert manifest.is_file()

    try:
        initialize_knowledge_workspace(
            source_root,
            data_root,
            batch_id="BATCH-TEST-001",
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing batch must not be overwritten")
