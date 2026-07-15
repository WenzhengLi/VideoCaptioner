import json
from pathlib import Path

from course_video_analyzer.knowledge.batch import _load_source_paths


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
