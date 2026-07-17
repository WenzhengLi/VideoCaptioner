from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from course_video_analyzer.knowledge.dify_sync import (
    DifyConfig,
    DifyConfigError,
    DifyApiError,
    create_dataset,
    plan_markdown_sync,
    save_document_map,
    sync_markdown_dir,
)


def test_dify_config_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIFY_BASE_URL", raising=False)
    monkeypatch.delenv("DIFY_API_KEY", raising=False)
    with pytest.raises(DifyConfigError):
        DifyConfig.from_env()


def test_dify_config_strips_bearer_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1/")
    monkeypatch.setenv("DIFY_API_KEY", "Bearer secret-token")
    cfg = DifyConfig.from_env()
    assert cfg.base_url == "http://127.0.0.1:3080/v1"
    assert cfg.api_key == "secret-token"


def test_dry_run_plan_without_api_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIFY_BASE_URL", raising=False)
    monkeypatch.delenv("DIFY_API_KEY", raising=False)
    md_dir = tmp_path / "documents"
    md_dir.mkdir()
    text_a = "---\nknowledge_id: KNOW-A\n---\n# A\n"
    (md_dir / "a.md").write_text(text_a, encoding="utf-8")
    (md_dir / "b.md").write_text(
        "---\nknowledge_id: KNOW-B\n---\n# B\n",
        encoding="utf-8",
    )
    map_path = tmp_path / "map.json"
    save_document_map(
        map_path,
        {
            "schema_version": "1.0",
            "documents": {
                "KNOW-A": {
                    "document_id": "doc-a",
                    "content_sha256": "0" * 64,
                }
            },
        },
    )
    plan = plan_markdown_sync(md_dir, map_path)
    assert plan["dry_run"] is True
    assert plan["create"] == 1
    assert plan["update"] == 1
    assert plan["skip"] == 0

    exact = hashlib.sha256(text_a.encode("utf-8")).hexdigest()
    save_document_map(
        map_path,
        {
            "schema_version": "1.0",
            "documents": {
                "KNOW-A": {"document_id": "doc-a", "content_sha256": exact},
            },
        },
    )
    plan2 = plan_markdown_sync(md_dir, map_path)
    assert plan2["skip"] == 1
    assert plan2["create"] == 1
    assert plan2["update"] == 0


def test_sync_rejects_missing_markdown_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1")
    monkeypatch.setenv("DIFY_API_KEY", "test-key")
    monkeypatch.setenv("DIFY_DATASET_ID", "ds-1")
    cfg = DifyConfig.from_env(require_dataset=True)
    with pytest.raises(DifyConfigError, match="不存在"):
        sync_markdown_dir(cfg, tmp_path / "missing", tmp_path / "map.json")


def test_sync_retries_transient_api_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1")
    monkeypatch.setenv("DIFY_API_KEY", "test-key")
    monkeypatch.setenv("DIFY_DATASET_ID", "ds-1")
    cfg = DifyConfig.from_env(require_dataset=True)
    md_dir = tmp_path / "markdown"
    md_dir.mkdir()
    (md_dir / "k.md").write_text(
        "---\nknowledge_id: KNOW-RETRY\n---\n# retry\n",
        encoding="utf-8",
    )
    map_path = tmp_path / "map.json"
    calls = {"n": 0}

    def _flaky_request(cfg_arg, method, path, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise DifyApiError("transient 503")
        return {"document": {"id": "doc-r"}, "batch": "b1"}

    with patch("course_video_analyzer.knowledge.dify_sync.ensure_dataset_exists", return_value={"id": "ds-1"}):
        with patch("course_video_analyzer.knowledge.dify_sync._request", side_effect=_flaky_request):
            with patch("course_video_analyzer.knowledge.dify_sync.time.sleep", return_value=None):
                result = sync_markdown_dir(cfg, md_dir, map_path, retries=2)
    assert result["created"] == 1
    assert calls["n"] == 2
    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    assert mapping["documents"]["KNOW-RETRY"]["document_id"] == "doc-r"


def test_ensure_dataset_maps_404_to_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1")
    monkeypatch.setenv("DIFY_API_KEY", "test-key")
    cfg = DifyConfig.from_env()

    def _not_found(*_args, **_kwargs):
        raise DifyApiError("Dify API GET /datasets/x -> HTTP 404: missing")

    with patch("course_video_analyzer.knowledge.dify_sync._request", side_effect=_not_found):
        with pytest.raises(DifyConfigError, match="不存在"):
            from course_video_analyzer.knowledge.dify_sync import ensure_dataset_exists

            ensure_dataset_exists(cfg, "x")


def test_save_document_map_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "map.json"
    save_document_map(target, {"schema_version": "1.0", "documents": {"A": {"document_id": "1"}}})
    assert target.is_file()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["documents"]["A"]["document_id"] == "1"
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_create_dataset_defaults_to_economy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1")
    monkeypatch.setenv("DIFY_API_KEY", "test-key")
    cfg = DifyConfig.from_env()

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return json.dumps({"id": "ds-eco", "name": "阿峰课程方法库-研究版"}).encode()

    with patch("urllib.request.urlopen", return_value=_Resp()) as mocked:
        result = create_dataset(cfg, "阿峰课程方法库-研究版")
    assert result["id"] == "ds-eco"
    req = mocked.call_args.args[0]
    assert req.full_url.endswith("/datasets")
    assert req.get_method() == "POST"
    assert "Bearer test-key" in req.headers["Authorization"]
    body = json.loads(req.data.decode("utf-8"))
    assert body["indexing_technique"] == "economy"


def test_plan_uses_canonical_id_when_course_and_case_present(tmp_path: Path) -> None:
    """When frontmatter has course_id+case_id, the canonical id is the map key,
    not any model-authored knowledge_id value. This prevents duplicate Dify
    documents on re-run or cross-model rerender."""
    md_dir = tmp_path / "documents"
    md_dir.mkdir()
    # Model-authored knowledge id in frontmatter; course_id+case_id also present.
    (md_dir / "doc.md").write_text(
        "---\n"
        'knowledge_id: "mimo-freehand-C007-001"\n'
        "course_id: C007\n"
        "case_id: CASE-C007-001\n"
        "fidelity_status: passed\n"
        "---\n# 方法\n",
        encoding="utf-8",
    )
    map_path = tmp_path / "map.json"
    plan = plan_markdown_sync(md_dir, map_path)
    assert plan["create"] == 1
    planned_id = plan["planned"][0]["knowledge_id"]
    assert planned_id == "AFENG-C007-CASE-C007-001"
    assert planned_id != "mimo-freehand-C007-001"

    # A second markdown for the SAME course/case but a different model-authored id
    # must map to the SAME canonical key (update, not a duplicate create).
    (md_dir / "doc2.md").write_text(
        "---\n"
        'knowledge_id: "glm-freehand-C007-001"\n'
        "course_id: C007\n"
        "case_id: CASE-C007-001\n"
        "fidelity_status: passed\n"
        "---\n# 方法\n",
        encoding="utf-8",
    )
    plan2 = plan_markdown_sync(md_dir, map_path)
    ids = {item["knowledge_id"] for item in plan2["planned"]}
    assert ids == {"AFENG-C007-CASE-C007-001"}


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

    with patch("course_video_analyzer.knowledge.dify_sync.ensure_dataset_exists", return_value={"id": "ds-1"}):
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


def test_sync_indexing_technique_explicit_param(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit indexing_technique parameter takes precedence over env var and dataset mode."""
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1")
    monkeypatch.setenv("DIFY_API_KEY", "test-key")
    monkeypatch.setenv("DIFY_DATASET_ID", "ds-1")
    cfg = DifyConfig.from_env(require_dataset=True)
    md_dir = tmp_path / "markdown"
    md_dir.mkdir()
    (md_dir / "k.md").write_text(
        "---\nknowledge_id: KNOW-IDX\n---\n# idx\n",
        encoding="utf-8",
    )
    map_path = tmp_path / "map.json"

    captured_payloads: list[dict] = []

    def _capture_request(cfg_arg, method, path, **kwargs):
        if kwargs.get("payload"):
            captured_payloads.append(kwargs["payload"])
        return {"document": {"id": "doc-idx"}, "batch": "b1"}

    with patch(
        "course_video_analyzer.knowledge.dify_sync.ensure_dataset_exists",
        return_value={
            "id": "ds-1",
            "indexing_technique": "economy",
            "embedding_model": "bge-m3",
            "embedding_model_provider": "ollama",
        },
    ):
        with patch(
            "course_video_analyzer.knowledge.dify_sync._request",
            side_effect=_capture_request,
        ):
            sync_markdown_dir(cfg, md_dir, map_path, indexing_technique="high_quality")
    assert captured_payloads[0]["indexing_technique"] == "high_quality"


def test_sync_high_quality_requires_embedding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """high_quality mode raises DifyConfigError when dataset has no embedding configured."""
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1")
    monkeypatch.setenv("DIFY_API_KEY", "test-key")
    monkeypatch.setenv("DIFY_DATASET_ID", "ds-1")
    cfg = DifyConfig.from_env(require_dataset=True)
    md_dir = tmp_path / "markdown"
    md_dir.mkdir()
    (md_dir / "k.md").write_text(
        "---\nknowledge_id: KNOW-HQ\n---\n# hq\n",
        encoding="utf-8",
    )
    map_path = tmp_path / "map.json"

    with patch(
        "course_video_analyzer.knowledge.dify_sync.ensure_dataset_exists",
        return_value={
            "id": "ds-1",
            "indexing_technique": "economy",
            "embedding_model": None,
            "embedding_model_provider": None,
        },
    ):
        with pytest.raises(DifyConfigError, match="embedding provider"):
            sync_markdown_dir(cfg, md_dir, map_path, indexing_technique="high_quality")


def test_sync_falls_back_to_dataset_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no explicit indexing_technique, falls back to dataset mode."""
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1")
    monkeypatch.setenv("DIFY_API_KEY", "test-key")
    monkeypatch.setenv("DIFY_DATASET_ID", "ds-1")
    # Clear env var to test fallback
    monkeypatch.delenv("DIFY_DATASET_INDEXING", raising=False)
    cfg = DifyConfig.from_env(require_dataset=True)
    md_dir = tmp_path / "markdown"
    md_dir.mkdir()
    (md_dir / "k.md").write_text(
        "---\nknowledge_id: KNOW-FB\n---\n# fb\n",
        encoding="utf-8",
    )
    map_path = tmp_path / "map.json"

    captured_payloads: list[dict] = []

    def _capture_request(cfg_arg, method, path, **kwargs):
        if kwargs.get("payload"):
            captured_payloads.append(kwargs["payload"])
        return {"document": {"id": "doc-fb"}, "batch": "b1"}

    with patch(
        "course_video_analyzer.knowledge.dify_sync.ensure_dataset_exists",
        return_value={"id": "ds-1", "indexing_technique": "economy"},
    ):
        with patch(
            "course_video_analyzer.knowledge.dify_sync._request",
            side_effect=_capture_request,
        ):
            sync_markdown_dir(cfg, md_dir, map_path)
    assert captured_payloads[0]["indexing_technique"] == "economy"


def test_sync_fails_fast_on_dataset_id_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sync refuses to proceed when map is bound to a different dataset.

    This prevents accidentally syncing v002.6 into the old economy working
    Dataset or corrupting the old map with new canonical keys.
    """
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1")
    monkeypatch.setenv("DIFY_API_KEY", "test-key")
    monkeypatch.setenv("DIFY_DATASET_ID", "ds-formal")
    cfg = DifyConfig.from_env(require_dataset=True)
    md_dir = tmp_path / "markdown"
    md_dir.mkdir()
    (md_dir / "k.md").write_text(
        "---\nknowledge_id: AFENG-C001-CASE-C001-001\ncourse_id: C001\n"
        "case_id: CASE-C001-001\n---\n# title\n",
        encoding="utf-8",
    )
    # Pre-populate map with a DIFFERENT dataset_id (simulating old economy map)
    map_path = tmp_path / "map.json"
    save_document_map(
        map_path,
        {
            "schema_version": "1.0",
            "dataset_id": "ds-economy-old",
            "documents": {},
        },
    )

    with patch(
        "course_video_analyzer.knowledge.dify_sync.ensure_dataset_exists",
        return_value={"id": "ds-formal", "indexing_technique": "high_quality",
                       "embedding_model": "bge-m3", "embedding_model_provider": "ollama"},
    ):
        with pytest.raises(DifyConfigError, match="document map 已绑定"):
            sync_markdown_dir(cfg, md_dir, map_path, indexing_technique="high_quality")


def test_sync_allows_fresh_map_for_new_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sync proceeds when map has no dataset_id bound yet (fresh map)."""
    monkeypatch.setenv("DIFY_BASE_URL", "http://127.0.0.1:3080/v1")
    monkeypatch.setenv("DIFY_API_KEY", "test-key")
    monkeypatch.setenv("DIFY_DATASET_ID", "ds-formal")
    cfg = DifyConfig.from_env(require_dataset=True)
    md_dir = tmp_path / "markdown"
    md_dir.mkdir()
    (md_dir / "k.md").write_text(
        "---\nknowledge_id: AFENG-C001-CASE-C001-001\n---\n# title\n",
        encoding="utf-8",
    )
    # Fresh map with no dataset_id
    map_path = tmp_path / "map.json"
    save_document_map(map_path, {"schema_version": "1.0", "documents": {}})

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return json.dumps({"document": {"id": "doc-new"}, "batch": "b1"}).encode()

    with patch(
        "course_video_analyzer.knowledge.dify_sync.ensure_dataset_exists",
        return_value={"id": "ds-formal", "indexing_technique": "high_quality",
                       "embedding_model": "bge-m3", "embedding_model_provider": "ollama"},
    ):
        with patch("urllib.request.urlopen", return_value=_Resp()):
            result = sync_markdown_dir(
                cfg, md_dir, map_path, indexing_technique="high_quality"
            )
    assert result["created"] == 1
    assert result["failed"] == []
    # After sync, map should be bound to the target dataset
    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    assert mapping["dataset_id"] == "ds-formal"
