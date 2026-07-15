from pathlib import Path
import shutil
import subprocess

import pytest

from course_video_analyzer.media.ffmpeg import FFmpegMediaProcessor
from course_video_analyzer.media.frames import extract_preview_frames


def _have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.mark.integration
def test_inspect_and_extract_synth_video(tmp_path: Path) -> None:
    if not _have_ffmpeg():
        pytest.skip("ffmpeg/ffprobe 不可用")

    video = tmp_path / "synth.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x240:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=2",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(video),
        ],
        check=True,
        capture_output=True,
    )

    processor = FFmpegMediaProcessor()
    media = processor.inspect(video)
    assert media.duration_ms >= 1000
    assert media.width == 320
    assert media.has_audio

    wav = tmp_path / "audio.wav"
    processor.extract_wav(video, wav)
    assert wav.exists() and wav.stat().st_size > 0

    frames_dir = tmp_path / "frames"
    frames = extract_preview_frames(video, frames_dir, media=media, interval_ms=1000, max_frames=3)
    assert frames
    # Re-run should skip regeneration
    again = extract_preview_frames(video, frames_dir, media=media, interval_ms=1000, max_frames=3)
    assert again == frames
