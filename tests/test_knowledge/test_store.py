import json
from pathlib import Path

from course_video_analyzer.knowledge.store import index_tidy_entries, search_tidy_entries


def test_local_tidy_index_and_search(tmp_path: Path) -> None:
    course = tmp_path / "courses/C001/05_tidy/P06-knowledge-v002"
    course.mkdir(parents=True)
    (course / "case.json").write_text(
        json.dumps(
            {
                "course_id": "C001",
                "case_id": "CASE-C001-001",
                "entries": [
                    {
                        "id": "KNOW-C001-CASE001-001",
                        "title": "尊重明确拒绝",
                        "type": "risk",
                        "evidence_spans": ["SEG-C001-000001"],
                        "confidence": 0.9,
                        "risks": ["对方拒绝后应停止推进"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    database = tmp_path / "tidy/knowledge.db"

    metrics = index_tidy_entries(tmp_path, database)
    results = search_tidy_entries(database, "拒绝")

    assert metrics["entry_count"] == 1
    assert results[0]["id"] == "KNOW-C001-CASE001-001"

    long_query_results = search_tidy_entries(
        database,
        "对方明确拒绝以后，我应该如何判断并回复？",
    )
    assert long_query_results[0]["id"] == "KNOW-C001-CASE001-001"


def test_index_tidy_entries_respects_output_version(tmp_path: Path) -> None:
    v003 = tmp_path / "courses/C001/05_tidy/P06-knowledge-v003"
    v003.mkdir(parents=True)
    (v003 / "case.json").write_text(
        json.dumps(
            {
                "course_id": "C001",
                "case_id": "CASE-C001-001",
                "entries": [
                    {
                        "id": "KNOW-C001-CASE001-V003",
                        "title": "v003 only",
                        "type": "principle",
                        "evidence_spans": [],
                        "confidence": 0.7,
                        "principles": ["版本隔离"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    database = tmp_path / "tidy/v003.db"
    metrics = index_tidy_entries(tmp_path, database, output_version="knowledge-v003")
    assert metrics["entry_count"] == 1
    assert search_tidy_entries(database, "版本隔离")[0]["id"] == "KNOW-C001-CASE001-V003"

    empty = index_tidy_entries(tmp_path, database, output_version="knowledge-v002")
    assert empty["entry_count"] == 0
