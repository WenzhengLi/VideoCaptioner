"""FFmpeg/FFprobe based media inspection and conversion."""

from __future__ import annotations

import json
from pathlib import Path

from course_video_analyzer.models import MediaInfo

from .errors import MediaNotFoundError, MediaToolError
from .subprocess_utils import require_tool, run_command


class FFmpegMediaProcessor:
    """Inspect media and extract a 16 kHz mono PCM WAV track."""

    def inspect(self, source: Path) -> MediaInfo:
        source = Path(source)
        if not source.exists():
            raise MediaNotFoundError(f"媒体文件不存在: {source}")
        if not source.is_file():
            raise MediaNotFoundError(f"媒体路径不是文件: {source}")

        ffprobe = require_tool("ffprobe")
        completed = run_command(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
                "-of",
                "json",
                str(source),
            ]
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise MediaToolError(
                "ffprobe 返回了无法解析的 JSON",
                stderr=completed.stdout,
            ) from exc

        streams = payload.get("streams") or []
        fmt = payload.get("format") or {}
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        if video is None and audio is None:
            raise MediaToolError("媒体不包含可用的音视频流", stderr=completed.stdout)

        duration_sec = float(fmt.get("duration") or 0.0)
        if duration_sec <= 0:
            raise MediaToolError("无法读取有效媒体时长", stderr=completed.stdout)

        fps = 0.0
        width = 0
        height = 0
        video_codec = None
        if video is not None:
            width = int(video.get("width") or 0)
            height = int(video.get("height") or 0)
            video_codec = video.get("codec_name")
            fps = _parse_frame_rate(video.get("r_frame_rate"))

        audio_sample_rate = None
        audio_channels = None
        audio_codec = None
        if audio is not None:
            audio_codec = audio.get("codec_name")
            if audio.get("sample_rate"):
                audio_sample_rate = int(audio["sample_rate"])
            if audio.get("channels"):
                audio_channels = int(audio["channels"])

        return MediaInfo(
            source_path=source.resolve(),
            duration_ms=max(1, int(round(duration_sec * 1000))),
            width=width,
            height=height,
            fps=fps,
            has_video=video is not None,
            has_audio=audio is not None,
            audio_sample_rate=audio_sample_rate,
            audio_channels=audio_channels,
            video_codec=video_codec,
            audio_codec=audio_codec,
        )

    def extract_wav(self, source: Path, output_wav: Path) -> Path:
        source = Path(source)
        output_wav = Path(output_wav)
        if not source.exists():
            raise MediaNotFoundError(f"媒体文件不存在: {source}")
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = require_tool("ffmpeg")
        run_command(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(output_wav),
            ]
        )
        if not output_wav.exists() or output_wav.stat().st_size == 0:
            raise MediaToolError(f"音频提取失败，输出为空: {output_wav}")
        return output_wav


def _parse_frame_rate(value: object) -> float:
    if not value:
        return 0.0
    text = str(value)
    if "/" in text:
        num_s, den_s = text.split("/", 1)
        num = float(num_s)
        den = float(den_s)
        if den == 0:
            return 0.0
        return num / den
    try:
        return float(text)
    except ValueError:
        return 0.0
