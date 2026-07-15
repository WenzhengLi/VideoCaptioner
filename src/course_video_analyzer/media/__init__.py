"""Media inspection, audio extraction, and frame sampling."""

from .errors import MediaError, MediaNotFoundError, MediaToolError
from .ffmpeg import FFmpegMediaProcessor
from .frames import extract_preview_frames

__all__ = [
    "FFmpegMediaProcessor",
    "MediaError",
    "MediaNotFoundError",
    "MediaToolError",
    "extract_preview_frames",
]
