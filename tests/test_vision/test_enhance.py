"""Unit tests for board-image enhancement (no OCR models)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from course_video_analyzer.vision.enhance import (
    EnhanceConfig,
    apply_clahe,
    binarize_image,
    default_enhance_config,
    denoise_image,
    enhance_board_image,
    perspective_correct,
    to_grayscale_bgr,
)


def _write_bgr(path: Path, image: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), image)
    return path


def _colored_slide(h: int = 240, w: int = 320) -> np.ndarray:
    """Synthetic electronic slide with vivid BGR colours."""
    image = np.full((h, w, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 30), (180, 90), (40, 40, 220), thickness=-1)  # red-ish
    cv2.rectangle(image, (40, 120), (280, 200), (40, 180, 40), thickness=-1)  # green
    cv2.putText(
        image,
        "Slide",
        (50, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return image


def test_default_enhance_config_electronic_preserves_colour() -> None:
    cfg = default_enhance_config("electronic")
    assert cfg.mode == "electronic"
    assert cfg.apply_clahe is False
    assert cfg.to_grayscale is False
    assert cfg.binarize is False
    assert cfg.denoise is False
    assert cfg.apply_perspective is False


def test_default_enhance_config_blackboard_enables_pipeline() -> None:
    cfg = default_enhance_config("blackboard")
    assert cfg.apply_clahe is True
    assert cfg.to_grayscale is True
    assert cfg.binarize is True
    assert cfg.denoise is True
    assert cfg.apply_perspective is True


@pytest.mark.parametrize("mode", ["whiteboard", "physical"])
def test_default_enhance_config_whiteboard_physical(mode: str) -> None:
    cfg = default_enhance_config(mode)  # type: ignore[arg-type]
    assert cfg.to_grayscale is True
    assert cfg.binarize is True
    assert cfg.denoise is True


def test_electronic_enhance_keeps_colour_channels(tmp_path: Path) -> None:
    src = _write_bgr(tmp_path / "slide.png", _colored_slide())
    result = enhance_board_image(src, tmp_path / "out", config=default_enhance_config("electronic"))
    assert result.image.ndim == 3
    assert result.image.shape[2] == 3
    # Colour regions must not collapse to grey (B≈G≈R).
    patch = result.image[40:80, 40:160]
    channel_spread = float(np.std(patch.astype(np.float32), axis=2).mean())
    assert channel_spread > 15.0
    assert result.enhanced_path is not None
    assert result.original_copy_path is not None
    assert result.enhanced_path.is_file()
    assert result.original_copy_path.is_file()


def test_electronic_with_default_none_refuses_destructive_stack(tmp_path: Path) -> None:
    """When config is omitted, mode defaults to electronic without grey/CLAHE/bin."""
    src = _write_bgr(tmp_path / "slide.png", _colored_slide())
    result = enhance_board_image(src, tmp_path / "out")
    assert result.applied.mode == "electronic"
    assert result.applied.apply_clahe is False
    assert result.applied.to_grayscale is False
    assert result.applied.binarize is False


def test_perspective_correct_produces_rectangular_output() -> None:
    h, w = 200, 300
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    # Skewed white quad on dark background.
    src_pts = np.array([[40, 30], [260, 20], [280, 170], [30, 180]], dtype=np.int32)
    cv2.fillConvexPoly(canvas, src_pts, (240, 240, 240))
    corners = [(40.0, 30.0), (260.0, 20.0), (280.0, 170.0), (30.0, 180.0)]
    warped = perspective_correct(canvas, corners)
    assert warped.ndim == 3
    assert warped.shape[0] >= 100
    assert warped.shape[1] >= 100
    # Most pixels should be bright after warp (filled region dominates).
    assert float(warped.mean()) > 80.0


def test_enhance_with_corners_applies_perspective(tmp_path: Path) -> None:
    canvas = np.full((220, 320, 3), 30, dtype=np.uint8)
    corners = [(50.0, 40.0), (270.0, 35.0), (290.0, 190.0), (40.0, 200.0)]
    src_pts = np.array(corners, dtype=np.int32)
    cv2.fillConvexPoly(canvas, src_pts, (220, 220, 220))
    src = _write_bgr(tmp_path / "skew.png", canvas)
    cfg = EnhanceConfig(mode="physical", apply_clahe=False, to_grayscale=False, binarize=False, denoise=False)
    result = enhance_board_image(
        src,
        tmp_path / "out",
        config=cfg,
        corners=corners,
    )
    assert result.applied.apply_perspective is True
    assert result.applied.corners is not None
    assert result.image.shape[0] != canvas.shape[0] or result.image.shape[1] != canvas.shape[1]


def test_clahe_grayscale_binarize_denoise_callable() -> None:
    image = _colored_slide()
    clahe = apply_clahe(image, clip_limit=2.0)
    assert clahe.shape == image.shape
    grey = to_grayscale_bgr(image)
    assert grey.shape == image.shape
    # Near-equal channels after grey conversion.
    assert abs(int(grey[50, 50, 0]) - int(grey[50, 50, 1])) <= 1
    binary = binarize_image(grey, block_size=31, c=10)
    unique = set(np.unique(binary[:, :, 0]).tolist())
    assert unique <= {0, 255}
    denoised = denoise_image(image, h=5.0)
    assert denoised.shape == image.shape


def test_blackboard_pipeline_outputs_near_binary(tmp_path: Path) -> None:
    board = np.full((200, 300, 3), 40, dtype=np.uint8)
    cv2.putText(board, "Math", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (230, 230, 230), 2)
    src = _write_bgr(tmp_path / "board.png", board)
    result = enhance_board_image(
        src,
        tmp_path / "out",
        config=default_enhance_config("blackboard"),
    )
    assert result.applied.to_grayscale is True
    assert result.applied.binarize is True
    vals = np.unique(result.image[:, :, 0])
    assert set(vals.tolist()) <= {0, 255}


def test_missing_image_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="无法读取"):
        enhance_board_image(tmp_path / "missing.png", tmp_path / "out")


def test_corners_require_four_points(tmp_path: Path) -> None:
    src = _write_bgr(tmp_path / "a.png", _colored_slide())
    with pytest.raises(ValueError, match="4"):
        enhance_board_image(
            src,
            tmp_path / "out",
            corners=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
        )


def test_save_false_skips_artifacts(tmp_path: Path) -> None:
    src = _write_bgr(tmp_path / "a.png", _colored_slide())
    result = enhance_board_image(src, tmp_path / "out", save=False)
    assert result.enhanced_path is None
    assert result.original_copy_path is None
