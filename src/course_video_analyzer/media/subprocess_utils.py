"""Shared subprocess helpers for ffmpeg/ffprobe."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .errors import MediaToolError


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None and _is_windows():
        path = _find_winget_ffmpeg_tool(name)
    if path is None:
        raise MediaToolError(
            f"未找到系统工具 `{name}`。请安装 FFmpeg 并确保 `{name}` 在 PATH 中。"
            " Windows 可用: winget install Gyan.FFmpeg"
        )
    return path


def _is_windows() -> bool:
    """Isolate the platform check so tests never mutate global ``os.name``."""

    return os.name == "nt"


def _find_winget_ffmpeg_tool(name: str) -> str | None:
    """Find Gyan.FFmpeg installed by WinGet even when PATH is stale.

    WinGet commonly installs FFmpeg successfully but the current desktop
    process keeps its old PATH until it is restarted.  Local Web processing
    should still work in that same session.
    """
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not packages.is_dir():
        return None
    executable = name if name.lower().endswith(".exe") else f"{name}.exe"
    patterns = (
        f"Gyan.FFmpeg_*/*/bin/{executable}",
        f"Gyan.FFmpeg_*/**/bin/{executable}",
    )
    for pattern in patterns:
        for candidate in packages.glob(pattern):
            if candidate.is_file():
                return str(candidate)
    return None


def run_command(cmd: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaToolError(
            f"命令超时: {' '.join(cmd[:4])}...",
            stderr=str(exc),
        ) from exc
    if completed.returncode != 0:
        raise MediaToolError(
            f"命令失败: {Path(cmd[0]).name} {' '.join(cmd[1:6])}",
            returncode=completed.returncode,
            stderr=completed.stderr or completed.stdout,
        )
    return completed
