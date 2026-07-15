"""Named processing profiles and backward-compatible config resolution.

Profiles describe product-level trade-offs.  The pipeline consumes the resolved
configuration and does not need to know which UI or caller selected it.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Mapping

SamplingMode = Literal["fixed", "adaptive"]

DEFAULT_PROCESSING_PROFILE = "complete-v1"


@dataclass(frozen=True)
class ProcessingProfile:
    """Immutable defaults for one supported processing strategy."""

    name: str
    description: str
    defaults: Mapping[str, Any]


def _profile(name: str, description: str, **defaults: Any) -> ProcessingProfile:
    return ProcessingProfile(name, description, MappingProxyType(defaults))


PROCESSING_PROFILES: Mapping[str, ProcessingProfile] = MappingProxyType(
    {
        "complete-v1": _profile(
            "complete-v1",
            "01 版本：固定 5 秒覆盖，优先保留短暂出现的课板内容。",
            sampling_mode="fixed",
            adaptive_sampling=False,
            interval_ms=5_000,
            max_frames=800,
            ocr_dedup_enabled=True,
            ocr_text_similarity_threshold=0.92,
            ocr_image_text_similarity_threshold=0.75,
        ),
        "adaptive-complete": _profile(
            "adaptive-complete",
            "自适应完整度模式：减少 OCR 调用，保守拆分变化区间。",
            sampling_mode="adaptive",
            adaptive_sampling=True,
            interval_ms=5_000,
            max_frames=800,
            adaptive_initial_stride_ms=60_000,
            adaptive_text_similarity_threshold=0.55,
            adaptive_image_difference_threshold=0.45,
            ocr_dedup_enabled=True,
        ),
        "adaptive-balanced": _profile(
            "adaptive-balanced",
            "自适应平衡模式：速度更快，但可能减少短暂课板内容。",
            sampling_mode="adaptive",
            adaptive_sampling=True,
            interval_ms=5_000,
            max_frames=800,
            adaptive_initial_stride_ms=60_000,
            adaptive_text_similarity_threshold=0.45,
            adaptive_image_difference_threshold=0.55,
            ocr_dedup_enabled=True,
        ),
    }
)

_PROFILE_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "01": "complete-v1",
        "complete": "complete-v1",
        "completeness": "complete-v1",
        "stable": "adaptive-complete",
        "balanced": "adaptive-balanced",
    }
)


def get_processing_profile(name: str | None = None) -> ProcessingProfile:
    """Return a profile by canonical name or supported user-facing alias."""

    requested = (name or DEFAULT_PROCESSING_PROFILE).strip().lower()
    canonical = _PROFILE_ALIASES.get(requested, requested)
    try:
        return PROCESSING_PROFILES[canonical]
    except KeyError as exc:
        supported = ", ".join(PROCESSING_PROFILES)
        raise ValueError(f"未知处理模式 {name!r}；可选值: {supported}") from exc


def resolve_processing_config(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Merge profile defaults with caller overrides and normalize legacy keys.

    Existing callers may continue to pass ``adaptive_sampling`` and the older
    ``adaptive_ocr_*`` keys.  New code should prefer ``sampling_mode`` and the
    generic ``ocr_*`` names because OCR de-duplication is shared by both fixed
    and adaptive sampling.
    """

    supplied = dict(config or {})
    profile = get_processing_profile(supplied.get("processing_profile"))
    resolved = dict(profile.defaults)
    resolved.update(supplied)

    if "sampling_mode" in supplied:
        mode = str(supplied["sampling_mode"]).strip().lower()
    elif "adaptive_sampling" in supplied:
        mode = "adaptive" if bool(supplied["adaptive_sampling"]) else "fixed"
    else:
        mode = str(resolved["sampling_mode"])
    if mode not in {"fixed", "adaptive"}:
        raise ValueError("sampling_mode 必须是 'fixed' 或 'adaptive'")

    resolved["processing_profile"] = profile.name
    resolved["sampling_mode"] = mode
    resolved["adaptive_sampling"] = mode == "adaptive"

    if "ocr_dedup_enabled" not in supplied and "adaptive_ocr_dedup" in supplied:
        resolved["ocr_dedup_enabled"] = bool(supplied["adaptive_ocr_dedup"])
    if (
        "ocr_text_similarity_threshold" not in supplied
        and "adaptive_ocr_text_similarity_threshold" in supplied
    ):
        resolved["ocr_text_similarity_threshold"] = supplied[
            "adaptive_ocr_text_similarity_threshold"
        ]
    if (
        "ocr_image_text_similarity_threshold" not in supplied
        and "adaptive_ocr_image_text_similarity_threshold" in supplied
    ):
        resolved["ocr_image_text_similarity_threshold"] = supplied[
            "adaptive_ocr_image_text_similarity_threshold"
        ]
    return resolved
