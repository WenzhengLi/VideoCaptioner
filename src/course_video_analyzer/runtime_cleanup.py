"""Safe cleanup helpers for disposable benchmark and visual-run artifacts."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

DISPOSABLE_ARTIFACT_DIRS = frozenset(
    {
        "_frame_cache",
        "artifacts",
        "boards",
        "frames",
        "ocr",
        "ocr_cache",
        "ocr_probes",
        "probes",
        "tracked",
    }
)


@dataclass(frozen=True)
class CleanupReport:
    removed_paths: tuple[str, ...]
    removed_bytes: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_text_output(path: Path) -> Path:
    """Require a non-empty UTF-8 text output before disposable data is removed."""

    resolved = Path(path).resolve()
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise RuntimeError(f"最终 TXT 不存在或为空，拒绝清理中间产物: {resolved}")
    resolved.read_text(encoding="utf-8")
    return resolved


def validate_json_output(path: Path) -> Path:
    """Require a readable non-empty JSON output before cleanup."""

    resolved = Path(path).resolve()
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise RuntimeError(f"最终 JSON 不存在或为空，拒绝清理中间产物: {resolved}")
    json.loads(resolved.read_text(encoding="utf-8"))
    return resolved


def cleanup_disposable_artifacts(
    output_dir: Path,
    *,
    directory_names: Iterable[str] = DISPOSABLE_ARTIFACT_DIRS,
) -> CleanupReport:
    """Remove only known generated child directories below ``output_dir``.

    The output directory itself and unrelated files are never deleted.  Each
    resolved child is checked to remain directly below the requested root.
    """

    root = Path(output_dir).resolve()
    if root == Path(root.anchor) or not root.is_dir():
        raise ValueError(f"清理目录无效: {root}")

    removed: list[str] = []
    removed_bytes = 0
    for name in sorted(set(directory_names)):
        if not name or Path(name).name != name:
            raise ValueError(f"只允许清理直接子目录名称: {name!r}")
        child = (root / name).resolve()
        if child.parent != root:
            raise ValueError(f"清理目标越界: {child}")
        if not child.exists():
            continue
        if not child.is_dir():
            raise ValueError(f"预期清理目录但发现文件: {child}")
        removed_bytes += _directory_size(child)
        shutil.rmtree(child)
        removed.append(str(child))
    return CleanupReport(tuple(removed), removed_bytes)


def _directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except FileNotFoundError:
            continue
    return total
