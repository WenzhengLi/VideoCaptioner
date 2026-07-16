from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from course_video_analyzer.knowledge.dify_sync import (
    DifyConfig,
    DifyConfigError,
    create_dataset,
    sync_markdown_dir,
)


def test_dify_config_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIFY_BASE_URL", raising=False)
    monkeypatch.delenv("DIFY_API_KEY", raising=False)
    with pytest.raises(DifyConfigError):
        DifyConfig.from_env()


def test_create_dataset_posts_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1")
    monkeypatch.setenv("DIFY_API_KEY", "test-key")
    cfg = DifyConfig.from_env()

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return json.dumps({"id": "ds-1", "name": "VideoCaptioner Courses"}).encode()

    with patch("urllib.request.urlopen", return_value=_Resp()) as mocked:
        result = create_dataset(cfg, "VideoCaptioner Courses")
    assert result["id"] == "ds-1"
    req = mocked.call_args.args[0]
    assert req.full_url.endswith("/datasets")
    assert req.get_method() == "POST"
    assert "Bearer test-key" in req.headers["Authorization"]


def test_sync_markdown_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1")
    monkeypatch.setenv("DIFY_API_KEY", "test-key")
    monkeypatch.setenv("DIFY_DATASET_ID", "ds-1")
    cfg = DifyConfig.from_env(require_dataset=True)
    md_dir = tmp_path / "markdown"
    md_dir.mkdir()
    document_path = md_dir / "file-name-does-not-control-id.md"
    document_path.write_text(
        "---\nknowledge_id: KNOW-C001-CASE001-001\ncourse_id: C001\n"
        "fidelity_status: passed\n---\n# title\n",
        encoding="utf-8",
    )
    map_path = tmp_path / "map.json"

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return json.dumps({"document": {"id": "doc-1"}, "batch": "batch-1"}).encode()

    with patch("urllib.request.urlopen", return_value=_Resp()):
        first = sync_markdown_dir(cfg, md_dir, map_path)
        second = sync_markdown_dir(cfg, md_dir, map_path)
        document_path.write_text(
            document_path.read_text(encoding="utf-8") + "\n更新内容\n",
            encoding="utf-8",
        )
        third = sync_markdown_dir(cfg, md_dir, map_path)
    assert first["created"] == 1
    assert first["updated"] == 0
    assert second["created"] == 0
    assert second["skipped"] == 1
    assert third["updated"] == 1
    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    assert mapping["documents"]["KNOW-C001-CASE001-001"]["document_id"] == "doc-1"
    assert len(mapping["documents"]["KNOW-C001-CASE001-001"]["content_sha256"]) == 64
