"""Minimal FunASR CAM++ backup diarizer (same ``SpeakerDiarizer`` protocol).

Default production path remains ``WeSpeakerAdapter``. Use this only when
WeSpeaker is unavailable or quality is unacceptable.

Pipeline used (FunASR AutoModel):

- ASR backbone (timestamp carrier): ``paraformer-zh``
- VAD: ``fsmn-vad``
- Speaker: ``cam++`` (``iic/speech_campplus_sv_zh-cn_16k-common``)

Text from ASR is discarded; only speaker intervals are kept as ``SpeakerTurn``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from course_video_analyzer.audio.wespeaker_parser import (
    WeSpeakerParseError,
    parse_wespeaker_raw,
)
from course_video_analyzer.models import SpeakerTurn

RAW_ARTIFACT_NAME = "campplus_raw.json"
TURNS_ARTIFACT_NAME = "speaker_turns.json"


class CampPlusNotAvailableError(RuntimeError):
    """Raised when FunASR (CAM++ path) is not installed."""


class CampPlusDeviceError(RuntimeError):
    """Raised when the requested CPU/CUDA device cannot be used."""


class CampPlusRuntimeError(RuntimeError):
    """Raised when CAM++ / FunASR diarization fails."""


class CampPlusParseError(WeSpeakerParseError):
    """Raised when FunASR+CAM++ raw output cannot be mapped to turns."""


@dataclass
class CampPlusConfig:
    """Minimal CAM++ / FunASR diarization options."""

    model: str = "paraformer-zh"
    vad_model: str | None = "fsmn-vad"
    spk_model: str = "cam++"
    punc_model: str | None = None
    device: str = "cpu"
    cache_dir: Path | None = None
    disable_update: bool = True
    disable_pbar: bool = True
    ncpu: int = 4
    hub: str = "ms"
    sentence_timestamp: bool = True
    extra_model_kwargs: dict[str, Any] = field(default_factory=dict)
    extra_generate_kwargs: dict[str, Any] = field(default_factory=dict)


class CampPlusAdapter:
    """Minimal ``SpeakerDiarizer`` backup using FunASR ``spk_model=cam++``.

    Pass ``model=`` in tests to inject a fake ``generate()``-compatible object.
    """

    def __init__(
        self,
        config: CampPlusConfig | None = None,
        *,
        model: Any | None = None,
    ) -> None:
        self.config = config or CampPlusConfig()
        self._model = model
        self._model_loaded = model is not None

    @property
    def model_loaded(self) -> bool:
        return self._model_loaded

    def diarize(self, wav_path: Path, artifact_dir: Path) -> list[SpeakerTurn]:
        wav_path = Path(wav_path)
        artifact_dir = Path(artifact_dir)
        if not wav_path.is_file():
            raise FileNotFoundError(f"音频文件不存在: {wav_path}")

        artifact_dir.mkdir(parents=True, exist_ok=True)
        model = self._ensure_model()

        generate_kwargs: dict[str, Any] = {
            "sentence_timestamp": self.config.sentence_timestamp,
            **self.config.extra_generate_kwargs,
        }
        try:
            raw = model.generate(input=str(wav_path), **generate_kwargs)
        except Exception as exc:
            raise CampPlusRuntimeError(
                f"CAM++ 说话人分离失败 ({wav_path.name}): {exc}"
            ) from exc

        if raw is None:
            raw = []

        self._write_json(artifact_dir / RAW_ARTIFACT_NAME, _json_safe(raw))
        try:
            turns = parse_campplus_raw(raw)
        except CampPlusParseError:
            raise
        self._write_json(
            artifact_dir / TURNS_ARTIFACT_NAME,
            [turn.model_dump(mode="json") for turn in turns],
        )
        return turns

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        auto_model_cls = _import_automodel()
        _validate_device(self.config.device)

        model_kwargs: dict[str, Any] = {
            "model": self.config.model,
            "device": self.config.device,
            "spk_model": self.config.spk_model,
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
        except CampPlusDeviceError:
            raise
        except Exception as exc:
            raise CampPlusRuntimeError(
                f"CAM++ 模型加载失败 (spk_model={self.config.spk_model!r}, "
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


def parse_campplus_raw(raw: Any) -> list[SpeakerTurn]:
    """Map FunASR+CAM++ ``generate()`` output to speaker turns (text discarded)."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise CampPlusParseError(
            f"CAM++ 原始结果应为 list，实际为 {type(raw).__name__}"
        )
    if not raw:
        return []

    # Prefer dict rows that already look like WeSpeaker tuples after earlier
    # serialization; otherwise build (utt, start_sec, end_sec, label) from
    # sentence_info.spk fields and reuse the shared parser for label stability.
    if raw and isinstance(raw[0], (list, tuple)) and len(raw[0]) >= 4:
        return parse_wespeaker_raw(raw, source="campplus")

    rows: list[tuple[str, float, float, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CampPlusParseError(
                f"CAM++ 结果项[{index}] 应为 dict，实际为 {type(item).__name__}"
            )
        sentence_info = item.get("sentence_info")
        if sentence_info is None:
            # Empty / no speech payload
            continue
        if not isinstance(sentence_info, list):
            raise CampPlusParseError(
                f"CAM++ 结果项[{index}].sentence_info 应为 list，"
                f"实际为 {type(sentence_info).__name__}"
            )
        for s_index, sentence in enumerate(sentence_info):
            path = f"[{index}].sentence_info[{s_index}]"
            if not isinstance(sentence, dict):
                raise CampPlusParseError(
                    f"{path} 应为 dict，实际为 {type(sentence).__name__}"
                )
            if "spk" not in sentence and "speaker" not in sentence:
                raise CampPlusParseError(f"{path} 缺少 spk/speaker 字段")
            label = sentence.get("spk", sentence.get("speaker"))
            start_ms, end_ms = _sentence_ms_range(sentence, path=path)
            # Convert back to seconds for the shared WeSpeaker-shaped parser.
            rows.append(("unk", start_ms / 1000.0, end_ms / 1000.0, label))

    if not rows:
        return []
    return parse_wespeaker_raw(rows, source="campplus")


def _sentence_ms_range(sentence: dict[str, Any], *, path: str) -> tuple[int, int]:
    """FunASR ``sentence_info`` start/end are millisecond timestamps."""
    start_raw = sentence.get("start_ms", sentence.get("start"))
    end_raw = sentence.get("end_ms", sentence.get("end"))
    if start_raw is None or end_raw is None:
        raise CampPlusParseError(f"{path} 缺少 start/end 时间戳")
    try:
        start_ms = int(round(float(start_raw)))
        end_ms = int(round(float(end_raw)))
    except (TypeError, ValueError) as exc:
        raise CampPlusParseError(
            f"{path} 时间戳无法转换为毫秒: start={start_raw!r}, end={end_raw!r}"
        ) from exc
    if start_ms < 0 or end_ms < 0:
        raise CampPlusParseError(
            f"{path} 时间戳不能为负: start_ms={start_ms}, end_ms={end_ms}"
        )
    if end_ms <= start_ms:
        raise CampPlusParseError(
            f"{path} 非法时间戳区间 [start_ms, end_ms)=[{start_ms}, {end_ms})"
        )
    return start_ms, end_ms


def _import_automodel() -> Any:
    try:
        from funasr import AutoModel
    except ImportError as exc:
        raise CampPlusNotAvailableError(
            "未安装 FunASR（CAM++ 备用路径需要 FunASR）。"
            "请执行 `uv sync --extra audio` 后重试。"
        ) from exc
    return AutoModel


def _validate_device(device: str) -> None:
    if not device or not isinstance(device, str):
        raise CampPlusDeviceError(f"非法 device 配置: {device!r}")
    if device == "cpu":
        return
    if not device.startswith("cuda"):
        raise CampPlusDeviceError(
            f"不支持的 device={device!r}；请使用 'cpu' 或 'cuda' / 'cuda:N'。"
        )
    try:
        import torch
    except ImportError as exc:
        raise CampPlusDeviceError(
            "请求 CUDA 设备但无法导入 torch；请安装 audio extra。"
        ) from exc
    if not torch.cuda.is_available():
        raise CampPlusDeviceError(
            f"请求 device={device!r}，但当前环境 torch.cuda.is_available()=False。"
        )
    if ":" in device:
        try:
            index = int(device.split(":", 1)[1])
        except ValueError as exc:
            raise CampPlusDeviceError(f"非法 CUDA 设备号: {device!r}") from exc
        count = torch.cuda.device_count()
        if index < 0 or index >= count:
            raise CampPlusDeviceError(
                f"请求 device={device!r}，但仅有 {count} 块可见 GPU。"
            )


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
