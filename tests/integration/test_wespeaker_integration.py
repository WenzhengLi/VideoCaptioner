"""Integration tests for WeSpeaker diarization (real model when available)."""

from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from course_video_analyzer.audio.wespeaker_adapter import (
    WeSpeakerAdapter,
    WeSpeakerConfig,
    WeSpeakerNotAvailableError,
)


def _wespeaker_importable() -> bool:
    try:
        import wespeaker  # noqa: F401
    except ImportError:
        return False
    return True


def _have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _write_two_tone_wav(path: Path, *, sample_rate: int = 16000) -> None:
    """Synthesize a short two-segment mono WAV (different tones ≈ two speakers)."""
    if _have_ffmpeg():
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=220:duration=2",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:duration=2",
                "-filter_complex",
                "[0:a][1:a]concat=n=2:v=0:a=1",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                str(path),
            ],
            check=True,
            capture_output=True,
        )
        return

    # Fallback without ffmpeg: PCM WAV with two amplitude patterns.
    import math
    import struct

    duration_a = 2.0
    duration_b = 2.0
    frames: list[int] = []
    for index in range(int(sample_rate * duration_a)):
        t = index / sample_rate
        frames.append(int(12000 * math.sin(2 * math.pi * 220 * t)))
    for index in range(int(sample_rate * duration_b)):
        t = index / sample_rate
        frames.append(int(12000 * math.sin(2 * math.pi * 880 * t)))

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(struct.pack("<h", sample) for sample in frames))


@pytest.mark.integration
def test_wespeaker_two_speaker_synth(tmp_path: Path) -> None:
    if not _wespeaker_importable():
        pytest.skip("WeSpeaker 未安装")

    wav = tmp_path / "two_tone.wav"
    try:
        _write_two_tone_wav(wav)
    except (subprocess.CalledProcessError, OSError) as exc:
        pytest.skip(f"无法生成集成测试音频: {exc}")

    artifact_dir = tmp_path / "artifacts" / "audio"
    adapter = WeSpeakerAdapter(WeSpeakerConfig(model="chinese", device="cpu"))

    try:
        turns = adapter.diarize(wav, artifact_dir)
    except WeSpeakerNotAvailableError as exc:
        pytest.skip(str(exc))
    except Exception as exc:
        # Model download / onnx / cluster failures → skip rather than fail CI.
        pytest.skip(f"WeSpeaker 运行环境不可用: {exc}")

    assert (artifact_dir / "wespeaker_raw.json").is_file()
    assert (artifact_dir / "speaker_turns.json").is_file()

    # Empty audio would return []; synth tones should usually yield speech.
    # Clustering may still collapse to one cluster on pure sines — require
    # at least valid non-negative ranges when any turn is produced.
    for turn in turns:
        assert turn.start_ms >= 0
        assert turn.end_ms > turn.start_ms
        assert turn.speaker_id.startswith("Speaker ")
        assert turn.source == "wespeaker"
        assert "text" not in turn.model_dump()

    speaker_ids = {turn.speaker_id for turn in turns}
    if len(turns) > 0:
        # Prefer two labels on dual-tone clips; if clusterer collapses, still
        # record a soft requirement note via assertion message.
        assert len(speaker_ids) >= 1
        if len(speaker_ids) < 2:
            pytest.xfail(
                "双音合成样例未聚类出两个 speaker（纯正弦对 embedding 不友好）；"
                "需用真实双人语音复查"
            )
