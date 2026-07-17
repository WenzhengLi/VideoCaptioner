"""Dify Knowledge API sync helpers.

This is the real product integration path. Local SQLite (`index-tidy`) is only an
offline regression index and must never be described as Dify ingestion.
"""

from __future__ import annotations

import json
import hashlib
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any, TypeVar

from course_video_analyzer.jobs.workspace import atomic_write_text
from course_video_analyzer.knowledge.afeng import canonical_knowledge_id

T = TypeVar("T")


class DifyConfigError(RuntimeError):
    """Missing or invalid Dify configuration."""


class DifyApiError(RuntimeError):
    """Dify HTTP API failure (status / payload)."""


@dataclass(frozen=True)
class DifyConfig:
    base_url: str
    api_key: str
    dataset_id: str | None = None

    @classmethod
    def from_env(cls, *, require_dataset: bool = False) -> "DifyConfig":
        base = (os.environ.get("DIFY_BASE_URL") or "").rstrip("/")
        key = os.environ.get("DIFY_API_KEY") or ""
        dataset = os.environ.get("DIFY_DATASET_ID") or None
        if not base or not key:
            raise DifyConfigError(
                "需要环境变量 DIFY_BASE_URL 与 DIFY_API_KEY；"
                "真实密钥不得写入仓库。参考 deploy/dify/.env.example。"
            )
        if require_dataset and not dataset:
            raise DifyConfigError("需要环境变量 DIFY_DATASET_ID（先运行 dify-create-dataset）。")
        if key.lower().startswith("bearer "):
            key = key.split(" ", 1)[1].strip()
        return cls(base_url=base, api_key=key, dataset_id=dataset)


def _redact_secrets(text: str) -> str:
    """Best-effort redaction if response bodies echo Authorization material."""
    lower = text.lower()
    marker = "bearer "
    idx = lower.find(marker)
    if idx < 0:
        return text
    start = idx + len(marker)
    end = start
    while end < len(text) and not text[end].isspace() and text[end] not in {",", '"', "'", "}"}:
        end += 1
    return text[:start] + "<redacted>" + text[end:]


def _request(
    cfg: DifyConfig,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    url = f"{cfg.base_url}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = _redact_secrets(exc.read().decode("utf-8", errors="replace"))
        raise DifyApiError(f"Dify API {method} {path} -> HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise DifyApiError(f"Dify API 不可达 {cfg.base_url}{path}: {exc}") from exc


def get_dataset(cfg: DifyConfig, dataset_id: str) -> dict[str, Any]:
    return _request(cfg, "GET", f"/datasets/{dataset_id}")


def ensure_dataset_exists(cfg: DifyConfig, dataset_id: str) -> dict[str, Any]:
    try:
        return get_dataset(cfg, dataset_id)
    except DifyApiError as exc:
        if "HTTP 404" in str(exc):
            raise DifyConfigError(
                f"Dify Dataset 不存在: {dataset_id}。"
                "请先运行 deploy/dify/scripts/initialize-dataset.ps1 或 dify-create-dataset。"
            ) from exc
        raise


def create_dataset(
    cfg: DifyConfig,
    name: str,
    *,
    description: str = "",
    indexing_technique: str = "economy",
) -> dict[str, Any]:
    if indexing_technique not in {"economy", "high_quality"}:
        raise DifyConfigError("indexing_technique 必须是 economy 或 high_quality")
    return _request(
        cfg,
        "POST",
        "/datasets",
        payload={
            "name": name,
            "description": description,
            "indexing_technique": indexing_technique,
            "permission": "only_me",
        },
    )


def create_document_by_text(
    cfg: DifyConfig,
    *,
    dataset_id: str,
    name: str,
    text: str,
    metadata: dict[str, Any] | None = None,
    indexing_technique: str = "economy",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "text": text,
        "indexing_technique": indexing_technique,
        "process_rule": {"mode": "automatic"},
    }
    if metadata:
        # Dify metadata support varies by version; keep as doc_metadata when accepted.
        payload["doc_metadata"] = [
            {"name": key, "value": value}
            for key, value in metadata.items()
            if value is not None and value != ""
        ]
    return _request(cfg, "POST", f"/datasets/{dataset_id}/document/create-by-text", payload=payload)


def update_document_by_text(
    cfg: DifyConfig,
    *,
    dataset_id: str,
    document_id: str,
    name: str,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "text": text,
        "process_rule": {"mode": "automatic"},
    }
    if metadata:
        payload["doc_metadata"] = [
            {"name": key, "value": value}
            for key, value in metadata.items()
            if value is not None and value != ""
        ]
    return _request(
        cfg,
        "POST",
        f"/datasets/{dataset_id}/documents/{document_id}/update-by-text",
        payload=payload,
    )


def get_indexing_status(cfg: DifyConfig, *, dataset_id: str, batch: str) -> dict[str, Any]:
    return _request(cfg, "GET", f"/datasets/{dataset_id}/documents/{batch}/indexing-status")


def load_document_map(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "1.0", "documents": {}}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_document_map(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _metadata_from_markdown(path: Path, text: str) -> dict[str, Any]:
    meta: dict[str, Any] = {"source_path": str(path).replace("\\", "/")}
    # Prefer YAML-ish front matter keys if present; otherwise parse KNOW id from filename.
    meta["knowledge_id"] = path.stem
    for line in text.splitlines()[:40]:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lstrip("#- ").lower()
        value = value.strip().strip('"\'')
        if key in {
            "knowledge_id",
            "course_id",
            "case_id",
            "content_type",
            "rights_status",
            "fidelity_status",
            "publication_class",
            "generalization_level",
            "pipeline_version",
            "type",
            "prompt_version",
            "source_start_ms",
            "source_end_ms",
            "input_hash",
            "confidence",
            "source_ids",
            "evidence_spans",
            "safety_flags",
        }:
            meta[key] = value
    # The canonical knowledge id is the only stable idempotency key. When the
    # frontmatter carries course_id and case_id, derive the canonical id from
    # them and ignore any model-authored knowledge_id value. This keeps re-runs
    # and cross-model rerenders from creating duplicate Dify documents.
    course_id = str(meta.get("course_id") or "").strip()
    case_id = str(meta.get("case_id") or "").strip()
    if course_id and case_id:
        meta["knowledge_id"] = canonical_knowledge_id(course_id, case_id)
    return meta


def _with_retries(
    operation: str,
    fn: Callable[[], T],
    *,
    retries: int = 2,
    backoff_seconds: float = 1.0,
) -> T:
    """Retry transient Dify API failures; never log secrets."""
    attempt = 0
    while True:
        try:
            return fn()
        except DifyApiError:
            attempt += 1
            if attempt > retries:
                raise
            # Keep error short; DifyApiError already truncates response bodies.
            time.sleep(backoff_seconds * attempt)
            _ = operation  # retained for call-site clarity / future structured logs


def plan_markdown_sync(
    markdown_root: Path,
    map_path: Path,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Dry-run plan: classify create / update / skip without calling Dify API."""
    if not markdown_root.exists():
        raise DifyConfigError(f"markdown_root 不存在: {markdown_root}")
    if not markdown_root.is_dir():
        raise DifyConfigError(f"markdown_root 不是目录: {markdown_root}")
    mapping = load_document_map(map_path)
    docs: dict[str, Any] = mapping.get("documents") or {}
    files = sorted(markdown_root.rglob("*.md"))
    if limit is not None:
        if limit < 0:
            raise DifyConfigError("--limit 不能为负数")
        files = files[:limit]
    planned: list[dict[str, str]] = []
    create = update = skip = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        meta = _metadata_from_markdown(path, text)
        knowledge_id = str(meta.get("knowledge_id") or path.stem)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = docs.get(knowledge_id)
        if (
            existing
            and existing.get("document_id")
            and existing.get("content_sha256") == digest
        ):
            action = "skip"
            skip += 1
        elif existing and existing.get("document_id"):
            action = "update"
            update += 1
        else:
            action = "create"
            create += 1
        planned.append(
            {
                "knowledge_id": knowledge_id,
                "action": action,
                "content_sha256": digest,
                "source_path": str(path).replace("\\", "/"),
            }
        )
    return {
        "dry_run": True,
        "markdown_root": str(markdown_root),
        "map_path": str(map_path),
        "create": create,
        "update": update,
        "skip": skip,
        "planned": planned,
        "note": "未调用 Dify API；最终包到位后再去掉 --dry-run 执行真实同步",
    }


def sync_markdown_dir(
    cfg: DifyConfig,
    markdown_root: Path,
    map_path: Path,
    *,
    dataset_id: str | None = None,
    limit: int | None = None,
    poll_indexing: bool = False,
    poll_seconds: float = 5.0,
    poll_timeout: float = 300.0,
    dry_run: bool = False,
    retries: int = 2,
    indexing_technique: str | None = None,
) -> dict[str, Any]:
    if not markdown_root.exists():
        raise DifyConfigError(f"markdown_root 不存在: {markdown_root}")
    if not markdown_root.is_dir():
        raise DifyConfigError(f"markdown_root 不是目录: {markdown_root}")
    if limit is not None and limit < 0:
        raise DifyConfigError("--limit 不能为负数")
    if dry_run:
        return plan_markdown_sync(markdown_root, map_path, limit=limit)
    dataset_id = dataset_id or cfg.dataset_id
    if not dataset_id:
        raise DifyConfigError("缺少 dataset_id")
    resolved_dataset_id: str = dataset_id
    dataset_info = ensure_dataset_exists(cfg, resolved_dataset_id)
    # Resolve indexing technique: explicit parameter > env var > dataset mode > default economy
    resolved_technique = (
        indexing_technique
        or os.environ.get("DIFY_DATASET_INDEXING", "").strip()
        or dataset_info.get("indexing_technique", "")
        or "economy"
    )
    if resolved_technique not in {"economy", "high_quality"}:
        resolved_technique = "economy"
    # Validate: high_quality requires embedding to be configured on the dataset
    if resolved_technique == "high_quality":
        ds_embedding = dataset_info.get("embedding_model")
        ds_embedding_provider = dataset_info.get("embedding_model_provider")
        if not ds_embedding or not ds_embedding_provider:
            raise DifyConfigError(
                "high_quality 模式需要 embedding provider 已在 Dataset 上配置；"
                "当前 Dataset 未配置 embedding。请先在 Dify 控制台配置 embedding provider。"
            )
    mapping = load_document_map(map_path)
    # Fail-fast: if the map was previously used for a different dataset, refuse to
    # overwrite it. This prevents accidentally syncing v002.6 into the old economy
    # working Dataset or corrupting the old map with new canonical keys.
    mapped_dataset_id = str(mapping.get("dataset_id") or "")
    if mapped_dataset_id and mapped_dataset_id != resolved_dataset_id:
        raise DifyConfigError(
            f"document map 已绑定 Dataset {mapped_dataset_id!r}，"
            f"但目标 Dataset 为 {resolved_dataset_id!r}。"
            "正式库必须使用独立 map（如 data/dify/document-map-v1.json），"
            "禁止复用旧工作库 map 导致跨 Dataset 错绑。"
        )
    docs: dict[str, Any] = mapping.setdefault("documents", {})
    files = sorted(markdown_root.rglob("*.md"))
    if limit is not None:
        files = files[:limit]
    created = 0
    updated = 0
    skipped = 0
    failed: list[dict[str, str]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        meta = _metadata_from_markdown(path, text)
        knowledge_id = str(meta.get("knowledge_id") or path.stem)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = docs.get(knowledge_id)
        if (
            existing
            and existing.get("document_id")
            and existing.get("content_sha256") == digest
        ):
            skipped += 1
            continue
        try:
            if existing and existing.get("document_id"):
                document_id_existing = str(existing["document_id"])

                def _do_update(
                    _dataset_id: str = resolved_dataset_id,
                    _document_id: str = document_id_existing,
                    _name: str = knowledge_id,
                    _text: str = text,
                    _meta: dict[str, Any] = meta,
                ) -> dict[str, Any]:
                    return update_document_by_text(
                        cfg,
                        dataset_id=_dataset_id,
                        document_id=_document_id,
                        name=_name,
                        text=_text,
                        metadata=_meta,
                    )

                result = _with_retries("update", _do_update, retries=retries)
                updated += 1
            else:

                def _do_create(
                    _dataset_id: str = resolved_dataset_id,
                    _name: str = knowledge_id,
                    _text: str = text,
                    _meta: dict[str, Any] = meta,
                    _indexing: str = resolved_technique,
                ) -> dict[str, Any]:
                    return create_document_by_text(
                        cfg,
                        dataset_id=_dataset_id,
                        name=_name,
                        text=_text,
                        metadata=_meta,
                        indexing_technique=_indexing,
                    )

                result = _with_retries("create", _do_create, retries=retries)
                created += 1
            document = result.get("document") or result
            document_id = str(
                document.get("id")
                or (existing or {}).get("document_id")
                or ""
            )
            batch = str(result.get("batch") or document.get("batch") or "")
            docs[knowledge_id] = {
                "document_id": document_id,
                "batch": batch,
                "source_path": str(path),
                "content_sha256": digest,
                "metadata": meta,
                "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            if poll_indexing and batch:
                _wait_indexing(
                    cfg,
                    dataset_id=resolved_dataset_id,
                    batch=batch,
                    timeout=poll_timeout,
                    interval=poll_seconds,
                )
        except DifyApiError as exc:
            # Never include Authorization headers; DifyApiError truncates bodies.
            failed.append({"knowledge_id": knowledge_id, "error": str(exc)})
    mapping["dataset_id"] = resolved_dataset_id
    mapping["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_document_map(map_path, mapping)
    return {
        "dataset_id": resolved_dataset_id,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "map_path": str(map_path),
        "total_mapped": len(docs),
    }


def _wait_indexing(
    cfg: DifyConfig,
    *,
    dataset_id: str,
    batch: str,
    timeout: float,
    interval: float,
) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = get_indexing_status(cfg, dataset_id=dataset_id, batch=batch)
        items = status.get("data") or status.get("documents") or []
        if isinstance(items, list) and items:
            states = {str(item.get("indexing_status") or item.get("status") or "") for item in items}
            if states and states <= {"completed", "error", "paused"}:
                return
        time.sleep(interval)
