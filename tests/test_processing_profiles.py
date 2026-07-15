from __future__ import annotations

import pytest

from course_video_analyzer.processing_profiles import resolve_processing_config


def test_default_profile_restores_01_complete_fixed_sampling() -> None:
    config = resolve_processing_config()

    assert config["processing_profile"] == "complete-v1"
    assert config["sampling_mode"] == "fixed"
    assert config["adaptive_sampling"] is False
    assert config["interval_ms"] == 5_000
    assert config["max_frames"] == 800
    assert config["ocr_dedup_enabled"] is True


def test_explicit_legacy_adaptive_switch_remains_supported() -> None:
    config = resolve_processing_config({"adaptive_sampling": True})

    assert config["sampling_mode"] == "adaptive"
    assert config["adaptive_sampling"] is True


def test_profile_alias_and_caller_overrides() -> None:
    config = resolve_processing_config(
        {"processing_profile": "01", "interval_ms": 2_500, "max_frames": 1_200}
    )

    assert config["processing_profile"] == "complete-v1"
    assert config["interval_ms"] == 2_500
    assert config["max_frames"] == 1_200


def test_legacy_ocr_dedup_keys_are_normalized() -> None:
    config = resolve_processing_config(
        {
            "adaptive_ocr_dedup": False,
            "adaptive_ocr_text_similarity_threshold": 0.81,
            "adaptive_ocr_image_text_similarity_threshold": 0.72,
        }
    )

    assert config["ocr_dedup_enabled"] is False
    assert config["ocr_text_similarity_threshold"] == 0.81
    assert config["ocr_image_text_similarity_threshold"] == 0.72


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="未知处理模式"):
        resolve_processing_config({"processing_profile": "missing"})
