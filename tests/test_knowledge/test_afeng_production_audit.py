"""Unit tests for the Afeng production audit script.

Uses mock/fixture, does not depend on real Dify.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audit_afeng_production import (
    CANONICAL_RE,
    _check_aggregate,
    _check_bundle,
    _check_map,
    _check_reports,
)


@pytest.fixture()
def good_manifest(tmp_path: Path) -> Path:
    """Create a minimal valid bundle manifest."""
    import hashlib

    docs = []
    for i in range(36):
        course = f"C{(i // 2) + 1:03d}"
        case_num = (i % 2) + 1
        case_id = f"CASE-{course}-{case_num:03d}"
        doc_path = tmp_path / f"AFENG-{course}-{case_id}.md"
        content = (
            f"---\nknowledge_id: \"AFENG-{course}-{case_id}\"\n"
            f"course_id: \"{course}\"\ncase_id: \"{case_id}\"\n"
            f"source_start_ms: 1000\nsource_end_ms: 2000\n"
            f"evidence_ids:\n  - \"SEG-{course}-000001\"\n---\n"
            f"# Test Method\n\n## 来源证据\n\n- `[SEG-{course}-000001]` test\n"
        )
        doc_path.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        docs.append({
            "knowledge_id": f"AFENG-{course}-{case_id}",
            "course_id": course,
            "case_id": case_id,
            "model": "test-model",
            "run_token": "abc123",
            "input_hash": "hash123",
            "source_summary": "/path/to/summary.json",
            "content_sha256": digest,
            "document_path": str(doc_path),
        })
    excluded = [
        {"course_id": "C006", "case_id": "CASE-C006-001", "status": "manual_review"},
        {"course_id": "C008", "case_id": "CASE-C008-002", "status": "manual_review"},
        {"course_id": "C014", "case_id": "CASE-C014-001", "status": "rejected"},
        {"course_id": "C015", "case_id": "CASE-C015-001", "status": "rejected"},
    ]
    manifest = {"documents": docs, "excluded": excluded}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@pytest.fixture()
def good_aggregate(tmp_path: Path) -> Path:
    """Create a minimal valid aggregate report."""
    agg = {
        "case_count": 40,
        "failure_count": 0,
        "status": "complete",
        "status_counts": {"published": 36, "manual_review": 2, "rejected": 2},
    }
    path = tmp_path / "afeng-twenty-course-v002.json"
    path.write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_check_bundle_pass(good_manifest: Path) -> None:
    result = _check_bundle(good_manifest)
    assert result["status"] == "PASS"


def test_check_bundle_missing_file(tmp_path: Path) -> None:
    result = _check_bundle(tmp_path / "nonexistent.json")
    assert result["status"] == "FAIL"


def test_check_bundle_hash_mismatch(good_manifest: Path) -> None:
    """Tamper with one document's hash."""
    manifest = json.loads(good_manifest.read_text(encoding="utf-8"))
    manifest["documents"][0]["content_sha256"] = "0" * 64
    good_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    result = _check_bundle(good_manifest)
    assert result["status"] == "FAIL"
    assert result["checks"]["content_hash_match"] is False


def test_check_bundle_non_canonical_id(good_manifest: Path) -> None:
    """Replace one ID with non-canonical."""
    manifest = json.loads(good_manifest.read_text(encoding="utf-8"))
    manifest["documents"][0]["knowledge_id"] = "KNOW-C001-001"
    good_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    result = _check_bundle(good_manifest)
    assert result["status"] == "FAIL"
    assert result["checks"]["canonical_format"] is False


def test_check_aggregate_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Create aggregate at expected relative path and check."""
    agg_dir = tmp_path / "docs" / "evaluation"
    agg_dir.mkdir(parents=True)
    agg = {
        "case_count": 40,
        "failure_count": 0,
        "status": "complete",
        "status_counts": {"published": 36, "manual_review": 2, "rejected": 2},
    }
    (agg_dir / "afeng-twenty-course-v002.json").write_text(
        json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    result = _check_aggregate()
    assert result["status"] == "PASS"


def test_check_aggregate_wrong_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agg_dir = tmp_path / "docs" / "evaluation"
    agg_dir.mkdir(parents=True)
    agg = {
        "case_count": 40,
        "failure_count": 0,
        "status": "complete",
        "status_counts": {"published": 35, "manual_review": 2, "rejected": 2},
    }
    (agg_dir / "afeng-twenty-course-v002.json").write_text(
        json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    result = _check_aggregate()
    assert result["status"] == "FAIL"


def test_check_map_pass(tmp_path: Path) -> None:
    docs = {}
    for i in range(36):
        course = f"C{(i // 2) + 1:03d}"
        case_num = (i % 2) + 1
        kid = f"AFENG-{course}-CASE-{course}-{case_num:03d}"
        docs[kid] = {"document_id": f"doc-{i}", "content_sha256": "a" * 64}
    mapping = {"schema_version": "1.0", "dataset_id": "ds-1", "documents": docs}
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    result = _check_map(map_path, "ds-1")
    assert result["status"] == "PASS"


def test_check_map_wrong_dataset_id(tmp_path: Path) -> None:
    docs = {}
    for i in range(36):
        course = f"C{(i // 2) + 1:03d}"
        case_num = (i % 2) + 1
        kid = f"AFENG-{course}-CASE-{course}-{case_num:03d}"
        docs[kid] = {"document_id": f"doc-{i}", "content_sha256": "a" * 64}
    mapping = {"schema_version": "1.0", "dataset_id": "ds-wrong", "documents": docs}
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    result = _check_map(map_path, "ds-1")
    assert result["status"] == "FAIL"
    assert result["checks"]["dataset_id_match"] is False


def test_check_map_smoke_key(tmp_path: Path) -> None:
    docs = {"KNOW-SMOKE-001": {"document_id": "doc-0", "content_sha256": "a" * 64}}
    for i in range(35):
        course = f"C{(i // 2) + 1:03d}"
        case_num = (i % 2) + 1
        kid = f"AFENG-{course}-CASE-{course}-{case_num:03d}"
        docs[kid] = {"document_id": f"doc-{i+1}", "content_sha256": "a" * 64}
    mapping = {"schema_version": "1.0", "dataset_id": "ds-1", "documents": docs}
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    result = _check_map(map_path, "ds-1")
    assert result["status"] == "FAIL"
    assert result["checks"]["no_smoke"] is False


def test_check_reports_no_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = _check_reports()
    assert result["status"] == "FAIL"


def test_check_reports_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    # Create retrieval report
    retrieval = {
        "document_dedup_top5": {"accuracy": 90.0, "correct": 18, "total": 20},
        "accuracy": 90.0,
    }
    (tmp_path / "data" / "dify").mkdir(parents=True)
    (tmp_path / "data" / "dify" / "afeng-retrieval-report.json").write_text(
        json.dumps(retrieval), encoding="utf-8"
    )
    # Create app acceptance report
    app_report = {"passed": 20, "total": 20, "correct": 20}
    (tmp_path / "data" / "dify" / "afeng-app-acceptance-report.json").write_text(
        json.dumps(app_report), encoding="utf-8"
    )
    result = _check_reports()
    assert result["status"] == "PASS"


def test_canonical_re() -> None:
    assert CANONICAL_RE.match("AFENG-C001-CASE-C001-001")
    assert CANONICAL_RE.match("AFENG-C020-CASE-C020-003")
    assert not CANONICAL_RE.match("KNOW-C001-001")
    assert not CANONICAL_RE.match("afeng-method-C016-001")
    assert not CANONICAL_RE.match("AFENG-C001-CASE-C001-001-extra")
