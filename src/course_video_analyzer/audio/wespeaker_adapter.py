"""WeSpeaker speaker diarization adapter (who spoke when, no transcript text).

Default model: ``chinese`` (WeSpeaker Hub asset ``cnceleb_resnet34``), pinned
with project dependency commit ``dfa741957e5c11f477623b6e583d67d0af25ee88``.

Artifacts (written under ``artifact_dir``, usually ``jobs/<id>/artifacts/audio``):

- ``wespeaker_raw.json`` — raw ``(utt, start, end, label)`` rows
- ``speaker_turns.json`` — normalized ``SpeakerTurn`` list

CUDA note: device selection is validated when loading; this adapter does not
claim CUDA correctness unless the host has a working CUDA torch build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from course_video_analyzer.audio.wespeaker_parser import (
    WeSpeakerParseError,
    parse_wespeaker_raw,
    raw_rows_to_jsonable,
)
from course_video_analyzer.models import SpeakerTurn

WESPEAKER_COMMIT = "dfa741957e5c11f477623b6e583d67d0af25ee88"
RAW_ARTIFACT_NAME = "wespeaker_raw.json"
TURNS_ARTIFACT_NAME = "speaker_turns.json"
DEFAULT_MODEL = "chinese"


class WeSpeakerNotAvailableError(RuntimeError):
    """Raised when the optional WeSpeaker dependency is not installed."""


class WeSpeakerDeviceError(RuntimeError):
    """Raised when the requested CPU/CUDA device cannot be used."""


class WeSpeakerRuntimeError(RuntimeError):
    """Raised when WeSpeaker model load or diarization fails."""


@dataclass
class WeSpeakerConfig:
    """Configurable WeSpeaker load / diarization options."""

    model: str = DEFAULT_MODEL
    device: str = "cpu"
    # Optional absolute/relative path to a downloaded WeSpeaker model directory
    # containing ``avg_model.pt`` + ``config.yaml``. When set, overrides ``model``.
    model_path: Path | str | None = None
    utt: str = "unk"
    diar_min_duration: float = 0.255
    diar_window_secs: float = 1.5
    diar_period_secs: float = 0.75
    diar_frame_shift: int = 10
    diar_batch_size: int = 32
    diar_subseg_cmn: bool = True
    extra_diarization_kwargs: dict[str, Any] = field(default_factory=dict)


class WeSpeakerAdapter:
    """``SpeakerDiarizer`` implementation backed by WeSpeaker.

    The underlying model is loaded lazily and reused across ``diarize`` calls.
    Pass ``model=`` in tests to inject a fake ``diarize()``-compatible object
    (no download / no network).
    """

    def __init__(
        self,
        config: WeSpeakerConfig | None = None,
        *,
        model: Any | None = None,
    ) -> None:
        self.config = config or WeSpeakerConfig()
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

        try:
            raw = model.diarize(str(wav_path), utt=self.config.utt)
        except WeSpeakerDeviceError:
            raise
        except Exception as exc:
            raise WeSpeakerRuntimeError(
                f"WeSpeaker 说话人分离失败 ({wav_path.name}): {exc}"
            ) from exc

        if raw is None:
            raw = []

        self._write_json(artifact_dir / RAW_ARTIFACT_NAME, raw_rows_to_jsonable(raw))
        try:
            turns = parse_wespeaker_raw(raw, source="wespeaker")
        except WeSpeakerParseError:
            raise
        self._write_json(
            artifact_dir / TURNS_ARTIFACT_NAME,
            [turn.model_dump(mode="json") for turn in turns],
        )
        return turns

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model

        load_model = _import_wespeaker_load_model()
        model_ref = self._resolve_model_ref()
        _validate_device(self.config.device)

        try:
            self._model = load_model(model_ref)
        except WeSpeakerDeviceError:
            raise
        except Exception as exc:
            raise WeSpeakerRuntimeError(
                f"WeSpeaker 模型加载失败 (model={model_ref!r}, "
                f"device={self.config.device!r}, commit={WESPEAKER_COMMIT}): {exc}"
            ) from exc

        try:
            if hasattr(self._model, "set_device"):
                self._model.set_device(self.config.device)
            if hasattr(self._model, "set_diarization_params"):
                self._model.set_diarization_params(
                    min_duration=self.config.diar_min_duration,
                    window_secs=self.config.diar_window_secs,
                    period_secs=self.config.diar_period_secs,
                    frame_shift=self.config.diar_frame_shift,
                    batch_size=self.config.diar_batch_size,
                    subseg_cmn=self.config.diar_subseg_cmn,
                    **self.config.extra_diarization_kwargs,
                )
        except WeSpeakerDeviceError:
            raise
        except Exception as exc:
            raise WeSpeakerDeviceError(
                f"WeSpeaker 设备/参数配置失败 (device={self.config.device!r}): {exc}"
            ) from exc

        self._model_loaded = True
        return self._model

    def _resolve_model_ref(self) -> str:
        if self.config.model_path is not None:
            path = Path(self.config.model_path).expanduser().resolve()
            if not path.exists():
                raise FileNotFoundError(f"WeSpeaker 模型路径不存在: {path}")
            return str(path)
        return self.config.model

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def create_default_diarizer(
    config: WeSpeakerConfig | None = None,
) -> WeSpeakerAdapter:
    """Factory used by the pipeline: default diarizer remains WeSpeaker."""
    return WeSpeakerAdapter(config=config)


def _import_wespeaker_load_model() -> Any:
    try:
        import wespeaker
    except ImportError as exc:
        raise WeSpeakerNotAvailableError(
            "未安装 WeSpeaker。请执行 `uv sync --extra audio` 后重试"
            f"（固定 commit {WESPEAKER_COMMIT}）。"
        ) from exc
    if not hasattr(wespeaker, "load_model"):
        raise WeSpeakerNotAvailableError(
            "已安装的 wespeaker 包缺少 load_model；请确认使用项目锁定的 Git 依赖。"
        )
    return wespeaker.load_model


def _validate_device(device: str) -> None:
    if not device or not isinstance(device, str):
        raise WeSpeakerDeviceError(f"非法 device 配置: {device!r}")
    if device == "cpu":
        return
    if not device.startswith("cuda"):
        raise WeSpeakerDeviceError(
            f"不支持的 device={device!r}；请使用 'cpu' 或 'cuda' / 'cuda:N'。"
        )

    try:
        import torch
    except ImportError as exc:
        raise WeSpeakerDeviceError(
            "请求 CUDA 设备但无法导入 torch；请安装 audio extra。"
        ) from exc

    if not torch.cuda.is_available():
        raise WeSpeakerDeviceError(
            f"请求 device={device!r}，但当前环境 torch.cuda.is_available()=False。"
            "请改用 device='cpu'，或安装匹配的 CUDA 版 PyTorch。"
        )

    if ":" in device:
        try:
            index = int(device.split(":", 1)[1])
        except ValueError as exc:
            raise WeSpeakerDeviceError(f"非法 CUDA 设备号: {device!r}") from exc
        count = torch.cuda.device_count()
        if index < 0 or index >= count:
            raise WeSpeakerDeviceError(
                f"请求 device={device!r}，但仅有 {count} 块可见 GPU。"
            )
