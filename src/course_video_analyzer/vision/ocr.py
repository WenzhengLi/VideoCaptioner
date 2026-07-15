"""PaddleOCR adapter implementing ``BoardOcr``.

Verified stack (CPU, Chinese boards / slides)::

    paddleocr>=3.0  (locked env: 3.7.0)
    lang="ch"
    ocr_version="PP-OCRv4"   # stable; PP-OCRv5/v6 also accepted by 3.x
    text_det_limit_side_len=960
    text_rec_score_thresh=0.0  # keep low-confidence; mark in parser

The real ``PaddleOCR`` class is imported lazily inside ``_ensure_engine``.
Unit tests inject a fake engine with ``predict()`` / ``ocr()`` — no model download.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from course_video_analyzer.models import OcrLine
from course_video_analyzer.vision.enhance import (
    BoardEnhanceMode,
    EnhanceConfig,
    default_enhance_config,
    enhance_board_image,
)
from course_video_analyzer.vision.ocr_parser import (
    apply_corrections,
    board_body_text,
    parse_paddleocr_raw,
)

RAW_ARTIFACT_NAME = "paddleocr_raw.json"
LINES_ARTIFACT_NAME = "ocr_lines.json"
META_ARTIFACT_NAME = "ocr_meta.json"
BODY_ARTIFACT_NAME = "board_body.txt"

DeviceName = Literal["cpu", "gpu", "gpu:0", "gpu:1"]
RawArtifactMode = Literal["compact", "full", "none"]


class PaddleOcrNotAvailableError(RuntimeError):
    """Raised when the optional PaddleOCR dependency is not installed."""


class PaddleOcrRuntimeError(RuntimeError):
    """Raised when PaddleOCR model load or inference fails."""


@dataclass
class OcrConfig:
    """Configurable PaddleOCR load / inference / enhance options."""

    lang: str = "ch"
    device: str = "cpu"
    ocr_version: str | None = "PP-OCRv4"
    confidence_threshold: float = 0.5
    text_det_limit_side_len: int = 960
    text_det_limit_type: str = "max"
    text_rec_score_thresh: float = 0.0
    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False
    use_textline_orientation: bool = False
    merge_same_line: bool = True
    board_mode: BoardEnhanceMode = "electronic"
    enhance: EnhanceConfig | None = None
    skip_enhance: bool = False
    extra_engine_kwargs: dict[str, Any] = field(default_factory=dict)
    extra_predict_kwargs: dict[str, Any] = field(default_factory=dict)
    raw_artifact_mode: RawArtifactMode = "compact"
    prune_raw_larger_than_bytes: int = 16 * 1024 * 1024


class PaddleBoardOcr:
    """``BoardOcr`` implementation backed by PaddleOCR.

    Pass ``engine=`` in tests to inject a fake ``predict()``-compatible object
    (no download). Real engines are constructed lazily on first ``recognize``.
    """

    def __init__(
        self,
        config: OcrConfig | None = None,
        *,
        engine: Any | None = None,
    ) -> None:
        self.config = config or OcrConfig()
        self._engine = engine
        self._engine_loaded = engine is not None

    @property
    def engine_loaded(self) -> bool:
        return self._engine_loaded

    def recognize(self, image_path: Path, artifact_dir: Path) -> list[OcrLine]:
        image_path = Path(image_path)
        artifact_dir = Path(artifact_dir)
        if not image_path.is_file():
            raise FileNotFoundError(f"课板图像不存在: {image_path}")

        artifact_dir.mkdir(parents=True, exist_ok=True)

        cached = self._load_cached_lines(artifact_dir)
        if cached is not None:
            self._prune_oversized_raw(artifact_dir)
            return cached

        ocr_input_path = image_path
        enhance_meta: dict[str, Any] = {"skipped": True}
        if not self.config.skip_enhance:
            enhance_cfg = self.config.enhance or default_enhance_config(
                self.config.board_mode
            )
            enhanced = enhance_board_image(
                image_path,
                artifact_dir,
                config=enhance_cfg,
                save=True,
            )
            if enhanced.enhanced_path is not None:
                ocr_input_path = enhanced.enhanced_path
            enhance_meta = {
                "skipped": False,
                "mode": enhanced.applied.mode,
                "original_path": (
                    str(enhanced.original_copy_path)
                    if enhanced.original_copy_path
                    else None
                ),
                "enhanced_path": (
                    str(enhanced.enhanced_path) if enhanced.enhanced_path else None
                ),
                "apply_clahe": enhanced.applied.apply_clahe,
                "to_grayscale": enhanced.applied.to_grayscale,
                "binarize": enhanced.applied.binarize,
                "denoise": enhanced.applied.denoise,
                "apply_perspective": enhanced.applied.apply_perspective,
            }

        engine = self._ensure_engine()
        predict_kwargs: dict[str, Any] = {
            "text_det_limit_side_len": self.config.text_det_limit_side_len,
            "text_det_limit_type": self.config.text_det_limit_type,
            "text_rec_score_thresh": self.config.text_rec_score_thresh,
            **self.config.extra_predict_kwargs,
        }

        try:
            raw = _call_engine(engine, ocr_input_path, predict_kwargs)
        except PaddleOcrRuntimeError:
            raise
        except Exception as exc:
            raise PaddleOcrRuntimeError(
                f"PaddleOCR 推理失败 ({ocr_input_path.name}): {exc}"
            ) from exc

        if self.config.raw_artifact_mode != "none":
            safe_raw = _json_safe(raw)
            if self.config.raw_artifact_mode == "compact":
                safe_raw = _compact_paddle_raw(safe_raw)
            self._write_json(artifact_dir / RAW_ARTIFACT_NAME, safe_raw)

        lines = parse_paddleocr_raw(
            raw,
            confidence_threshold=self.config.confidence_threshold,
            merge_same_line=self.config.merge_same_line,
        )
        self._write_json(
            artifact_dir / LINES_ARTIFACT_NAME,
            [line.model_dump(mode="json") for line in lines],
        )
        body = board_body_text(lines, prefer_corrected=True)
        (artifact_dir / BODY_ARTIFACT_NAME).write_text(body, encoding="utf-8")
        self._write_json(
            artifact_dir / META_ARTIFACT_NAME,
            {
                "lang": self.config.lang,
                "device": self.config.device,
                "ocr_version": self.config.ocr_version,
                "confidence_threshold": self.config.confidence_threshold,
                "text_det_limit_side_len": self.config.text_det_limit_side_len,
                "source_image": str(image_path),
                "ocr_input_image": str(ocr_input_path),
                "line_count": len(lines),
                "low_confidence_count": sum(1 for line in lines if line.low_confidence),
                "raw_artifact_mode": self.config.raw_artifact_mode,
                "enhance": enhance_meta,
            },
        )
        return lines

    def _load_cached_lines(self, artifact_dir: Path) -> list[OcrLine] | None:
        lines_path = artifact_dir / LINES_ARTIFACT_NAME
        meta_path = artifact_dir / META_ARTIFACT_NAME
        if not lines_path.is_file() or not meta_path.is_file():
            return None
        try:
            payload = json.loads(lines_path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                return None
            return [OcrLine.model_validate(item) for item in payload]
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def _prune_oversized_raw(self, artifact_dir: Path) -> None:
        raw_path = artifact_dir / RAW_ARTIFACT_NAME
        threshold = self.config.prune_raw_larger_than_bytes
        if threshold <= 0 or not raw_path.is_file() or raw_path.stat().st_size <= threshold:
            return
        raw_path.unlink(missing_ok=True)
        meta_path = artifact_dir / META_ARTIFACT_NAME
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        meta["raw_artifact_pruned"] = True
        meta["raw_artifact_prune_threshold_bytes"] = threshold
        self._write_json(meta_path, meta)

    def apply_corrections(
        self,
        lines: list[OcrLine],
        corrections: dict[int, str],
        *,
        artifact_dir: Path | None = None,
    ) -> list[OcrLine]:
        """Human revision helper: fills ``corrected_text`` only."""
        updated = apply_corrections(lines, corrections)
        if artifact_dir is not None:
            artifact_dir = Path(artifact_dir)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            self._write_json(
                artifact_dir / LINES_ARTIFACT_NAME,
                [line.model_dump(mode="json") for line in updated],
            )
            body = board_body_text(updated, prefer_corrected=True)
            (artifact_dir / BODY_ARTIFACT_NAME).write_text(body, encoding="utf-8")
        return updated

    def _ensure_engine(self) -> Any:
        if self._engine is not None:
            return self._engine

        paddle_ocr_cls = _import_paddleocr()
        engine_kwargs: dict[str, Any] = {
            "lang": self.config.lang,
            "device": self.config.device,
            "use_doc_orientation_classify": self.config.use_doc_orientation_classify,
            "use_doc_unwarping": self.config.use_doc_unwarping,
            "use_textline_orientation": self.config.use_textline_orientation,
            "text_det_limit_side_len": self.config.text_det_limit_side_len,
            "text_det_limit_type": self.config.text_det_limit_type,
            "text_rec_score_thresh": self.config.text_rec_score_thresh,
            **self.config.extra_engine_kwargs,
        }
        if self.config.ocr_version is not None:
            engine_kwargs["ocr_version"] = self.config.ocr_version

        try:
            self._engine = paddle_ocr_cls(**engine_kwargs)
        except Exception as exc:
            raise PaddleOcrRuntimeError(
                f"PaddleOCR 模型加载失败 (lang={self.config.lang!r}, "
                f"device={self.config.device!r}, "
                f"ocr_version={self.config.ocr_version!r}): {exc}"
            ) from exc
        self._engine_loaded = True
        return self._engine

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _call_engine(engine: Any, image_path: Path, predict_kwargs: dict[str, Any]) -> Any:
    path_str = str(image_path)
    if hasattr(engine, "predict") and callable(engine.predict):
        try:
            return engine.predict(path_str, **predict_kwargs)
        except TypeError:
            # Fake/legacy engines may only accept the image path.
            return engine.predict(path_str)
    if hasattr(engine, "ocr") and callable(engine.ocr):
        try:
            return engine.ocr(path_str, **predict_kwargs)
        except TypeError:
            return engine.ocr(path_str)
    raise PaddleOcrRuntimeError("OCR engine 缺少 predict()/ocr() 方法")


def _import_paddleocr() -> Any:
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise PaddleOcrNotAvailableError(
            "未安装 PaddleOCR。请执行 `uv sync --extra vision` 后重试。"
        ) from exc
    return PaddleOCR


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
    # PaddleOCR OCRResult / Mapping-like
    if hasattr(value, "keys") and callable(value.keys):
        try:
            keys_raw: Any = value.keys()
            return {str(k): _json_safe(value[k]) for k in keys_raw}
        except Exception:
            pass
    if hasattr(value, "json"):
        try:
            return _json_safe(value.json)
        except Exception:
            pass
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _compact_paddle_raw(value: Any) -> Any:
    """Drop embedded preprocessor images while preserving OCR evidence fields."""
    keep = {
        "input_path",
        "page_index",
        "dt_polys",
        "model_settings",
        "text_det_params",
        "text_type",
        "text_rec_score_thresh",
        "return_word_box",
        "rec_texts",
        "rec_scores",
        "rec_polys",
        "textline_orientation_angles",
        "rec_boxes",
    }
    if isinstance(value, list):
        return [_compact_paddle_raw(item) for item in value]
    if isinstance(value, dict):
        if "rec_texts" in value or "rec_scores" in value:
            return {key: item for key, item in value.items() if key in keep}
        return {key: _compact_paddle_raw(item) for key, item in value.items()}
    return value
