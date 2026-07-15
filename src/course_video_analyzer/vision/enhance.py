"""Configurable board-image enhancement before OCR.

Default stacks:

- ``electronic``: keep colour; optional mild denoise only (no grey / bin / CLAHE).
- ``blackboard`` / ``whiteboard`` / ``physical``: CLAHE → grey → denoise → binary.
- Perspective warp is independent and applied when four corners are provided.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Sequence

import cv2
import numpy as np

BoardEnhanceMode = Literal["electronic", "blackboard", "whiteboard", "physical"]

# Four corners in image coords: TL, TR, BR, BL (or any consistent order; we sort).
CornerQuad = Sequence[Sequence[float]]


@dataclass(frozen=True)
class EnhanceConfig:
    """Per-stage toggles and parameters for ``enhance_board_image``."""

    mode: BoardEnhanceMode = "electronic"
    apply_perspective: bool = False
    corners: tuple[tuple[float, float], ...] | None = None
    apply_clahe: bool = False
    clahe_clip_limit: float = 2.0
    clahe_tile_grid: tuple[int, int] = (8, 8)
    to_grayscale: bool = False
    binarize: bool = False
    binarize_block_size: int = 31
    binarize_c: int = 10
    denoise: bool = False
    denoise_h: float = 10.0
    denoise_template_window: int = 7
    denoise_search_window: int = 21
    output_name: str = "enhanced.png"


def default_enhance_config(mode: BoardEnhanceMode = "electronic") -> EnhanceConfig:
    """Return mode-specific defaults (electronic preserves colour)."""
    if mode == "electronic":
        return EnhanceConfig(
            mode=mode,
            apply_perspective=False,
            apply_clahe=False,
            to_grayscale=False,
            binarize=False,
            denoise=False,
        )
    if mode == "blackboard":
        return EnhanceConfig(
            mode=mode,
            apply_perspective=True,
            apply_clahe=True,
            clahe_clip_limit=3.0,
            to_grayscale=True,
            binarize=True,
            binarize_block_size=31,
            binarize_c=8,
            denoise=True,
            denoise_h=12.0,
        )
    # whiteboard / physical: less aggressive C than blackboard chalk noise.
    return EnhanceConfig(
        mode=mode,
        apply_perspective=True,
        apply_clahe=True,
        clahe_clip_limit=2.0,
        to_grayscale=True,
        binarize=True,
        binarize_block_size=31,
        binarize_c=10,
        denoise=True,
        denoise_h=8.0,
    )


@dataclass
class EnhanceResult:
    """Enhanced image array plus artifact paths."""

    image: np.ndarray
    source_path: Path
    enhanced_path: Path | None
    original_copy_path: Path | None
    applied: EnhanceConfig


def enhance_board_image(
    image_path: Path,
    artifact_dir: Path | None = None,
    *,
    config: EnhanceConfig | None = None,
    corners: CornerQuad | None = None,
    save: bool = True,
) -> EnhanceResult:
    """Load ``image_path``, apply configured enhancements, optionally save artifacts.

    When ``config.mode == \"electronic\"``, grayscale / CLAHE / binarize stay off
    unless the caller explicitly enables them on ``config``.
    """
    image_path = Path(image_path)
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"无法读取课板图像: {image_path}")

    cfg = config or default_enhance_config("electronic")
    if corners is not None:
        corner_tuples = _normalize_corners(corners)
        cfg = replace(cfg, apply_perspective=True, corners=corner_tuples)
    elif cfg.corners is not None:
        cfg = replace(cfg, corners=_normalize_corners(cfg.corners))

    # Electronic default: never colour-destructive unless explicitly opted in.
    if cfg.mode == "electronic":
        destructive = cfg.apply_clahe or cfg.to_grayscale or cfg.binarize
        if destructive and config is None:
            cfg = replace(cfg, apply_clahe=False, to_grayscale=False, binarize=False)

    working = image.copy()
    if cfg.apply_perspective and cfg.corners is not None:
        working = perspective_correct(working, cfg.corners)

    if cfg.apply_clahe:
        working = apply_clahe(
            working,
            clip_limit=cfg.clahe_clip_limit,
            tile_grid=cfg.clahe_tile_grid,
        )

    if cfg.to_grayscale:
        working = to_grayscale_bgr(working)

    if cfg.denoise:
        working = denoise_image(
            working,
            h=cfg.denoise_h,
            template_window=cfg.denoise_template_window,
            search_window=cfg.denoise_search_window,
        )

    if cfg.binarize:
        working = binarize_image(
            working,
            block_size=cfg.binarize_block_size,
            c=cfg.binarize_c,
        )

    enhanced_path: Path | None = None
    original_copy_path: Path | None = None
    if save and artifact_dir is not None:
        artifact_dir = Path(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        original_copy_path = artifact_dir / "original.png"
        enhanced_path = artifact_dir / cfg.output_name
        cv2.imwrite(str(original_copy_path), image)
        cv2.imwrite(str(enhanced_path), working)

    return EnhanceResult(
        image=working,
        source_path=image_path,
        enhanced_path=enhanced_path,
        original_copy_path=original_copy_path,
        applied=cfg,
    )


def perspective_correct(image: np.ndarray, corners: CornerQuad) -> np.ndarray:
    """Warp a quadrilateral board region to an axis-aligned rectangle."""
    ordered = _order_corners(_normalize_corners(corners))
    width_a = float(np.linalg.norm(ordered[2] - ordered[3]))
    width_b = float(np.linalg.norm(ordered[1] - ordered[0]))
    height_a = float(np.linalg.norm(ordered[1] - ordered[2]))
    height_b = float(np.linalg.norm(ordered[0] - ordered[3]))
    max_w = max(int(round(max(width_a, width_b))), 1)
    max_h = max(int(round(max(height_a, height_b))), 1)

    src = ordered.astype(np.float32)
    dst = np.array(
        [[0.0, 0.0], [max_w - 1.0, 0.0], [max_w - 1.0, max_h - 1.0], [0.0, max_h - 1.0]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(image, matrix, (max_w, max_h))


def apply_clahe(
    image: np.ndarray,
    *,
    clip_limit: float = 2.0,
    tile_grid: tuple[int, int] = (8, 8),
) -> np.ndarray:
    """Contrast-limited adaptive histogram equalization on the L channel (or grey)."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
    if len(image.shape) == 2 or image.shape[2] == 1:
        grey = image if len(image.shape) == 2 else image[:, :, 0]
        enhanced = clahe.apply(grey)
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    l_ch = clahe.apply(l_ch)
    merged = cv2.merge((l_ch, a_ch, b_ch))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def to_grayscale_bgr(image: np.ndarray) -> np.ndarray:
    """Convert to single-channel grey then back to 3-channel BGR for OCR engines."""
    if len(image.shape) == 2:
        grey = image
    else:
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)


def binarize_image(
    image: np.ndarray,
    *,
    block_size: int = 31,
    c: int = 10,
) -> np.ndarray:
    """Adaptive Gaussian threshold; returns 3-channel BGR of the binary mask."""
    if block_size % 2 == 0:
        block_size += 1
    block_size = max(block_size, 3)
    if len(image.shape) == 2:
        grey = image
    else:
        grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        grey,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        c,
    )
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def denoise_image(
    image: np.ndarray,
    *,
    h: float = 10.0,
    template_window: int = 7,
    search_window: int = 21,
) -> np.ndarray:
    """Fast NlMeans denoise; colour-aware when input is BGR."""
    if len(image.shape) == 2 or image.shape[2] == 1:
        grey = image if len(image.shape) == 2 else image[:, :, 0]
        denoised = cv2.fastNlMeansDenoising(
            grey,
            None,
            h=h,
            templateWindowSize=template_window,
            searchWindowSize=search_window,
        )
        return cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)
    return cv2.fastNlMeansDenoisingColored(
        image,
        None,
        h,
        h,
        template_window,
        search_window,
    )


def _normalize_corners(
    corners: CornerQuad,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]:
    points = [(float(p[0]), float(p[1])) for p in corners]
    if len(points) != 4:
        raise ValueError(f"透视矫正需要恰好 4 个角点，实际为 {len(points)}")
    return points[0], points[1], points[2], points[3]


def _order_corners(
    corners: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]],
) -> np.ndarray:
    """Order points as top-left, top-right, bottom-right, bottom-left."""
    pts = np.array(corners, dtype=np.float32)
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(-1)
    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = pts[int(np.argmin(sums))]  # TL
    ordered[2] = pts[int(np.argmax(sums))]  # BR
    ordered[1] = pts[int(np.argmin(diffs))]  # TR
    ordered[3] = pts[int(np.argmax(diffs))]  # BL
    return ordered
