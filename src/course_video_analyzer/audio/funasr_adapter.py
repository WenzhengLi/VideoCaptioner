"""FunASR speech recognition adapter (text + timestamps only, no speakers).

Verified model combination (Chinese course audio, 16 kHz mono WAV)::

    model="paraformer-zh"
    vad_model="fsmn-vad"
    punc_model="ct-punc"

Also accepted as a single hub id (when available locally / on ModelScope)::

    iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch

Cache directory (optional ``FunASRConfig.cache_dir``) maps to ``MODELSCOPE_CACHE``.
Suggested project cache root::

    %USERPROFILE%\\.cache\\course-video-analyzer\\funasr

Long-audio batching is controlled only via ``batch_size_s`` / ``batch_size_threshold_s``
passed into ``AutoModel.generate`` — this adapter does not hard-code chunking.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from course_video_analyzer.audio.funasr_parser import parse_funasr_raw
from course_video_analyzer.models import TranscriptSegment

RAW_ARTIFACT_NAME = "funasr_raw.json"
TRANSCRIPT_ARTIFACT_NAME = "transcript.json"


class FunASRNotAvailableError(RuntimeError):
    """Raised when the optional FunASR dependency is not installed."""


class FunASRRuntimeError(RuntimeError):
    """Raised when FunASR model load or inference fails."""


@dataclass
class FunASRConfig:
    """Configurable FunASR load / inference options."""

    model: str = "paraformer-zh"
    vad_model: str | None = "fsmn-vad"
    punc_model: str | None = "ct-punc"
    device: str = "cpu"
    batch_size_s: int = 300
    batch_size_threshold_s: int | None = None
    cache_dir: Path | None = None
    sentence_timestamp: bool = True
    disable_update: bool = True
    disable_pbar: bool = True
    ncpu: int = 4
    hub: str = "ms"
    extra_model_kwargs: dict[str, Any] = field(default_factory=dict)
    extra_generate_kwargs: dict[str, Any] = field(default_factory=dict)


class FunASRAdapter:
    """``SpeechRecognizer`` implementation backed by FunASR ``AutoModel``.

    The underlying model is loaded lazily and reused across ``transcribe`` calls.
    Pass ``model=`` in tests to inject a fake generate()-compatible object (no download).
    """

    def __init__(
        self,
        config: FunASRConfig | None = None,
        *,
        model: Any | None = None,
    ) -> None:
        self.config = config or FunASRConfig()
        self._model = model
        self._model_loaded = model is not None

    @property
    def model_loaded(self) -> bool:
        return self._model_loaded

    def transcribe(self, wav_path: Path, artifact_dir: Path) -> list[TranscriptSegment]:
        wav_path = Path(wav_path)
        artifact_dir = Path(artifact_dir)
        if not wav_path.is_file():
            raise FileNotFoundError(f"音频文件不存在: {wav_path}")

        artifact_dir.mkdir(parents=True, exist_ok=True)
        model = self._ensure_model()

        generate_kwargs: dict[str, Any] = {
            "batch_size_s": self.config.batch_size_s,
            "sentence_timestamp": self.config.sentence_timestamp,
            **self.config.extra_generate_kwargs,
        }
        if self.config.batch_size_threshold_s is not None:
            generate_kwargs["batch_size_threshold_s"] = self.config.batch_size_threshold_s

        try:
            raw = model.generate(input=str(wav_path), **generate_kwargs)
        except Exception as exc:
            raise FunASRRuntimeError(
                f"FunASR 推理失败 ({wav_path.name}): {exc}"
            ) from exc

        self._write_json(artifact_dir / RAW_ARTIFACT_NAME, _json_safe(raw))
        segments = parse_funasr_raw(raw)
        self._write_json(
            artifact_dir / TRANSCRIPT_ARTIFACT_NAME,
            [seg.model_dump(mode="json") for seg in segments],
        )
        return segments

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        auto_model_cls = _import_automodel()
        model_kwargs: dict[str, Any] = {
            "model": self.config.model,
            "device": self.config.device,
            "disable_update": self.config.disable_update,
            "disable_pbar": self.config.disable_pbar,
            "ncpu": self.config.ncpu,
            "hub": self.config.hub,
            **self.config.extra_model_kwargs,
        }
        if self.config.vad_model is not None:
            model_kwargs["vad_model"] = self.config.vad_model
        if self.config.punc_model is not None:
            model_kwargs["punc_model"] = self.config.punc_model

        if self.config.cache_dir is not None:
            cache_dir = Path(self.config.cache_dir).expanduser().resolve()
            cache_dir.mkdir(parents=True, exist_ok=True)
            os.environ["MODELSCOPE_CACHE"] = str(cache_dir)

        try:
            self._model = auto_model_cls(**model_kwargs)
        except Exception as exc:
            raise FunASRRuntimeError(
                f"FunASR 模型加载失败 (model={self.config.model!r}, "
                f"device={self.config.device!r}): {exc}"
            ) from exc
        self._model_loaded = True
        return self._model

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _import_automodel() -> Any:
    try:
        from funasr import AutoModel
    except ImportError as exc:
        raise FunASRNotAvailableError(
            "未安装 FunASR。请执行 `uv sync --extra audio` 后重试。"
        ) from exc
    return AutoModel


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist())
        except Exception:
            return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)
