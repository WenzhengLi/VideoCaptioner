"""Offline unit tests for FunASR adapter/parser (fake model, no network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from course_video_analyzer.audio.funasr_adapter import (
    FunASRAdapter,
    FunASRConfig,
    FunASRNotAvailableError,
    FunASRRuntimeError,
)
from course_video_analyzer.audio.funasr_parser import (
    FunASRParseError,
    normalize_transcript_text,
    parse_funasr_raw,
)


class FakeFunASRModel:
    """Minimal stand-in for FunASR AutoModel.generate()."""

    def __init__(self, result: Any = None, *, error: Exception | None = None) -> None:
        self.result = result if result is not None else []
        self.error = error
        self.generate_calls: list[dict[str, Any]] = []

    def generate(self, input: str, **kwargs: Any) -> Any:
        self.generate_calls.append({"input": input, **kwargs})
        if self.error is not None:
            raise self.error
        if callable(self.result):
            return self.result(input, **kwargs)
        return self.result


def _sample_raw() -> list[dict[str, Any]]:
    return [
        {
            "key": "clip",
            "text": "我们先看一下课板上的这个公式。下一页。",
            "sentence_info": [
                {
                    "text": "我们先看一下课板上的这个公式。",
                    "raw_text": "我们 先 看 一下 课板 上 的 这个 公式",
                    "start": 35200,
                    "end": 42800,
                    "confidence": 0.93,
                    "timestamp": [[35200, 36000], [36000, 42800]],
                },
                {
                    "text": "下一页。",
                    "start": 43000,
                    "end": 45000,
                    "score": 0.88,
                },
                {
                    "text": "   ",
                    "start": 45000,
                    "end": 46000,
                },
            ],
        }
    ]


def test_normalize_transcript_text_collapses_whitespace() -> None:
    assert normalize_transcript_text("  你好\t世界\n  ") == "你好 世界"
    assert normalize_transcript_text("全角　空格") == "全角 空格"


def test_parse_sentence_info_sorted_and_filters_empty() -> None:
    raw = [
        {
            "text": "B。A。",
            "sentence_info": [
                {"text": "B。", "start": 2000, "end": 3000},
                {"text": "A。", "start": 0, "end": 1000},
                {"text": "。。", "start": 3000, "end": 4000},
            ],
        }
    ]
    segments = parse_funasr_raw(raw)
    assert [s.text for s in segments] == ["A。", "B。"]
    assert segments[0].start_ms == 0
    assert segments[0].source == "funasr"
    assert "speaker" not in segments[0].model_dump()


def test_parse_empty_results() -> None:
    assert parse_funasr_raw([]) == []
    assert parse_funasr_raw([{"text": "", "timestamp": []}]) == []
    assert parse_funasr_raw([{"text": "   ", "sentence_info": []}]) == []


def test_parse_illegal_timestamps_raises() -> None:
    with pytest.raises(FunASRParseError, match="非法时间戳"):
        parse_funasr_raw(
            [{"sentence_info": [{"text": "你好", "start": 1000, "end": 1000}]}]
        )
    with pytest.raises(FunASRParseError, match="不能为负"):
        parse_funasr_raw(
            [{"sentence_info": [{"text": "你好", "start": -1, "end": 1000}]}]
        )
    with pytest.raises(FunASRParseError, match="应为 list"):
        parse_funasr_raw({"text": "x"})


def test_parse_unexpected_structure_raises() -> None:
    with pytest.raises(FunASRParseError, match="缺少 sentence_info 或 text"):
        parse_funasr_raw([{"key": "only"}])


def test_parse_utterance_fallback_from_timestamp() -> None:
    segments = parse_funasr_raw(
        [
            {
                "text": "你好世界",
                "timestamp": [[10, 50], [50, 120]],
                "confidence": 91,
            }
        ]
    )
    assert len(segments) == 1
    assert segments[0].start_ms == 10
    assert segments[0].end_ms == 120
    assert segments[0].confidence == pytest.approx(0.91)
    assert segments[0].raw_text == "你好世界"


def test_adapter_transcribe_writes_artifacts(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF")
    artifact_dir = tmp_path / "artifacts" / "audio"
    fake = FakeFunASRModel(_sample_raw())
    adapter = FunASRAdapter(model=fake)

    segments = adapter.transcribe(wav, artifact_dir)

    assert len(segments) == 2
    assert segments[0].text == "我们先看一下课板上的这个公式。"
    assert segments[0].raw_text == "我们 先 看 一下 课板 上 的 这个 公式"
    assert segments[0].confidence == pytest.approx(0.93)
    assert segments[0].start_ms == 35200
    assert segments[0].end_ms == 42800

    raw_path = artifact_dir / "funasr_raw.json"
    transcript_path = artifact_dir / "transcript.json"
    assert raw_path.is_file()
    assert transcript_path.is_file()
    dumped = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert dumped[0]["start_ms"] == 35200
    assert dumped[0]["source"] == "funasr"
    assert "speaker" not in dumped[0]

    assert fake.generate_calls
    assert fake.generate_calls[0]["sentence_timestamp"] is True
    assert fake.generate_calls[0]["batch_size_s"] == 300


def test_adapter_reuses_injected_model(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    fake = FakeFunASRModel([{"text": "一", "timestamp": [[0, 100]]}])
    adapter = FunASRAdapter(model=fake)
    adapter.transcribe(wav, tmp_path / "out1")
    adapter.transcribe(wav, tmp_path / "out2")
    assert len(fake.generate_calls) == 2
    assert adapter.model_loaded is True


def test_adapter_model_exception(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    adapter = FunASRAdapter(model=FakeFunASRModel(error=RuntimeError("boom")))
    with pytest.raises(FunASRRuntimeError, match="推理失败"):
        adapter.transcribe(wav, tmp_path / "out")


def test_adapter_propagates_parse_error(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    bad = [{"sentence_info": [{"text": "坏", "start": 5, "end": 1}]}]
    adapter = FunASRAdapter(model=FakeFunASRModel(bad))
    with pytest.raises(FunASRParseError, match="非法时间戳"):
        adapter.transcribe(wav, tmp_path / "out")
    # Raw artifact is still written for debugging
    assert (tmp_path / "out" / "funasr_raw.json").is_file()


def test_adapter_missing_wav(tmp_path: Path) -> None:
    adapter = FunASRAdapter(model=FakeFunASRModel([]))
    with pytest.raises(FileNotFoundError):
        adapter.transcribe(tmp_path / "missing.wav", tmp_path / "out")


def test_adapter_empty_model_result(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    adapter = FunASRAdapter(model=FakeFunASRModel([]))
    assert adapter.transcribe(wav, tmp_path / "out") == []
    assert json.loads((tmp_path / "out" / "transcript.json").read_text("utf-8")) == []


def test_import_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def blocked(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "funasr" or name.startswith("funasr."):
            raise ImportError("No module named funasr")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    adapter = FunASRAdapter(FunASRConfig(model="paraformer-zh"))
    with pytest.raises(FunASRNotAvailableError, match="uv sync --extra audio"):
        adapter._ensure_model()


def test_config_batch_size_passed(tmp_path: Path) -> None:
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    fake = FakeFunASRModel([{"text": "测", "timestamp": [[0, 10]]}])
    adapter = FunASRAdapter(
        FunASRConfig(batch_size_s=60, batch_size_threshold_s=20),
        model=fake,
    )
    adapter.transcribe(wav, tmp_path / "out")
    assert fake.generate_calls[0]["batch_size_s"] == 60
    assert fake.generate_calls[0]["batch_size_threshold_s"] == 20
