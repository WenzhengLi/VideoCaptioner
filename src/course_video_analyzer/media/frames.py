"""Preview frame extraction helpers."""

from __future__ import annotations

from pathlib import Path

from course_video_analyzer.models import MediaInfo

from .errors import MediaNotFoundError, MediaToolError
from .subprocess_utils import require_tool, run_command


def extract_preview_frames(
    source: Path,
    output_dir: Path,
    *,
    media: MediaInfo | None = None,
    interval_ms: int = 5000,
    max_frames: int = 60,
    prefix: str = "preview",
) -> list[Path]:
    """Extract JPEG preview frames at a fixed interval."""
    source = Path(source)
    output_dir = Path(output_dir)
    if not source.exists():
        raise MediaNotFoundError(f"媒体文件不存在: {source}")
    if interval_ms <= 0:
        raise ValueError("interval_ms must be > 0")
    if max_frames <= 0:
        raise ValueError("max_frames must be > 0")

    if media is not None and not media.has_video:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(output_dir.glob(f"{prefix}-*.jpg"))
    if existing:
        return existing

    ffmpeg = require_tool("ffmpeg")
    fps = 1000.0 / float(interval_ms)
    pattern = str(output_dir / f"{prefix}-%04d.jpg")
    run_command(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-vf",
            f"fps={fps}",
            "-frames:v",
            str(max_frames),
            "-q:v",
            "2",
            pattern,
        ]
    )
    frames = sorted(output_dir.glob(f"{prefix}-*.jpg"))
    if not frames and (media is None or media.has_video):
        raise MediaToolError(f"未能抽帧，目录为空: {output_dir}")
    return frames
