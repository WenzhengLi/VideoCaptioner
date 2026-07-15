from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from course_video_analyzer.media.errors import MediaNotFoundError, MediaToolError
from course_video_analyzer.media.ffmpeg import FFmpegMediaProcessor, _parse_frame_rate
from course_video_analyzer.media.subprocess_utils import require_tool


def test_inspect_missing_file(tmp_path: Path) -> None:
    processor = FFmpegMediaProcessor()
    with pytest.raises(MediaNotFoundError):
        processor.inspect(tmp_path / "missing.mp4")


def test_parse_frame_rate() -> None:
    assert _parse_frame_rate("25/1") == 25.0
    assert _parse_frame_rate("30000/1001") == pytest.approx(29.97, rel=1e-3)
    assert _parse_frame_rate(None) == 0.0


def test_inspect_parses_ffprobe_json(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake")
    payload = """
    {
      "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "r_frame_rate": "25/1"},
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": 2}
      ],
      "format": {"duration": "12.5"}
    }
    """
    completed = MagicMock(returncode=0, stdout=payload, stderr="")
    with (
        patch("course_video_analyzer.media.ffmpeg.require_tool", return_value="ffprobe"),
        patch("course_video_analyzer.media.ffmpeg.run_command", return_value=completed),
    ):
        media = FFmpegMediaProcessor().inspect(source)
    assert media.duration_ms == 12500
    assert media.width == 1920
    assert media.has_audio is True


def test_run_command_error_includes_exit_code() -> None:
    from course_video_analyzer.media.subprocess_utils import run_command

    with patch("course_video_analyzer.media.subprocess_utils.subprocess.run") as mocked:
        mocked.return_value = MagicMock(returncode=3, stdout="", stderr="bad input\n")
        with pytest.raises(MediaToolError) as exc:
            run_command(["ffprobe", "x"])
    assert "exit_code=3" in str(exc.value)
    assert "bad input" in str(exc.value)


def test_require_tool_finds_winget_ffmpeg_when_path_is_stale(tmp_path: Path) -> None:
    packages = tmp_path / "Microsoft" / "WinGet" / "Packages"
    ffmpeg = packages / "Gyan.FFmpeg_Test" / "ffmpeg-test" / "bin" / "ffmpeg.exe"
    ffmpeg.parent.mkdir(parents=True)
    ffmpeg.write_bytes(b"")
    with (
        patch("course_video_analyzer.media.subprocess_utils.shutil.which", return_value=None),
        patch("course_video_analyzer.media.subprocess_utils.os.name", "nt"),
        patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}),
    ):
        assert require_tool("ffmpeg") == str(ffmpeg)
