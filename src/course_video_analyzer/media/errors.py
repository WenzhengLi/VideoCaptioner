"""Media-layer exceptions with actionable messages."""


class MediaError(RuntimeError):
    """Base error for media inspection and conversion."""


class MediaNotFoundError(MediaError):
    """Raised when the source file does not exist."""


class MediaToolError(MediaError):
    """Raised when ffmpeg/ffprobe fails."""

    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        parts = [message]
        if returncode is not None:
            parts.append(f"exit_code={returncode}")
        cleaned = _clean_stderr(stderr)
        if cleaned:
            parts.append(f"stderr={cleaned}")
        super().__init__(" | ".join(parts))


def _clean_stderr(stderr: str, limit: int = 1200) -> str:
    text = " ".join(line.strip() for line in stderr.splitlines() if line.strip())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text
