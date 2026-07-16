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
from typing import Any


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
        detail = exc.read().decode("utf-8", errors="replace")
        raise DifyApiError(f"Dify API {method} {path} -> HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise DifyApiError(f"Dify API 不可达 {url}: {exc}") from exc


def create_dataset(cfg: DifyConfig, name: str, *, description: str = "") -> dict[str, Any]:
    return _request(
        cfg,
        "POST",
        "/datasets",
        payload={
            "name": name,
            "description": description,
            "indexing_technique": "high_quality",
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
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "text": text,
        "indexing_technique": "high_quality",
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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    return meta


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
) -> dict[str, Any]:
    dataset_id = dataset_id or cfg.dataset_id
    if not dataset_id:
        raise DifyConfigError("缺少 dataset_id")
    mapping = load_document_map(map_path)
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
                result = update_document_by_text(
                    cfg,
                    dataset_id=dataset_id,
                    document_id=str(existing["document_id"]),
                    name=knowledge_id,
                    text=text,
                    metadata=meta,
                )
                updated += 1
            else:
                result = create_document_by_text(
                    cfg,
                    dataset_id=dataset_id,
                    name=knowledge_id,
                    text=text,
                    metadata=meta,
                )
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
                _wait_indexing(cfg, dataset_id=dataset_id, batch=batch, timeout=poll_timeout, interval=poll_seconds)
        except DifyApiError as exc:
            failed.append({"knowledge_id": knowledge_id, "error": str(exc)})
    mapping["dataset_id"] = dataset_id
    mapping["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_document_map(map_path, mapping)
    return {
        "dataset_id": dataset_id,
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
