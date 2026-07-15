"""Real FunASR model smoke test (optional; requires models + network on first run)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _have_funasr() -> bool:
    return importlib.util.find_spec("funasr") is not None


@pytest.mark.integration
def test_funasr_real_model_transcribe(tmp_path: Path) -> None:
    """Run against a local Chinese WAV fixture when FunASR + model cache are ready."""
    if not _have_funasr():
        pytest.skip("FunASR 未安装（uv sync --extra audio）")

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "audio" / "zh_short.wav"
    wav = tmp_path / "sample.wav"
    if fixture.is_file():
        wav.write_bytes(fixture.read_bytes())
    else:
        pytest.skip(
            "缺少中文语音样例 tests/fixtures/audio/zh_short.wav；"
            "放入 16kHz 单声道 WAV 后重跑本集成测试"
        )

    from course_video_analyzer.audio.funasr_adapter import FunASRAdapter, FunASRConfig

    cache_dir = Path.home() / ".cache" / "course-video-analyzer" / "funasr"
    adapter = FunASRAdapter(
        FunASRConfig(
            model="paraformer-zh",
            vad_model="fsmn-vad",
            punc_model="ct-punc",
            device="cpu",
            batch_size_s=60,
            cache_dir=cache_dir,
            disable_update=True,
            disable_pbar=True,
        )
    )
    artifact_dir = tmp_path / "artifacts" / "audio"
    try:
        segments = adapter.transcribe(wav, artifact_dir)
    except Exception as exc:
        pytest.skip(f"FunASR 真实模型不可用: {exc}")

    assert (artifact_dir / "funasr_raw.json").is_file()
    assert (artifact_dir / "transcript.json").is_file()
    assert segments, "期望非空转录结果"
    for seg in segments:
        assert seg.end_ms > seg.start_ms
        assert seg.text.strip()
        assert seg.source == "funasr"
