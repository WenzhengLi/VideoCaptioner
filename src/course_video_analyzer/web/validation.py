"""Validate upload paths, media types, and size limits for the Web layer."""

from __future__ import annotations

from pathlib import Path

ALLOWED_VIDEO_SUFFIXES = frozenset(
    {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mpeg", ".mpg", ".wmv"}
)
# Soft default for local V1; large classroom recordings are common.
DEFAULT_MAX_BYTES = 8 * 1024 * 1024 * 1024  # 8 GiB


class VideoValidationError(ValueError):
    """Raised when a user-supplied media path fails validation."""


def validate_video_path(
    path: str | Path | None,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Path:
    """Return a resolved existing video path or raise ``VideoValidationError``."""
    if path is None or str(path).strip() == "":
        raise VideoValidationError("请先选择或上传视频文件。")

    resolved = Path(path).expanduser()
    try:
        resolved = resolved.resolve(strict=True)
    except FileNotFoundError as exc:
        raise VideoValidationError(f"文件不存在: {path}") from exc
    except OSError as exc:
        raise VideoValidationError(f"无法访问路径: {path}（{exc}）") from exc

    if not resolved.is_file():
        raise VideoValidationError(f"路径不是文件: {resolved}")

    suffix = resolved.suffix.lower()
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_VIDEO_SUFFIXES))
        raise VideoValidationError(f"不支持的文件类型「{suffix}」。允许: {allowed}")

    size = resolved.stat().st_size
    if size <= 0:
        raise VideoValidationError("视频文件为空，请重新选择。")
    if size > max_bytes:
        limit_gb = max_bytes / (1024**3)
        size_gb = size / (1024**3)
        raise VideoValidationError(
            f"文件过大（{size_gb:.2f} GiB），超过上限 {limit_gb:.1f} GiB。"
            "请先用 FFmpeg 压缩或分段后再上传。"
        )
    return resolved
